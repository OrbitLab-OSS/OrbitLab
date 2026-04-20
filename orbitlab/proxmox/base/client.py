"""Proxmox Base Client."""

import asyncio
import base64
import functools
import json
import os
import re
import ssl
import subprocess
import tempfile
import textwrap
import time
from functools import cached_property
from pathlib import Path
from types import TracebackType
from typing import Any, Final, Literal, Self, TypeVar, overload
from urllib.parse import quote

import httpx
from websockets.asyncio import client as websocket
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
    QemuConfig
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
        if os.environ.get("ORBITLAB_DEV"):
            return os.environ["PROXMOX_API_URL"]
        address = _get_node_ip(node=self.node)
        return f"https://{address}:8006"

    @property
    def websocket_base(self) -> str:
        """Get the WebSocket base URL by replacing https with wss in the API URL."""
        return self.api_url.replace("https", "wss")

    async def generate_websocket_url(self, node: str, port: str, ticket: str, *, compute_type: str = "", vmid: int = 0) -> str:
        if compute_type and vmid:
            return (
                f"{self.websocket_base}/api2/json/nodes/{node}/{compute_type}/{vmid}/vncwebsocket"
                f"?port={port}&vncticket={quote(ticket)}"
            )
        return f"{self.websocket_base}/api2/json/nodes/{node}/vncwebsocket?port={port}&vncticket={quote(ticket)}"

    def get_session_params(self) -> dict:
        """Generate and return HTTP session parameters for connecting to the Proxmox API."""
        username = os.environ.get("PROXMOX_USER", ProxmoxRE.USER)
        password = os.environ["ORBITLAB_VAULT_KEY"] if username == ProxmoxRE.USER else os.environ["PROXMOX_PASSWORD"]
        with httpx.Client(verify=False) as client:  # noqa: S501
            resp = client.post(
                url=f"{self.api_url}/api2/json/access/ticket",
                data={"username": username, "password": password},
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


class RemoteExecutionConfig(BaseModel):
    """Configuration for remote WebSocket connections to Proxmox nodes."""

    websocket_url: str
    user: str
    ticket: str
    cookie: str

    @property
    def use_websocket(self) -> bool:
        return self.user != ProxmoxRE.USER

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

    def __init__(self, node: str, config: RemoteExecutionConfig) -> None:
        """Initialize."""
        self.node = node
        self.config = config
        self.ws: websocket.ClientConnection | None = None

    async def close(self) -> None:
        """Close the websocket."""
        if self.ws:
            await self.ws.close()

    async def __aenter__(self) -> Self:
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    @classmethod
    async def create_default_context(cls) -> ssl.SSLContext:
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        return ssl_context

    async def connect(self) -> None:
        """Establish WebSocket connection to the remote Proxmox node if remote config is available."""
        if self.config.use_websocket:
            ssl_context = await self.create_default_context()
            self.ws = await websocket.connect(
                self.config.websocket_url,
                additional_headers={"Cookie": f"PVEAuthCookie={self.config.cookie}"},
                ssl=ssl_context,
            )
            await self.ws.send(self.config.auth_message)
            await self.__recv__()

    async def __parse_frame__(self, frame: str, username: str) -> list[str]:
        """Parse WebSocket frame data by removing escape sequences and filtering out username lines."""
        frame = frame.replace("\x1b[?2004l", "").replace("\x1b[?2004", "")
        return [line for line in frame.split(sep="\r\n") if line and username not in line]

    async def __recv__(self, *, command: str = "", capture: bool = False) -> str:
        """Receive and process WebSocket frame data from the remote connection."""
        if not self.ws:
            raise RuntimeError
        output: list[str] = []
        username = self.config.user.split(sep="@")[0]
        while True:
            frame = await self.ws.recv(decode=True)
            if capture and command not in frame:
                output.extend(await self.__parse_frame__(frame=frame, username=username))
            if "\x1b[?" in frame and username in frame:
                break
        return "\n".join(output).strip()

    async def __pct_exec__(self, vmid: int, filename: str) -> list[str]:
        """Execute a bash script file inside a Proxmox LXC container."""
        command = f"pct exec {vmid} -- bash -c 'bash {filename}; echo \"__EXIT_CODE__:$?\"'"
        output = await self.run_command(command=command, check_output=True)
        match = re.search(r"__EXIT_CODE__:(\d+)", output)
        if not match:
            raise PctExecError(exit_code=-1, msg="No exit code returned", logs=[])
        exit_code = int(match.group(1))
        logs = output.replace(f"__EXIT_CODE__:{exit_code}", "")
        if exit_code > 0:
            raise PctExecError(
                exit_code=exit_code,
                msg="PCT EXEC returned a non-zero exit code.",
                logs=await self.__normalize_terminal_output__(logs),
            )
        return await self.__normalize_terminal_output__(logs)

    async def __pct_push__(self, vmid: int, source: Path, destination: Path) -> None:
        """Push a file from host to Proxmox LXC container."""
        await self.run_command(command=f"pct exec {vmid} -- mkdir -p {destination.parent}")
        command = f"pct push {vmid} {source} {destination}"
        await self.run_command(command=command)

    async def __normalize_terminal_output__(self, text: str) -> list[str]:
        """Normalize terminal output by decoding bytes and splitting into cleaned lines."""
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
    async def run_command(self, command: str, *, check_output: Literal[False] = False) -> None: ...

    @overload
    async def run_command(self, command: str, *, check_output: Literal[True]) -> str: ...

    async def run_command(self, command: str, *, check_output: bool = False) -> str | None:
        """Execute a command on the remote Proxmox node or locally via subprocess."""
        if self.ws:
            await self.ws.send(f"0:{len(command)}:{command}\n")
            await self.ws.send("0:1:\n")
            output = await self.__recv__(command=command, capture=True)
        else:
            output = subprocess.check_output(args=command, shell=True, text=True)
        if check_output:
            return output
        return None

    async def write_file(self, content: str) -> Path:
        with tempfile.NamedTemporaryFile() as file:
            heredoc = f"cat << 'EOF' | base64 -d > {file.name}"
            await self.ws.send(f"0:{len(heredoc)}:{heredoc}\n")
            await self.ws.send("0:1:\n")
            encoded = base64.b64encode(content.encode()).decode()
            await self.ws.send(f"0:{len(encoded)}:{encoded}\n")
            await self.ws.send("0:1:\n")
            end_heredoc = "EOF"
            await self.ws.send(f"0:{len(end_heredoc)}:{end_heredoc}\n")
            await self.ws.send("0:1:\n")
            await self.__recv__()
            return Path(file.name)

    async def lxc_push_file(self, vmid: int, source: Path, destination: Path) -> None:
        """Push a file from the host to a Proxmox LXC container."""
        await self.__pct_push__(vmid=vmid, source=source, destination=destination)
        await self.run_command(command=f"rm -f {source}")

    async def lxc_execute_script(self, vmid: int, content: str) -> list[str]:
        """Execute a script inside an LXC container."""
        with tempfile.NamedTemporaryFile() as file:
            command = ProxmoxRE.SCRIPT.format(filename=file.name, content=textwrap.dedent(content))
            print(command)
            await self.run_command(command=command)
            await self.__pct_push__(vmid=vmid, source=file.name, destination=Path(file.name))
            await self.run_command(command=f"rm -f {file.name}")
            return await self.__pct_exec__(vmid=vmid, filename=file.name)


class Proxmox:
    """Proxmox client for interacting with Proxmox endpoints via HTTP API or local CLI."""

    def __init__(self) -> None:
        """Initialize the Proxmox client."""
        self.http_config = HTTPConfig(node=self.__node__)

    @cached_property
    def __session__(self) -> httpx.AsyncClient:
        """Initialize and return an HTTPX client session for Proxmox API access."""
        return httpx.AsyncClient(**self.http_config.get_session_params())

    @cached_property
    def __node__(self) -> str:
        """Get the local node name from the Proxmox cluster status."""
        if os.environ.get("ORBITLAB_DEV"):
            return os.environ["PROXMOX_NODE"]
        try:
            return subprocess.check_output("hostname", text=True, shell=True).strip()
        except subprocess.CalledProcessError:
            return ""

    def __aenter__(self) -> Self:
        """Enter the runtime context related to this object."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit the runtime context and close the HTTP session if it exists."""
        if self.__session__:
            await self.__session__.aclose()

    async def __request__(self, method: str, path: str, **kwargs: int | str | list[str]) -> str | dict[str, Any]:
        """Internal method to perform a request to the Proxmox API using either HTTP or local CLI."""
        remote_method_map = {
            "get": "get",
            "create": "post",
            "set": "put",
            "delete": "delete",
        }
        kwargs = {k.replace("_", "-"):v for k,v in kwargs.items()}
        response = await self.__session__.request(method=remote_method_map[method].upper(), url=f"/api2/json{path}", params=kwargs)
        response.raise_for_status()
        return response.json()["data"]

    @overload
    async def get(self, path: str, model: type[T], **params: int | str) -> T: ...

    @overload
    async def get(self, path: str, model: None, **params: int | str) -> str | dict: ...

    async def get(self, path: str, model: type[T] | None = None, **params: int | str) -> T | dict | str:
        """Retrieve data from the specified Proxmox API path, optionally parsing the response into a Pydantic model."""
        data = await self.__request__("get", path, **params)
        if model:
            return model.model_validate(obj=data)
        return data

    @overload
    async def create(self, path: str, model: None = None, **params: int | str| list[str]) -> str | dict: ...

    @overload
    async def create(self, path: str, model: type[T], **params: int | str| list[str]) -> T: ...

    async def create(self, path: str, model: type[T] | None = None, **params: int | str | list[str]) -> T | str | dict:
        """Create a resource at the specified Proxmox API path."""
        data = await self.__request__("create", path, **params)
        if model:
            return model.model_validate(data)
        return data

    @overload
    async def set(self, path: str, model: type[T], **params: int | str) -> T: ...

    @overload
    async def set(self, path: str, model: None = None, **params: int | str) -> str | dict[str, Any]: ...

    async def set(self, path: str, model: type[T] | None = None, **params: int | str) -> T | str | dict[str, Any]:
        """Update or modify a resource at the specified Proxmox API path."""
        data = await self.__request__(method="set", path=path, **params)
        if model:
            return model.model_validate(data)
        return data

    @overload
    async def delete(self, path: str, model: type[T], **params: int | str) -> T: ...

    @overload
    async def delete(self, path: str, model: None = None, **params: int | str) -> str | dict: ...

    async def delete(self, path: str, model: type[T] | None = None, **params: int | str) -> T | str | dict[str, Any]:
        """Delete a resource at the specified Proxmox API path."""
        data = await self.__request__(method="delete", path=path, **params)
        if model:
            return model.model_validate(data)
        return data

    async def get_next_vmid(self, *, vmid: int | None = None) -> int:
        """Retrieve the next available VMID from the Proxmox cluster."""
        if vmid:
            try:
                response = await self.get(path="/cluster/nextid", model=VMID, vmid=vmid)
            except httpx.HTTPStatusError:
                return 0
            else:
                return vmid
        response = await self.get(path="/cluster/nextid", model=VMID)
        return response.root

    async def get_task_status(self, node: str, upid: str) -> ProxmoxTaskStatus:
        """Retrieve the status of a specific task on a Proxmox node."""
        return await self.get(f"/nodes/{node}/tasks/{upid}/status", model=ProxmoxTaskStatus)

    async def wait_for_task(self, task: Task, interval: int = 3, timeout: int = 900) -> None:
        """Wait for a Proxmox task to complete, polling its status at regular intervals."""
        _task = await self.get_task_status(task.node, task.upid)
        start_time = time.time()
        while _task.status == TaskStatus.RUNNING:
            await asyncio.sleep(interval)
            if (time.time() - start_time) > timeout:
                msg = f"Task {task.upid} timed out after {timeout}s"
                raise TimeoutError(msg)
            _task = await self.get_task_status(task.node, task.upid)
        _task.raise_for_status()

    async def get_node_for_vmid(self, vmid: int) -> str:
        """Retrieve the node name that hosts the VM with the specified VMID."""
        params = {"type": "vm"}
        resources = await self.get(path="/cluster/resources", model=VMClusterResources, **params)
        return resources.get_node(vmid=vmid)

    async def get_vm_root_volume_id(self, vmid: int) -> str:
        node = await self.get_node_for_vmid(vmid=vmid)
        config = await self.get(path=f"/nodes/{node}/qemu/{vmid}/config", model=QemuConfig)
        return config.root_volume_id

    async def list_storages_for_node(self, node: str, content_type: StorageContentType | None = None) -> list[str]:
        """List all storage names for a given node and optional content type."""
        params = {"enabled": "1"}
        if content_type:
            params["content"] = str(content_type)
        storages = await self.get(f"/nodes/{node}/storage", model=ProxmoxStorages, **params)
        return storages.list_all()

    async def create_connection(self, node: str = "") -> RemoteExecution:
        """Create a remote execution connection to a Proxmox node."""
        if not node:
            node = self.__node__
        proxy = await self.create(f"/nodes/{node}/termproxy", model=ProxmoxTermProxy)
        return RemoteExecution(
            node=node,
            config=RemoteExecutionConfig(
                websocket_url=await self.http_config.generate_websocket_url(node=node, port=proxy.port, ticket=proxy.ticket),
                user=proxy.user,
                ticket=proxy.ticket,
                cookie=self.__session__.cookies["PVEAuthCookie"],
            ),
        )

    async def get_terminal_websocket(self, compute_type: Literal["qemu", "lxc"], vmid: int) -> websocket.ClientConnection:
        """Create and return a WebSocket connection to the terminal of a specified VM or LXC container."""
        node = await self.get_node_for_vmid(vmid=vmid)
        proxy = await self.create(f"/nodes/{node}/{compute_type}/{vmid}/termproxy", model=ProxmoxTermProxy)
        cookie = self.__session__.cookies["PVEAuthCookie"]
        ssl_context = await RemoteExecution.create_default_context()
        terminal_websocket = await websocket.connect(
            await self.http_config.generate_websocket_url(node=node, port=proxy.port, ticket=proxy.ticket, compute_type=compute_type, vmid=vmid),
            additional_headers={"Cookie": f"PVEAuthCookie={cookie}"},
            ssl=ssl_context,
        )
        await terminal_websocket.send(f"{proxy.user}:{proxy.ticket}\n")
        return terminal_websocket

    async def create_lxc(self, *, node: str, params: dict[str, str | int], start: bool = False) -> None:
        """Create an LXC container on the specified Proxmox node with the given parameters."""
        task = await self.create(path=f"/nodes/{node}/lxc", model=Task, **params)
        self.wait_for_task(task=task)
        if start:
            vmid = params["vmid"]
            task = await self.create(path=f"/nodes/{node}/lxc/{vmid}/status/start", model=Task)
            await self.wait_for_task(task=task)

    async def create_vm(self, *, node: str, params: dict[str, str | int], disk_size: int, start: bool = False) -> None:
        """Create a virtual machine (VM) on the specified Proxmox node with the given parameters."""
        vmid = params["vmid"]
        task = await self.create(path=f"/nodes/{node}/qemu", model=Task, **params)
        await self.wait_for_task(task=task)
        resize_pararms = {"disk": "scsi0", "size": f"{disk_size}G"}
        await asyncio.sleep(1)  # Take a beat so Proxmox doesn't panic when trying to resize the disk after creation
        task = await self.set(f"/nodes/{node}/qemu/{vmid}/resize", model=Task, **resize_pararms)
        await self.wait_for_task(task=task)
        if start:
            task = await self.create(path=f"/nodes/{node}/qemu/{vmid}/status/start", model=Task)
            await self.wait_for_task(task=task)
