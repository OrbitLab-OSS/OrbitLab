"""Proxmox Base Client."""

import asyncio
import base64
import functools
import hashlib
import ipaddress
import json
import os
import re
import ssl
from string import Template
import subprocess
import tempfile
import textwrap
import time
from functools import cached_property
from pathlib import Path
from types import TracebackType
from typing import Any, Final, Literal, Self, TypeVar, overload
from urllib.parse import quote

import backoff
import httpx
from websockets.asyncio import client as websocket
from pydantic import BaseModel
from pydantic_settings import BaseSettings

from orbitlab.data_types import ApplianceType, InstanceType, StorageContentType, TaskStatus
from orbitlab.redis.models import BackplaneConfig

from . import models, exceptions

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


PROXMOX_USER: Final = "orbitlab@pve"

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

    async def generate_websocket_url(self, node: str, port: str, ticket: str, *, resource: models.ProxmoxComputeResource | None = None) -> str:
        if resource:
            return (
                f"{self.websocket_base}/api2/json/nodes/{node}/{resource.type}/{resource.vmid}/vncwebsocket"
                f"?port={port}&vncticket={quote(ticket)}"
            )
        return f"{self.websocket_base}/api2/json/nodes/{node}/vncwebsocket?port={port}&vncticket={quote(ticket)}"

    def get_session_params(self) -> dict:
        """Generate and return HTTP session parameters for connecting to the Proxmox API."""
        username = os.environ.get("PROXMOX_USER", PROXMOX_USER)
        password = os.environ["ORBITLAB_VAULT_KEY"] if username == PROXMOX_USER else os.environ["PROXMOX_PASSWORD"]
        with httpx.Client(verify=False) as client:  # noqa: S501
            resp = client.post(
                url=f"{self.api_url}/api2/json/access/ticket",
                data={"username": username, "password": password},
            )
        resp.raise_for_status()
        auth = models.ProxmoxAuth.model_validate(resp.json())
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


SCRIPT_WRAPPER = """cat <<'EOF' > {filename}
#!/bin/bash
set -euo pipefail
{content}
rm -f {filename}
EOF
"""

