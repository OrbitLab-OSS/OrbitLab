"""Proxmox Base Client."""

import base64
import functools
import json
import os
import re
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
from pydantic import BaseModel
from pydantic_settings import BaseSettings

from orbitlab.constants import ProxmoxRE
from orbitlab.data_types import StorageContentType, TaskStatus
from orbitlab.proxmox.exceptions import PctExecError

from .models import (
    VMID,
    ProxmoxAuth,
    ProxmoxStorages,
    ProxmoxTaskStatus,
    ProxmoxTermProxy,
    Task,
    VMClusterResources,
)

T = TypeVar("T", bound=BaseModel)


@functools.lru_cache(maxsize=3)
def _get_node_ip(node: str) -> str:
    output = subprocess.check_output(
        args=f"pvesh get /nodes/{node}/network -type=bridge -output-format=json",
        text=True,
        shell=True,
    )
    bridges: list[dict] = json.loads(output)
    return next(iter(bridge["address"] for bridge in bridges if bridge["iface"] == "vmbr0"))


class HTTPConfig(BaseSettings):
    """Configuration for HTTP API access to Proxmox."""

    node: str
    verify_ssl: bool = False
    timeout: int = 10

    @cached_property
    def api_url(self) -> str:
        address = _get_node_ip(node=self.node)
        return f"https://{address}:8006"

    @property
    def websocket_base(self) -> str:
        """Get the WebSocket base URL by replacing https with wss in the API URL."""
        return self.api_url.replace("https", "wss")

    def get_session_params(self) -> dict:
        """Generate and return HTTP session parameters for connecting to the Proxmox API."""
        with httpx.Client(verify=False) as client:  # noqa: S501
            resp = client.post(
                url=f"{self.api_url}/api2/json/access/ticket",
                data={"username": "orbitlab@pve", "password": os.environ["ORBITLAB_VAULT_KEY"]},
            )
        resp.raise_for_status()
        auth = ProxmoxAuth.model_validate(resp.json())
        headers = {"CSRFPreventionToken": auth.data.csrf_prevention_token}
        cookies = {"PVEAuthCookie": auth.data.cookie}

        params = {
            "base_url": self.api_url,
            "headers": headers,
            "verify": self.verify_ssl,
            "timeout": self.timeout,
            "cookies": cookies
        }
        return params


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

    def close(self) -> None:
        """Close the websocket."""
        if self.ws:
            self.ws.close()

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
        return b"\n".join(output).strip()

    def __pct_exec__(self, vmid: int, filename: str) -> list[str]:
        """Execute a bash script file inside a Proxmox LXC container."""
        command = f"pct exec {vmid} -- bash -c 'bash {filename}; echo \"__EXIT_CODE__:$?\"'"
        output = self.run_command(command=command, check_output=True)
        match = re.search(rb"__EXIT_CODE__:(\d+)", output)
        if not match:
            raise PctExecError(exit_code=-1, msg="No exit code returned", logs=[])
        exit_code = int(match.group(1))
        logs = output.replace(f"__EXIT_CODE__:{exit_code}".encode(), b"")
        if exit_code > 0:
            raise PctExecError(
                exit_code=exit_code,
                msg="PCT EXEC returned a non-zero exit code.",
                logs=self.__normalize_terminal_output__(logs),
            )
        return self.__normalize_terminal_output__(logs)

    def __pct_push__(self, vmid: int, source: str, destination: Path) -> None:
        """Push a file from host to Proxmox LXC container."""
        self.run_command(command=f"pct exec {vmid} -- mkdir -p {destination.parent}")
        command = f"pct push {vmid} {source} {destination}"
        self.run_command(command=command)

    def __normalize_terminal_output__(self, raw: bytes) -> list[str]:
        """Normalize terminal output by decoding bytes and splitting into cleaned lines."""
        text = raw.decode(errors="replace")
        lines: list[str] = []
        buf = ""
        i = 0
        while i < len(text):
            ch = text[i]
            if ch == "\r":
                if i + 1 < len(text) and text[i + 1] == "\n":
                    if buf.strip():
                        lines.append(buf.rstrip())
                    buf = ""
                    i += 2
                    continue
                buf = ""
                i += 1
                continue
            if ch == "\n":
                if buf.strip():
                    lines.append(buf.rstrip())
                buf = ""
                i += 1
                continue
            buf += ch
            i += 1
        if buf.strip():
            lines.append(buf.rstrip())
        return lines

    @overload
    def run_command(self, command: str, *, check_output: Literal[False] = False) -> None: ...

    @overload
    def run_command(self, command: str, *, check_output: Literal[True]) -> bytes: ...

    def run_command(self, command: str, *, check_output: bool = False) -> bytes | None:
        """Execute a command on the remote Proxmox node or locally via subprocess."""
        if self.ws:
            self.ws.send(payload=f"0:{len(command)}:{command}\n")
            self.ws.send(payload="0:1:\n")
            output = self.__recv__(command=command, capture=True)
        else:
            output = subprocess.check_output(args=command, shell=True)
        if check_output:
            return output
        return None

    def lxc_push_file(self, vmid: int, source: Path, destination: Path) -> None:
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

    def lxc_execute_script(self, vmid: int, content: str) -> list[str]:
        """Execute a script inside an LXC container."""
        retries = 0
        while True:
            try:
                with tempfile.NamedTemporaryFile() as file:
                    command = ProxmoxRE.SCRIPT.format(filename=file.name, content=content)
                    self.run_command(command=command)
                    self.__pct_push__(vmid=vmid, source=file.name, destination=Path(file.name))
                    self.run_command(command=f"rm -f {file.name}")
                    return self.__pct_exec__(vmid=vmid, filename=file.name)
            except PctExecError as err:
                retries += 1
                time.sleep(retries)
                if retries >= 3:  # noqa: PLR2004
                    raise RuntimeError from err


