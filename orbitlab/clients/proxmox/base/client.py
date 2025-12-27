"""Proxmox Base Client."""

import base64
import json
import ssl
import subprocess
import tempfile
import time
from functools import cached_property
from pathlib import Path
from types import TracebackType
from typing import Any, Final, Literal, Self, TypeVar, overload
from urllib.parse import quote

import httpx
import websocket
from pydantic import BaseModel, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from orbitlab.clients.proxmox.cluster.models import ProxmoxClusterStatus
from orbitlab.clients.proxmox.exceptions import HTTPConfigError, PVECommandError
from orbitlab.constants import ProxmoxRE
from orbitlab.data_types import TaskStatus

from .models import VMID, ProxmoxAuth, ProxmoxTaskStatus, ProxmoxTermProxy, Task

T = TypeVar("T", bound=BaseModel)


def _proxmox_auth(url: str, user: str, password: str) -> ProxmoxAuth:
    with httpx.Client(verify=False) as client:  # noqa: S501
        resp = client.post(f"{url}/api2/json/access/ticket", data={"username": user, "password": password})
    resp.raise_for_status()
    return ProxmoxAuth.model_validate(resp.json())


class HTTPConfig(BaseSettings):
    """Configuration for HTTP API access to Proxmox."""

    model_config = SettingsConfigDict(
        env_nested_delimiter="_",
        env_nested_max_split=1,
        env_prefix="PROXMOX_",
    )

    api_url: str = ""
    token_id: str | None = None
    token_secret: str | None = None
    user: str | None = None
    password: str | None = None
    verify_ssl: bool = True
    timeout: int = 10
    configured: bool = False

    @property
    def websocket_base(self) -> str:
        """Get the WebSocket base URL by replacing https with wss in the API URL."""
        return self.api_url.replace("https", "wss")

    def get_session_params(self) -> dict:
        """Generate and return HTTP session parameters for connecting to the Proxmox API."""
        headers = {}
        cookies = {}

        if self.user and self.password:
            auth = _proxmox_auth(url=self.api_url, user=self.user, password=self.password)
            headers["CSRFPreventionToken"] = auth.data.csrf_prevention_token
            cookies = {"PVEAuthCookie": auth.data.cookie}
        else:
            headers["Authorization"] = f"PVEAPIToken={self.token_id}={self.token_secret}"
        params = {
            "base_url": self.api_url,
            "headers": headers,
            "verify": self.verify_ssl,
            "timeout": self.timeout,
        }
        if cookies:
            params["cookies"] = cookies
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


class RemoteConfig(BaseModel):
    """Configuration for remote WebSocket connections to Proxmox nodes."""

    websocket_url: str
    user: str
    ticket: str
    cookie: str

    @property
    def auth_message(self) -> str:
        """Generate authentication message for WebSocket connection."""
        return f"{self.user}:{self.ticket}\n"


