"""
PVESHClient: Lightweight wrapper around `pvesh` commands for Proxmox API access.

This module provides a client for interacting with Proxmox endpoints using subprocess calls to `pvesh`,
with optional Pydantic model parsing and endpoint discovery/caching.
"""

import json
import subprocess
import time
from functools import cached_property
from types import TracebackType
from typing import Any, Self, TypeVar

import httpx
from pydantic import BaseModel, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from orbitlab.clients.proxmox.exceptions import HTTPConfigError, PVECommandError
from orbitlab.clients.proxmox.models import ApplianceInfo, ProxmoxAppliances, ProxmoxClusterStatus, ProxmoxTaskStatus
from orbitlab.data_types import ApplianceType, TaskStatus

T = TypeVar("T", bound=BaseModel)


class HTTPConfig(BaseSettings):
    """
    Configuration for HTTP API access to Proxmox.

    Attributes:
        api_url (str): The API URL endpoint.
        token_id (str | None): The authentication token ID.
        token_secret (str | None): The authentication token secret.
        user (str | None): The username for authentication.
        password (str | None): The password for authentication.
        verify_ssl (bool): Whether to verify SSL certificates.
        timeout (int): Timeout for API requests in seconds.
    """

    model_config = SettingsConfigDict(
        env_nested_delimiter="_",
        env_nested_max_split=1,
        env_prefix="PROXMOX_",
    )

    api_url: str
    token_id: str | None = None
    token_secret: str | None = None
    user: str | None = None
    password: str | None = None
    verify_ssl: bool = True
    timeout: int = 10
    configured: bool = False

    def get_session_params(self) -> dict:
        """Generate and return HTTP session parameters for connecting to the Proxmox API.

        Returns:
            dict: A dictionary containing the HTTPX session parameters.
        """
        params = {
            "base_url": self.api_url,
            "headers": {},
            "verify": self.verify_ssl,
            "timeout": self.timeout,
        }
        if self.user:
            with httpx.Client(verify=False) as client:  # noqa: S501
                resp = client.post(
                    f"{self.api_url}/api2/json/access/ticket",
                    data={
                        "username": self.user,
                        "password": self.password,
                    },
                )
            resp.raise_for_status()
            data = resp.json()["data"]
            params["headers"]["CSRFPreventionToken"] = data["CSRFPreventionToken"]
            params["cookies"] = {"PVEAuthCookie": data["ticket"]}
        else:
            params["headers"]["Authorization"] = f"PVEAPIToken={self.token_id}={self.token_secret}"
        return params

    @model_validator(mode="after")
    def _ensure_credentials(self) -> Self:
        http = [self.token_id, self.token_secret]
        if any(http) and not all(http):
            msg = "Both `token_id`, and `token_secret` must be configured."
            raise HTTPConfigError(msg)
        basic = [self.user, self.password]
        if any(basic) and not all(basic):
            msg = "Both `user` and  `password` must be configured."
            raise HTTPConfigError(msg)
        if any(http + basic):
            self.configured = True
        return self