class Proxmox:
    """Proxmox client for interacting with Proxmox endpoints via HTTP API or local CLI."""

    def __init__(self) -> None:
        """Initialize the Proxmox client."""
        self.http_config = HTTPConfig(node=self.__node__)

    @cached_property
    def __session__(self) -> httpx.Client:
        """Initialize and return an HTTPX client session for Proxmox API access."""
        return httpx.Client(**self.http_config.get_session_params())

    @cached_property
    def __node__(self) -> str:
        """Get the local node name from the Proxmox cluster status."""
        return subprocess.check_output("hostname", text=True, shell=True).strip()

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

    def __request__(self, method: str, path: str, **kwargs: int | str | list[str]) -> str | dict[str, Any]:
        """Internal method to perform a request to the Proxmox API using either HTTP or local CLI."""
        remote_method_map = {
            "get": "get",
            "create": "post",
            "set": "put",
            "delete": "delete",
        }
        kwargs = {k.replace("_", "-"):v for k,v in kwargs.items()}
        response = self.__session__.request(method=remote_method_map[method].upper(), url=f"/api2/json{path}", params=kwargs)
        response.raise_for_status()
        return response.json()["data"]

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
    def create(self, path: str, model: None = None, **params: int | str| list[str]) -> str | dict: ...

    @overload
    def create(self, path: str, model: type[T], **params: int | str| list[str]) -> T: ...

    def create(self, path: str, model: type[T] | None = None, **params: int | str | list[str]) -> T | str | dict:
        """Create a resource at the specified Proxmox API path."""
        data = self.__request__("create", path, **params)
        if model:
            return model.model_validate(data)
        return data

    @overload
    def set(self, path: str, model: type[T], **params: int | str) -> T: ...

    @overload
    def set(self, path: str, model: None = None, **params: int | str) -> str | dict[str, Any]: ...

    def set(self, path: str, model: type[T] | None = None, **params: int | str) -> T | str | dict[str, Any]:
        """Update or modify a resource at the specified Proxmox API path."""
        data = self.__request__(method="set", path=path, **params)
        if model:
            return model.model_validate(data)
        return data

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

    def get_next_vmid(self, *, vmid: int | None = None) -> int:
        """Retrieve the next available VMID from the Proxmox cluster."""
        if vmid:
            try:
                response = self.get(path="/cluster/nextid", model=VMID, vmid=vmid)
            except httpx.HTTPStatusError:
                return 0
            else:
                return vmid
        response = self.get(path="/cluster/nextid", model=VMID)
        return response.root

    def get_task_status(self, node: str, upid: str) -> ProxmoxTaskStatus:
        """Retrieve the status of a specific task on a Proxmox node."""
        return self.get(f"/nodes/{node}/tasks/{upid}/status", model=ProxmoxTaskStatus)

    def wait_for_task(self, task: Task, interval: int = 3, timeout: int = 900) -> None:
        """Wait for a Proxmox task to complete, polling its status at regular intervals."""
        _task = self.get_task_status(task.node, task.upid)
        start_time = time.time()
        while _task.status == TaskStatus.RUNNING:
            time.sleep(interval)
            if (time.time() - start_time) > timeout:
                msg = f"Task {task.upid} timed out after {timeout}s"
                raise TimeoutError(msg)
            _task = self.get_task_status(task.node, task.upid)

    def get_node_for_vmid(self, vmid: int) -> str:
        """Retrieve the node name that hosts the VM with the specified VMID."""
        params = {"type": "vm"}
        resources = self.get(path="/cluster/resources", model=VMClusterResources, **params)
        return resources.get_node(vmid=vmid)

    def list_storages_for_node(self, node: str, content_type: StorageContentType | None = None) -> list[str]:
        """List all storage names for a given node and optional content type."""
        params = {"enabled": "1"}
        if content_type:
            params["content"] = str(content_type)
        return self.get(f"/nodes/{node}/storage", model=ProxmoxStorages, **params).list_all()

    def create_connection(self, node: str = "") -> RemoteExecution:
        """Create a remote execution connection to a Proxmox node."""
        if not node:
            node = self.__node__
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

    def get_terminal_websocket(self, compute_type: Literal["qemu", "lxc"], vmid: int) -> websocket.WebSocket:
        """Create and return a WebSocket connection to the terminal of a specified VM or LXC container."""
        node = self.get_node_for_vmid(vmid=vmid)
        proxy = self.create(f"/nodes/{node}/{compute_type}/{vmid}/termproxy", model=ProxmoxTermProxy)
        websocket_url = (
            f"{self.http_config.websocket_base}/api2/json/nodes/{node}/{compute_type}/{vmid}/vncwebsocket"
            f"?port={proxy.port}&vncticket={quote(proxy.ticket)}"
        )
        cookie = self.__session__.cookies["PVEAuthCookie"]
        terminal_websocket = websocket.create_connection(
            url=websocket_url,
            cookie=f"PVEAuthCookie={cookie}",
            sslopt={"cert_reqs": ssl.CERT_NONE},
        )
        terminal_websocket.send(f"{proxy.user}:{proxy.ticket}\n")
        return terminal_websocket

    def create_lxc(self, *, node: str, params: dict[str, str | int], start: bool = False) -> None:
        """Create an LXC container on the specified Proxmox node with the given parameters."""
        task = self.create(path=f"/nodes/{node}/lxc", model=Task, **params)
        self.wait_for_task(task=task)
        if start:
            vmid = params["vmid"]
            task = self.create(path=f"/nodes/{node}/lxc/{vmid}/status/start", model=Task)
            self.wait_for_task(task=task)

    def create_vm(self, *, node: str, params: dict[str, str | int], disk_size: int, start: bool = False) -> None:
        """Create a virtual machine (VM) on the specified Proxmox node with the given parameters."""
        vmid = params["vmid"]
        task = self.create(path=f"/nodes/{node}/qemu", model=Task, **params)
        self.wait_for_task(task=task)
        resize_pararms = {"disk": "scsi0", "size": f"{disk_size}G"}
        time.sleep(1)  # Take a beat so Proxmox doesn't panic when trying to resize the disk after creation
        task = self.set(f"/nodes/{node}/qemu/{vmid}/resize", model=Task, **resize_pararms)
        self.wait_for_task(task=task)
        if start:
            task = self.create(path=f"/nodes/{node}/qemu/{vmid}/status/start", model=Task)
            self.wait_for_task(task=task)