class RemoteExecution:
    """Handle remote command execution on Proxmox nodes via WebSocket connections.

    This class provides functionality to execute commands remotely on Proxmox nodes
    using WebSocket connections for real-time communication. It supports both
    authenticated remote connections and local execution fallback.
    """
    prompt_pattern: Final = r"\w+@.+:.+#"

    def __init__(self, node: str, remote_config: RemoteConfig | None = None) -> None:
        """Initialize."""
        self.node = node
        self.remote_config = remote_config
        self.ws = None
        self.__connect__()

    def __connect__(self) -> None:
        """Establish WebSocket connection to the remote Proxmox node if remote config is available."""
        if self.remote_config:
            self.ws = websocket.create_connection(
                url=self.remote_config.websocket_url,
                cookie=f"PVEAuthCookie={self.remote_config.cookie}",
                sslopt={"cert_reqs": ssl.CERT_NONE},
            )
            self.ws.send(payload=self.remote_config.auth_message)
            self.__recv__()
            print("CONNECTED")

    def __parse_frame__(self, frame: bytes, username: bytes) -> list[bytes]:
        """Parse WebSocket frame data by removing escape sequences and filtering out username lines."""
        frame = frame.replace(b"\x1b[?2004l", b"").replace(b"\x1b[?2004", b"")
        return [line for line in frame.split(sep=b"\r\n") if line and username not in line]

    def __recv__(self, *, command: str = "", capture: bool = False) -> bytes:
        """Receive and process WebSocket frame data from the remote connection."""
        if self.ws is None or self.remote_config is None:
            raise TypeError
        output: list[bytes] = []
        username = self.remote_config.user.split(sep="@")[0].encode()
        while True:
            frame: bytes = self.ws.recv() # pyright: ignore[reportAssignmentType]
            if capture and command.encode() not in frame:
                output.extend(self.__parse_frame__(frame=frame, username=username))
            if b"\x1b[?" in frame and username in frame:
                break
        print(output)
        return b"\n".join(output).strip()

    def __pct_exec__(self, vmid: str, filename: str) -> None:
        """Execute a bash script file inside a Proxmox LXC container."""
        command = f"pct exec {vmid} -- bash {filename} && rm -f {filename}"
        self.run_command(command=command)

    def __pct_push__(self, vmid: str, source: str, destination: Path) -> None:
        """Push a file from host to Proxmox LXC container."""
        self.run_command(command=f"pct exec {vmid} -- mkdir -p {destination.parent}")
        command = f"pct push {vmid} {source} {destination}"
        self.run_command(command=command)

    @overload
    def run_command(self, command: str, *, check_output: Literal[False] = False) -> None: ...

    @overload
    def run_command(self, command: str, *, check_output: Literal[True]) -> bytes: ...

    def run_command(self, command: str, *, check_output: bool = False) -> bytes | None:
        """Execute a command on the remote Proxmox node or locally via subprocess."""
        print("COMMAND", command)
        if self.ws:
            self.ws.send(payload=f"0:{len(command)}:{command}\n")
            self.ws.send(payload="0:1:\n")
            output = self.__recv__(command=command, capture=True)
        else:
            output = subprocess.check_output(args=command)
        if check_output:
            return output
        return None

    def lxc_push_file(self, vmid: str, source: Path, destination: Path) -> None:
        """Push a file from the host to a Proxmox LXC container."""
        if self.ws:
            chunk_size = 4096
            with tempfile.NamedTemporaryFile() as file:
                heredoc = f"cat << 'EOF' | base64 -d > {file.name}"
                self.ws.send(payload=f"0:{len(heredoc)}:{heredoc}\n")
                self.ws.send(payload="0:1:\n")
                with source.open("rb") as _file:
                    while chunk := _file.read(chunk_size):
                        encoded = base64.b64encode(chunk).decode()
                        self.ws.send(payload=f"0:{len(encoded)}:{encoded}\n")
                        self.ws.send(payload="0:1:\n")
                end_heredoc = "EOF"
                self.ws.send(payload=f"0:{len(end_heredoc)}:{end_heredoc}\n")
                self.ws.send(payload="0:1:\n")
                self.__recv__()
        self.__pct_push__(vmid=vmid, source=file.name, destination=destination)
        self.run_command(command=f"rm -f {file.name}")

    def lxc_execute_script(self, vmid: str, content: str) -> None:
        """Execute a script inside an LXC container."""
        with tempfile.NamedTemporaryFile() as file:
            command = ProxmoxRE.SCRIPT.format(filename=file.name, content=content)
            self.run_command(command=command)
            self.__pct_push__(vmid=vmid, source=file.name, destination=Path(file.name))
            self.run_command(command=f"rm -f {file.name}")
            self.__pct_exec__(vmid=vmid, filename=file.name)