class Proxmox:
    """
    Proxmox client for interacting with Proxmox endpoints via HTTP API or local CLI.

    Provides methods for performing CRUD operations, retrieving data, and managing sessions
    with support for both HTTP and local command-line access.
    """

    def __init__(self, *, http_config: HTTPConfig | None = None) -> None:
        """Initialize the Proxmox client.

        Args:
            http_config (HTTPConfig | None): Optional HTTP configuration for API access.
        """
        self.http_config = http_config or HTTPConfig()

    @cached_property
    def __session__(self) -> httpx.Client:
        """Initialize and return an HTTPX client session for Proxmox API access."""
        return httpx.Client(**self.http_config.get_session_params())

    def __enter__(self) -> Self:
        """Enter the runtime context related to this object."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit the runtime context and close the HTTP session if it exists."""
        if self.__session__:
            self.__session__.close()

    def __local_request__(self, method: str, path: str, **kwargs: dict) -> dict[str, Any]:
        """Perform a local request to the Proxmox API using the pvesh CLI.

        Args:
            method (str): The request method (e.g., 'get', 'create', 'set', 'delete').
            path (str): The API endpoint path.
            kwargs (dict): Additional parameters for the request.

        Returns:
            dict[str, Any]: The response from the local CLI command.
        """
        cmd = ["pvesh", method.lower(), path]
        if kwargs:
            for k, v in kwargs.items():
                cmd += [f"-{k}", str(v)]
        cmd.append("--output-format=json")

        result = subprocess.run(cmd, capture_output=True, text=True, check=False)  # noqa: S603
        if result.returncode != 0:
            raise PVECommandError(cmd=cmd, stderr=result.stderr)
        return json.loads(result.stdout)

    def __remote_request__(self, method: str, path: str, **kwargs: dict) -> dict[str, Any]:
        """Perform a remote HTTP request to the Proxmox API.

        Args:
            method (str): The HTTP method to use (e.g., 'GET', 'POST').
            path (str): The API endpoint path.
            kwargs (dict): Additional parameters for the request.

        Returns:
            dict[str, Any]: The response data from the API.
        """
        if not self.__session__:
            msg = "HTTP session not initialized"
            raise RuntimeError(msg)

        url = f"/api2/json{path}"
        response = self.__session__.request(method.upper(), url, params=kwargs)
        response.raise_for_status()
        return response.json()["data"]

    def __request__(self, method: str, path: str, **kwargs: dict) -> str | dict[str, Any]:
        """Internal method to perform a request to the Proxmox API using either HTTP or local CLI.

        Args:
            method (str): The request method ('get', 'create', 'set', 'delete').
            path (str): The API endpoint path.
            kwargs (dict): Additional parameters for the request.

        Returns:
            dict[str, Any]: The response from the API.
        """
        remote_method_map = {
            "get": "get",
            "create": "post",
            "set": "put",
            "delete": "delete",
        }
        if self.http_config.configured:
            return self.__remote_request__(remote_method_map[method], path, **kwargs)
        return self.__local_request__(method, path, **kwargs)

    def get(self, path: str, model: type[T] | None = None, **params: dict[str, str]) -> T | list[T] | dict | str:
        """Retrieve data from the specified Proxmox API path, optionally parsing the response into a Pydantic model.

        Args:
            path (str): The API endpoint path to retrieve data from.
            model (type[T] | None): Optional Pydantic model class to parse the response.
            params (dict[str, str]): Additional query parameters for the request.

        Returns:
            T | list[T] | dict | str: Parsed model instance(s), raw dictionary, or string response.
        """
        data = self.__request__("get", path, **params)
        if model:
            return model.model_validate(data)
        return data

    def create(self, path: str, **params: dict[str, str]) -> str | dict:
        """Create a resource at the specified Proxmox API path.

        Args:
            path (str): The API endpoint path to create the resource.
            params (dict[str, str]): Additional parameters for the create request.

        Returns:
            dict: The response from the create operation, or an empty dict if no response.
        """
        return self.__request__("create", path, **params)

    def set(self, path: str, **params: dict[str, str]) -> dict:
        """Update or modify a resource at the specified Proxmox API path.

        Args:
            path (str): The API endpoint path to update.
            params (dict[str, str]): Additional parameters for the set request.

        Returns:
            dict: The response from the set operation, or an empty dict if no response.
        """
        return self.__request__("set", path, **params)

    def delete(self, path: str, **params: dict[str, str]) -> dict:
        """Delete a resource at the specified Proxmox API path.

        Args:
            path (str): The API endpoint path to delete.
            params (dict[str, str]): Additional parameters for the delete request.

        Returns:
            dict: The response from the delete operation, or an empty dict if no response.
        """
        return self.__request__("delete", path, **params)

    def get_cluster_status(self) -> ProxmoxClusterStatus:
        return self.get("/cluster/status", model=ProxmoxClusterStatus)

    def get_next_vmid(self) -> int:
        """Retrieve the next available VMID from the Proxmox cluster.

        Returns:
            int: The next available VMID.
        """
        result = self.get("/cluster/nextid")
        return int(result.strip())

    def list_appliances(self, node: str, appliance_type: ApplianceType | None = None) -> ProxmoxAppliances:
        """List available LXC appliances on the specified Proxmox node.

        Args:
            node (str): The node name.
            appliance_type (ApplianceType | None): Filter for appliance type (SYSTEM, TURNKEY, or None for all).

        Returns:
            ProxmoxAppliances: A list of available LXC appliances.
        """
        appliances = self.get(f"/nodes/{node}/aplinfo", model=ProxmoxAppliances)
        match appliance_type:
            case ApplianceType.SYSTEM:
                return [apl for apl in appliances if not apl.is_turnkey]
            case ApplianceType.TURNKEY:
                return [apl for apl in appliances if apl.is_turnkey]
            case _:
                return appliances

    def download_appliance(self, node: str, storage: str, appliance: ApplianceInfo) -> str:
        """Download an LXC appliance to the specified storage on a Proxmox node.

        Args:
            node (str): The node name.
            storage (str): The storage identifier where the template will be downloaded.
            appliance (ProxmoxApplianceInfo): The appliance information for the template.

        Returns:
            str: The UPID of the task.
        """
        return self.create(f"/nodes/{node}/aplinfo", storage=storage, template=appliance.template)

    def node_in_maintenance_mode(self, node: str) -> bool:
        nodes = [node for node in self.get("/cluster/ha/status/current") if node["type"] == "lrm"]
        node_status = next(iter(i for i in nodes if i["node"] == node))
        return "maintenance" in node_status["status"]

    def get_task_status(self, node: str, upid: str) -> ProxmoxTaskStatus:
        """Retrieve the status of a specific task on a Proxmox node.

        Args:
            node (str): The node name.
            upid (str): The unique task identifier (UPID).

        Returns:
            ProxmoxTaskStatus: The status information of the specified task.
        """
        return self.get(f"/nodes/{node}/tasks/{upid}/status", model=ProxmoxTaskStatus)

    def wait_for_task(self, node: str, upid: str, interval: int = 3, timeout: int = 900) -> None:
        """Wait for a Proxmox task to complete, polling its status at regular intervals.

        Args:
            node (str): The node name.
            upid (str): The unique task identifier (UPID).
            interval (int, optional): Polling interval in seconds. Defaults to 3.
            timeout (int, optional): Maximum time to wait in seconds. Defaults to 900.

        Raises:
            TimeoutError: If the task does not complete within the specified timeout.
        """
        status = self.get_task_status(node, upid)
        start_time = time.time()
        while status == TaskStatus.RUNNING:
            time.sleep(interval)
            if (time.time() - start_time) > timeout:
                msg = f"Task {upid} timed out after {timeout}s"
                raise TimeoutError(msg)
            status = self.get_task_status(node, upid)