class RemoteExecutionConfig(BaseModel):
    """Configuration for remote WebSocket connections to Proxmox nodes."""

    websocket_url: str
    user: str
    ticket: str
    cookie: str

    @property
    def use_websocket(self) -> bool:
        return self.user != PROXMOX_USER

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
            raise exceptions.PctExecError(exit_code=-1, msg="No exit code returned", logs=[])
        exit_code = int(match.group(1))
        logs = output.replace(f"__EXIT_CODE__:{exit_code}", "")
        if exit_code > 0:
            raise exceptions.PctExecError(
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
            command = SCRIPT_WRAPPER.format(filename=file.name, content=textwrap.dedent(content))
            await self.run_command(command=command)
            await self.__pct_push__(vmid=vmid, source=file.name, destination=Path(file.name))
            await self.run_command(command=f"rm -f {file.name}")
            return await self.__pct_exec__(vmid=vmid, filename=file.name)


class ProxmoxBase:
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


class Proxmox(ProxmoxBase):
    """Proxmox client for interacting with Proxmox endpoints via HTTP API or local CLI."""

    async def get_view_in_proxmox_url(self, vmid: int, compute_type: Literal["lxc", "qemu"] | None = None) -> str:
        if not compute_type:
            resource = await self.get_compute_resource(vmid=vmid)
            compute_type = resource.type
        return f"https://{self.__session__.base_url.host}:8006#v1:0:={compute_type}/{vmid}"

    async def get_next_vmid(self, *, vmid: int | None = None) -> int:
        """Retrieve the next available VMID from the Proxmox cluster."""
        if vmid:
            try:
                response = await self.get(path="/cluster/nextid", model=models.VMID, vmid=vmid)
            except httpx.HTTPStatusError:
                return 0
            else:
                return vmid
        response = await self.get(path="/cluster/nextid", model=models.VMID)
        return response.root

    async def _get_task_status(self, node: str, upid: str) -> models.ProxmoxTaskStatus:
        """Retrieve the status of a specific task on a Proxmox node."""
        return await self.get(f"/nodes/{node}/tasks/{upid}/status", model=models.ProxmoxTaskStatus)

    async def wait_for_task(self, task: models.Task, interval: int = 3, timeout: int = 900) -> None:
        """Wait for a Proxmox task to complete, polling its status at regular intervals."""
        _task = await self._get_task_status(task.node, task.upid)
        start_time = time.time()
        while _task.status == TaskStatus.RUNNING:
            await asyncio.sleep(interval)
            if (time.time() - start_time) > timeout:
                msg = f"Task {task.upid} timed out after {timeout}s"
                raise TimeoutError(msg)
            _task = await self._get_task_status(task.node, task.upid)
        _task.raise_for_status()

    async def create_fabric(self, lan_network: ipaddress.IPv4Network) -> None:
        params = {
            "id": "OrbitLab",
            "protocol": "ospf",
            "area": 0,
            "ip_prefix": str(lan_network)
        }
        await self.create("/cluster/sdn/fabrics/fabric", model=None, **params)
        await self.set(path="/cluster/sdn")

    async def add_node_to_fabric(self, node: str, address: ipaddress.IPv4Address) -> None:
        params = {
            "protocol": "ospf",
            "node_id": node,
            "interfaces": "name=vmbr0",
            "ip": str(address)
        }
        await self.create("/cluster/sdn/fabrics/node/OrbitLab", model=None, **params)
        await self.set(path="/cluster/sdn")

    async def get_compute_resource(self, vmid: int) -> models.ProxmoxComputeResource:
        resources = await self.get(path="/cluster/resources", model=models.ProxmoxComputeResources, type="vm")
        return resources.get_resource(vmid=vmid)

    async def get_vm_root_volume_id(self, vmid: int) -> str:
        resource = await self.get_compute_resource(vmid=vmid)
        config = await self.get(path=f"/nodes/{resource.node}/qemu/{vmid}/config", model=models.QemuConfig)
        return config.root_volume_id

    async def list_storages_for_node(self, node: str, content_type: StorageContentType | None = None) -> list[str]:
        """List all storage names for a given node and optional content type."""
        params = {"enabled": "1"}
        if content_type:
            params["content"] = str(content_type)
        storages = await self.get(f"/nodes/{node}/storage", model=models.ProxmoxStorages, **params)
        return storages.list_all()

    async def create_connection(self, node: str = "") -> RemoteExecution:
        """Create a remote execution connection to a Proxmox node."""
        if not node:
            node = self.__node__
        proxy = await self.create(f"/nodes/{node}/termproxy", model=models.ProxmoxTermProxy)
        return RemoteExecution(
            node=node,
            config=RemoteExecutionConfig(
                websocket_url=await self.http_config.generate_websocket_url(node=node, port=proxy.port, ticket=proxy.ticket),
                user=proxy.user,
                ticket=proxy.ticket,
                cookie=self.__session__.cookies["PVEAuthCookie"],
            ),
        )

    async def get_terminal_websocket(self, vmid: int) -> websocket.ClientConnection:
        """Create and return a WebSocket connection to the terminal of a specified VM or LXC container."""
        resource = await self.get_compute_resource(vmid=vmid)
        proxy = await self.create(f"/nodes/{resource.node}/{resource.type}/{vmid}/termproxy", model=models.ProxmoxTermProxy)
        cookie = self.__session__.cookies["PVEAuthCookie"]
        ssl_context = await RemoteExecution.create_default_context()
        terminal_websocket = await websocket.connect(
            await self.http_config.generate_websocket_url(node=resource.node, port=proxy.port, ticket=proxy.ticket, resource=resource),
            additional_headers={"Cookie": f"PVEAuthCookie={cookie}"},
            ssl=ssl_context,
        )
        await terminal_websocket.send(f"{proxy.user}:{proxy.ticket}\n")
        return terminal_websocket

    async def configure_frr_on_node(self, node: str) -> None:
        async with await self.create_connection(node=node) as connection:
            await connection.run_command("apt update -y")
            await connection.run_command("apt install -y frr frr-pythontools")
            await connection.run_command("sed -i 's|bgpd=no|bgpd=yes|' /etc/frr/daemons")
            await connection.run_command("systemctl enable frr && systemctl restart frr")   

    async def list_nodes(self) -> list[models.ProxmoxNode]:
        status = await self.get(path="/cluster/status", model=models.ProxmoxClusterStatus)
        return status.list_nodes()

    async def describe_node(self, node: str) -> models.ProxmoxNode:
        status = await self.get(path="/cluster/status", model=models.ProxmoxClusterStatus)
        return status.get_node(node=node)

    async def get_node_proxmox_version(self, node: str) -> str:
        data: dict = await self.get(path=f"/nodes/{node}/version", model=None)
        return data["version"]

    async def get_vmbr0_for_node(self, node: str) -> models.ProxmoxBridge:
        bridges = await self.get(path=f"/nodes/{node}/network", model=models.ProxmoxBridges, type="bridge")
        return bridges.get_vmbr0()

    async def list_vnets(self) -> models.ProxmoxVnets:
        params = {"pending": 1, "running": 1}
        return await self.get(path="/cluster/sdn/vnets", model=models.ProxmoxVnets, **params)

    async def create_instance(self, instance_type: InstanceType, params: dict, node: str = "") -> None:
        if not node:
            node = self.__node__
        task = await self.create(path=f"/nodes/{node}/{instance_type}", model=models.Task, **params)
        await self.wait_for_task(task=task)

    async def list_compute(self) -> models.ProxmoxComputeResources:
        return await self.get(path="/cluster/resources", model=models.ProxmoxComputeResources, type="vm")

    async def get_agent_enabled(self, vmid: int) -> bool:
        resource = await self.get_compute_resource(vmid=int(vmid))
        config = await self.get(f"/nodes/{resource.node}/qemu/{vmid}/config", model=models.QemuConfig)
        return config.agent_enabled

    async def wait_for_agent(self, vmid: int) -> None:
        """Wait for the guest agent on a virtual machine to become available."""
        resource = await self.get_compute_resource(vmid=int(vmid))
        async with asyncio.timeout(30):
            while True:
                try:
                    await self.create(path=f"/nodes/{resource.node}/qemu/{vmid}/agent/ping", model=None)
                except httpx.HTTPStatusError:
                    await asyncio.sleep(2)
                else:
                    break

    async def agent_write_file(self, vmid: int, source: Path, destination: Path) -> None:
        resource = await self.get_compute_resource(vmid=vmid)
        params = {"content": source.read_text(), "file": str(destination)}
        await self.create(path=f"/nodes/{resource.node}/qemu/{vmid}/agent/file-write", model=None, **params)

    async def agent_execute_script(self, vmid: int, script: str) -> models.AgentExecStatus:
        resource = await self.get_compute_resource(vmid=vmid)
        filename = f"/tmp/{hashlib.md5(script.encode()).hexdigest()}.sh"  # noqa: S324
        script_template = Template("#!/bin/bash\nset -euo pipefail\n$content\nrm -f $filename\n")

        await self.create(
            path=f"/nodes/{resource.node}/qemu/{vmid}/agent/file-write",
            model=None,
            content=script_template.safe_substitute(content=script, filename=filename),
            file=filename,
        )

        pid_response = await self.create(
            path=f"/nodes/{resource.node}/qemu/{vmid}/agent/exec",
            model=models.AgentExecPid,
            command=["bash", filename],
        )
        
        @backoff.on_predicate(
            lambda: backoff.fibo(max_value=15),
            max_time=300,
            on_backoff=lambda x: print("backoff: ", x),
            on_giveup=lambda x: print("giveup: ", x),
        )
        async def _wait() -> models.AgentExecStatus:
            return await self.get(
                path=f"/nodes/{resource.node}/qemu/{vmid}/agent/exec-status",
                model=models.AgentExecStatus,
                pid=pid_response.pid,
            )
        
        return await _wait()

    @backoff.on_predicate(backoff.fibo, max_time=30, max_tries=5)
    async def get_ipv4_address(self, vmid: int, device: str = "eth0") -> ipaddress.IPv4Interface | None:
        """Retrieve the private IPv4 address for the given LXC VMID."""
        resource = await self.get_compute_resource(vmid=vmid)

        if resource.type == "qemu":
            if resource.status == "stopped":
                await self.wait_for_agent(vmid=vmid)
            try:
                interfaces = await self.get(
                    path=f"/nodes/{resource.node}/qemu/{vmid}/agent/network-get-interfaces",
                    model=models.VMInterfaces,
                )
            except httpx.HTTPStatusError:
                return None
            else:
                return interfaces.get_ipv4(device=device)
        else:
            interfaces = await self.get(f"/nodes/{resource.node}/lxc/{vmid}/interfaces", model=models.LXCInterfaces)
        return interfaces.get_ipv4(device=device)

    async def resize_disk(self, vmid: int, disk_size: int, disk_id: str) -> None:
        resource = await self.get_compute_resource(vmid=vmid)
        task = await self.set(
            path=f"/nodes/{resource.node}/{resource.type}/{vmid}/resize",
            model=models.Task,
            disk=disk_id,
            size=f"{disk_size}G",
        )
        await self.wait_for_task(task=task)

    async def get_status(self, vmid: int) -> Literal["stopped", "running"]:
        resources = await self.list_compute()
        try:
            resource = resources.get_resource(vmid=vmid)
        except StopIteration:
            return "stopped"
        response = await self.get(f"/nodes/{resource.node}/{resource.type}/{vmid}/status/current", model=models.InstanceStatus)
        return response.status

    async def start(self, vmid: int) -> None:
        resource = await self.get_compute_resource(vmid=vmid)
        task = await self.create(path=f"/nodes/{resource.node}/{resource.type}/{vmid}/status/start", model=models.Task)
        await self.wait_for_task(task=task)

    async def stop(self, vmid: int) -> None:
        resource = await self.get_compute_resource(vmid=vmid)
        task = await self.create(path=f"/nodes/{resource.node}/{resource.type}/{vmid}/status/stop", model=models.Task)
        await self.wait_for_task(task=task)

    async def shutdown(self, vmid: int) -> None:
        resource = await self.get_compute_resource(vmid=vmid)
        task = await self.create(path=f"/nodes/{resource.node}/{resource.type}/{vmid}/status/shutdown", model=models.Task)
        await self.wait_for_task(task=task)

    async def reboot(self, vmid: int) -> None:
        resource = await self.get_compute_resource(vmid=vmid)
        task = await self.create(path=f"/nodes/{resource.node}/{resource.type}/{vmid}/status/reboot", model=models.Task)
        await self.wait_for_task(task=task)

    async def terminate(self, vmid: int) -> None:
        resources = await self.get(path="/cluster/resources", model=models.ProxmoxComputeResources, type="vm")
        try:
            resource = resources.get_resource(vmid=vmid)
        except StopIteration:
            return
        if await self.get_status(vmid=vmid) == "running":
            task = await self.create(path=f"/nodes/{resource.node}/{resource.type}/{vmid}/status/shutdown", model=models.Task)
            await self.wait_for_task(task=task)
        params = {"destroy-unreferenced-disks": 1, "purge": 1}
        task = await self.delete(path=f"/nodes/{resource.node}/{resource.type}/{vmid}", model=models.Task, **params)
        await self.wait_for_task(task=task)

    async def move_disk(self, from_vmid: int, to_vmid: int, disk_id: str, target_disk_id: str = "") -> None:
        if not target_disk_id:
            target_disk_id = disk_id

        resource = await self.get_compute_resource(vmid=from_vmid)
        params = {"disk": "scsi1", "target-disk": "scsi1", "target-vmid": to_vmid}
        task = await self.create(path=f"/nodes/{resource.node}/qemu/{from_vmid}/move_disk", model=models.Task, **params)
        await self.wait_for_task(task=task)

    async def attach_redis_socket_file(self, vmid: int) -> None:
        async with await self.create_connection() as connection:
            await connection.run_command(command=f"pct set {vmid} -mp0 /run/redis,mp=/var/redis")

    async def list_pools(self) -> models.ProxmoxPools:
        return await self.get(f"/pools", model=models.ProxmoxPools)

    async def pool_exists(self, pool_id: str) -> bool:
        pools = await self.list_pools()
        return bool(pools.get_pool_by_id(pool_id=pool_id))

    async def create_pool(self, pool_id: str, alias: str) -> None:
        if await self.pool_exists(pool_id=pool_id):
            return
        params = {"poolid": pool_id, "comment": alias}
        await self.create("/pools", model=None, **params)

    async def delete_pool(self, pool_id: str) -> None:
        if await self.pool_exists(pool_id=pool_id):
            await self.delete(f"/pools/{pool_id}", model=None)

    async def get_infrastructure_appliances(self) -> models.OrbitLabAppliances:
        async with httpx.AsyncClient() as client:
            response = await client.get("https://raw.githubusercontent.com/OrbitLab-OSS/Appliances/refs/heads/main/metadata/appliances.json")
            response.raise_for_status()
        return models.OrbitLabAppliances.model_validate(response.json())

    async def get_vendored_images(self) -> models.VendoredImages:
        async with httpx.AsyncClient() as client:
            response = await client.get("https://raw.githubusercontent.com/OrbitLab-OSS/VendoredImages/refs/heads/main/metadata/images.json")
        response.raise_for_status()
        return models.VendoredImages.model_validate(response.json())

    async def list_appliances(self, appliance_type: ApplianceType | None = None) -> list[models.ApplianceInfo]:
        """List available LXC appliances on the specified Proxmox node."""
        appliances = await self.get(f"/nodes/{self.__node__}/aplinfo", model=models.Appliances)
        match appliance_type:
            case ApplianceType.SYSTEM:
                return appliances.system_appliances()
            case ApplianceType.TURNKEY:
                return appliances.turnkey_appliances()
            case _:
                return appliances.root

    async def list_stored_appliances(self, node: str, storage: str) -> models.StoredAppliances:
        """List stored appliance templates in the specified storage on a Proxmox node."""
        params = {"content": "vztmpl"}
        return await self.get(f"/nodes/{node}/storage/{storage}/content", model=models.StoredAppliances, **params)

    async def list_stored_images(self, node: str, storage: str) -> models.StoredImages:
        """List stored images in the specified storage on a Proxmox node."""
        params = {"content": "import"}
        return await self.get(f"/nodes/{node}/storage/{storage}/content", model=models.StoredImages, **params)

    async def volume_id_exists(self, node: str, storage: str, volume_id: str) -> bool:
        content_list: list[dict] = await self.get(f"/nodes/{node}/storage/{storage}/content", model=None)
        return bool(next(iter(item for item in content_list if item["volid"] == volume_id), None))

    async def get_volume_id(self, node: str, storage: str, filename: str) -> str:
        stored_images = await self.list_stored_images(node=node, storage=storage)
        return stored_images.get_image(filename=filename).volid

    async def _delete_template(self, node: str, storage: str, volume_id: str) -> None:
        if volume_id:
            task = await self.delete(path=f"/nodes/{node}/storage/{storage}/content/{volume_id}", model=models.Task)
            await self.wait_for_task(task=task)

    async def delete_appliance(self, node: str, storage: str, volume_id: str) -> None:
        """Delete a custom appliance from the specified Proxmox storage."""
        await self._delete_template(node=node, storage=storage, volume_id=volume_id)

    async def delete_image(self, node: str, storage: str, volume_id: str) -> None:
        """Delete a custom image from the specified Proxmox storage."""
        await self._delete_template(node=node, storage=storage, volume_id=volume_id)

    async def download_proxmox_managed_appliance(self, node: str, storage: str, template: str) -> str:
        task = await self.create(
            path=f"/nodes/{node}/aplinfo",
            model=models.Task,
            storage=storage,
            template=template,
        )
        await self.wait_for_task(task=task)
        stored = await self.list_stored_appliances(node=node, storage=storage)
        return stored.get_appliance(filename=template).volid

    async def oci_registry_pull(self, node: str, storage: str, template: str) -> str:
        task = await self.create(
            path=f"/nodes/{node}/storage/{storage}/oci-registry-pull",
            model=models.Task,
            reference=template,
        )
        await self.wait_for_task(task=task)
        stored = await self.list_stored_appliances(node=node, storage=storage)
        filename = template.rsplit("/", 1)[-1].replace(":", "_")
        return stored.get_appliance(filename=f"{filename}.tar").volid

    async def download_appliance_from_url(self, node: str, storage: str, params: dict) -> str:
        task = await self.create(path=f"/nodes/{node}/storage/{storage}/download-url", model=models.Task, **params)
        await self.wait_for_task(task=task)
        stored = await self.list_stored_appliances(node=node, storage=storage)
        return stored.get_appliance(filename=params["filename"]).volid

    async def download_image(self, node: str, storage: str, params: dict) -> str:
        task = await self.create(path=f"/nodes/{node}/storage/{storage}/download-url", model=models.Task, **params)
        await self.wait_for_task(task=task)
        stored = await self.list_stored_images(node=node, storage=storage)
        return stored.get_image(filename=params["filename"]).volid

    async def download_infrastructure_appliance(self, storage: str, params: dict, node: str = "") -> str:
        if not node:
            node = self.__node__

        task = await self.create(path=f"/nodes/{node}/storage/{storage}/download-url", model=models.Task, **params)
        await self.wait_for_task(task=task)
        filename: str = params["filename"]
        if filename.endswith(".qcow2") or filename.endswith(".raw"):
            stored = await self.list_stored_images(node=node, storage=storage)
            return stored.get_image(filename=filename).volid
        else:
            stored = await self.list_stored_appliances(node=node, storage=storage)
            return stored.get_appliance(filename=filename).volid

    async def generate_image(self, vmid: int, image_id: str, disk_storage: str, image_storage: str) -> str:
        """Generate a QCOW2 image from a virtual machine disk and upload it to storage."""
        volume_id = await self.get_vm_root_volume_id(vmid=vmid)
        resource = await self.get_compute_resource(vmid=vmid)
        volume = await self.get(
            path=f"/nodes/{resource.node}/storage/{disk_storage}/content/{volume_id}",
            model=models.VolumeContentInfo,
        )
        temp_name = hashlib.sha256(image_id.encode()).hexdigest()
        command = Template("qemu-img convert -p -O qcow2 $path /var/tmp/pveupload-$temp_name").safe_substitute(path=volume.path, temp_name=temp_name)
        async with await self.create_connection(node=resource.node) as connection:
            await connection.run_command(command=command, check_output=True)

        params = {
            "content": "import",
            "filename": f"{image_id}.qcow2",
            "tmpfilename": f"/var/tmp/pveupload-{temp_name}",
        }
        task = await self.create(
            path=f"/nodes/{resource.node}/storage/{image_storage}/upload",
            model=models.Task,
            **params,
        )
        await self.wait_for_task(task=task)
        stored_images = await self.list_stored_images(node=resource.node, storage=image_storage)
        return stored_images.get_image(filename=params["filename"]).volid

    async def generate_appliance(self, vmid: int, appliance_id: str, storage: str) -> str:
        resource = await self.get_compute_resource(vmid=vmid)
        params = {"vmid": vmid, "quiet": 1, "compress": "gzip", "dumpdir": "/var/tmp"}
        task = await self.create(path=f"/nodes/{resource.node}/vzdump", model=models.Task, **params)
        await self.wait_for_task(task=task)

        temp_name = hashlib.sha256(appliance_id.encode()).hexdigest()
        command = f"mv /var/tmp/vzdump-lxc-{vmid}-*.tar.gz /var/tmp/pveupload-{temp_name}"
        async with await self.create_connection(node=resource.node) as connection:
            await connection.run_command(command=command)

        params = {
            "content": "vztmpl",
            "filename": f"{appliance_id}.tar.gz",
            "tmpfilename": f"/var/tmp/pveupload-{temp_name}",
        }
        task = await self.create(path=f"/nodes/{resource.node}/storage/{storage}/upload", model=models.Task, **params)
        await self.wait_for_task(task=task)
        
        stored = await self.list_stored_appliances(node=resource.node, storage=storage)
        return stored.get_appliance(filename=params["filename"]).volid

    async def get_mtu(self) -> int:
        """Get the MTU (Maximum Transmission Unit) of the vmbr0 network interface."""
        async with await self.create_connection(node=self.__node__) as connection:
            output = await connection.run_command(command="cat /sys/class/net/vmbr0/mtu", check_output=True)
        return int(output)

    async def list_controllers(self) -> models.SDNControllers:
        return await self.get(path="/cluster/sdn/controllers", model=models.SDNControllers, running=1)

    async def list_sectors(self) -> list[models.DescribeSector]:
        """List existing Sectors."""
        sectors = []
        vnets = await self.list_vnets()
        for vnet in vnets.root:
            if not vnet.name.startswith("olvn"):
                continue
            subnets = await self.get(path=f"/cluster/sdn/vnets/{vnet.name}/subnets", model=models.Subnets)
            sector_network = subnets.get_cidr()
            bridges = await self.get(path=f"/nodes/{self.__node__}/sdn/zones/{vnet.name}/bridges", model=models.ZoneBridges)
            gateway_vmid = 0
            assignments = {}
            for vm in bridges.get_vms():
                if not vm.vmid:
                    continue
                instance = await self.get(path=f"/nodes/{self.__node__}/lxc/{vm.vmid}/config", model=models.ComputeConfig)
                if address := instance.get_sector_address(sector_network):
                    assignments[vm.vmid] = address
            sectors.append(
                models.DescribeSector(
                    vnet=vnet,
                    subnets=subnets,
                    gateway_vmid=gateway_vmid,
                    assignments=assignments,
                ),
            )
        return sectors

    async def create_backplane(self, backplane: BackplaneConfig) -> None:
        """Create the backplane network configuration."""
        controller_params = {
            "controller": backplane.controller.id,
            "type": "evpn",
            "asn": backplane.controller.asn,
            "peers": backplane.controller.peer_list,
        }
        await self.create(path="/cluster/sdn/controllers", model=None, **controller_params)
        zone_params = {
            "type": "evpn",
            "zone": backplane.zone_id,
            "controller": backplane.controller.id,
            "vrf-vxlan": backplane.zone_tag,
            "advertise-subnets": 1,
            "mtu": backplane.mtu,
            "ipam": "pve",
            "exitnodes": ",".join(backplane.exit_nodes),
        }
        await self.create(path="/cluster/sdn/zones", model=None, **zone_params)
        vnet_params = {
            "vnet": backplane.vnet_id,
            "zone": backplane.zone_id,
            "alias": "OrbitLab Backplane",
            "tag": backplane.vnet_tag,
        }
        await self.create("/cluster/sdn/vnets", model=None, **vnet_params)
        subnet_params = {
            "subnet": backplane.cidr_block.with_prefixlen,
            "gateway": str(backplane.default_gateway.ip),
            "type": "subnet",
            "snat": 1,
        }
        await self.create(f"/cluster/sdn/vnets/{backplane.vnet_id}/subnets", model=None, **subnet_params)
        await self.set(path="/cluster/sdn")

    async def list_vnets(self) -> models.VNetList:
        """List all virtual networks (VNets) in the cluster."""
        return await self.get(path="/cluster/sdn/vnets", model=models.VNetList)

    async def list_attached(self, sector_id: str) -> list[models.AttachedInstances]:
        """List all compute instances attached to a specific sector network."""
        bridges = await self.get(path=f"/nodes/{self.__node__}/sdn/zones/{sector_id}/bridges", model=models.ZoneBridges)
        instances = []
        for vm in bridges.get_vms():
            if not vm.vmid:
                continue
            if vm.compute_type == "qemu":
                instances.append(models.AttachedInstances(vmid=vm.vmid, compute_type="qemu"))
                continue
            instance = await self.get(path=f"/nodes/{self.__node__}/lxc/{vm.vmid}/config", model=models.ComputeConfig)
            if not instance.is_orbitlab_infra:
                instances.append(models.AttachedInstances(vmid=vm.vmid, compute_type="lxc"))
        return instances