class Proxmox:
    """Proxmox client for interacting with Proxmox endpoints via HTTP API or local CLI."""

    def __init__(self, *, http_config: HTTPConfig | None = None) -> None:
        """Initialize the Proxmox client."""
        self.http_config = http_config or HTTPConfig()

    @cached_property
    def __session__(self) -> httpx.Client:
        """Initialize and return an HTTPX client session for Proxmox API access."""
        return httpx.Client(**self.http_config.get_session_params())

    @cached_property
    def __node__(self) -> str:
        """Get the local node name from the Proxmox cluster status."""
        cluster = self.get("/cluster/status", model=ProxmoxClusterStatus)
        return cluster.get_local_node()

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

    def __local_request__(self, method: str, path: str, **kwargs: int | str) -> dict[str, Any]:
        """Perform a local request to the Proxmox API using the pvesh CLI."""
        cmd = ["pvesh", method.lower(), path]
        if kwargs:
            for k, v in kwargs.items():
                cmd += [f"-{k}", str(v)]
        cmd.append("--output-format=json")

        result = subprocess.run(args=cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise PVECommandError(cmd=cmd, stderr=result.stderr)
        return json.loads(result.stdout)

    def __remote_request__(self, method: str, path: str, **kwargs: str | int) -> dict[str, Any]:
        """Perform a remote HTTP request to the Proxmox API."""
        if not self.__session__:
            msg = "HTTP session not initialized"
            raise RuntimeError(msg)

        response = self.__session__.request(method=method.upper(), url=f"/api2/json{path}", params=kwargs)
        response.raise_for_status()
        return response.json()["data"]

    def __request__(self, method: str, path: str, **kwargs: int | str) -> str | dict[str, Any]:
        """Internal method to perform a request to the Proxmox API using either HTTP or local CLI."""
        remote_method_map = {
            "get": "get",
            "create": "post",
            "set": "put",
            "delete": "delete",
        }
        kwargs = {k.replace("_", "-"):v for k,v in kwargs.items()}
        if self.http_config.configured:
            return self.__remote_request__(remote_method_map[method], path, **kwargs)
        return self.__local_request__(method, path, **kwargs)

    @overload
    def get(self, path: str, model: type[T], **params: int | str) -> T: ...

    @overload
    def get(self, path: str, model: None, **params: int | str) -> str | dict: ...

    def get(self, path: str, model: type[T] | None = None, **params: int | str) -> T | dict | str:
        """Retrieve data from the specified Proxmox API path, optionally parsing the response into a Pydantic model."""
        data = self.__request__("get", path, **params)
        if model:
            return model.model_validate(obj=data)
        return data

    @overload
    def create(self, path: str, model: None = None, **params: int | str) -> str | dict: ...

    @overload
    def create(self, path: str, model: type[T], **params: int | str) -> T: ...

    def create(self, path: str, model: type[T] | None = None, **params: int | str) -> T | str | dict:
        """Create a resource at the specified Proxmox API path."""
        data = self.__request__("create", path, **params)
        if model:
            return model.model_validate(data)
        return data

    def set(self, path: str, **params: int | str) -> str | dict[str, Any]:
        """Update or modify a resource at the specified Proxmox API path."""
        return self.__request__(method="set", path=path, **params)

    @overload
    def delete(self, path: str, model: type[T], **params: int | str) -> T: ...

    @overload
    def delete(self, path: str, model: None = None, **params: int | str) -> str | dict: ...

    def delete(self, path: str, model: type[T] | None = None, **params: int | str) -> T | str | dict[str, Any]:
        """Delete a resource at the specified Proxmox API path."""
        data = self.__request__(method="delete", path=path, **params)
        if model:
            return model.model_validate(data)
        return data

    def get_next_vmid(self) -> int:
        """Retrieve the next available VMID from the Proxmox cluster."""
        response = self.get(path="/cluster/nextid", model=VMID)
        return response.root

    def get_task_status(self, node: str, upid: str) -> ProxmoxTaskStatus:
        """Retrieve the status of a specific task on a Proxmox node."""
        print("GET TASK", upid)
        return self.get(f"/nodes/{node}/tasks/{upid}/status", model=ProxmoxTaskStatus)

    def wait_for_task(self, node: str, upid: str, interval: int = 3, timeout: int = 900) -> None:
        """Wait for a Proxmox task to complete, polling its status at regular intervals."""
        task = self.get_task_status(node, upid)
        start_time = time.time()
        while task.status == TaskStatus.RUNNING:
            time.sleep(interval)
            if (time.time() - start_time) > timeout:
                msg = f"Task {upid} timed out after {timeout}s"
                raise TimeoutError(msg)
            task = self.get_task_status(node, upid)

    def create_connection(self, node: str = "") -> RemoteExecution:
        """Create a remote execution connection to a Proxmox node."""
        if not node:
            node = self.__node__
        if self.http_config.configured:
            proxy = self.create(f"/nodes/{node}/termproxy", model=ProxmoxTermProxy)
            websocket_url = (
                f"{self.http_config.websocket_base}/api2/json/nodes/{node}/vncwebsocket"
                f"?port={proxy.port}&vncticket={quote(proxy.ticket)}"
            )
            return RemoteExecution(
                node=node,
                remote_config=RemoteConfig(
                    websocket_url=websocket_url,
                    user=proxy.user,
                    ticket=proxy.ticket,
                    cookie=self.__session__.cookies["PVEAuthCookie"],
                ),
            )
        return RemoteExecution(node=node)

    def create_lxc(self, *, node: str, params: dict[str, str], start: bool = False) -> None:
        """Create an LXC container on the specified Proxmox node with the given parameters."""
        task = self.create(path=f"/nodes/{node}/lxc", model=Task, **params)
        self.wait_for_task(node=task.node, upid=task.upid)
        if start:
            vmid = params["vmid"]
            task = self.create(path=f"/nodes/{node}/lxc/{vmid}/status/start", model=Task)
            self.wait_for_task(node=task.node, upid=task.upid)
