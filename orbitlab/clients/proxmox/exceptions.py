"""Exception classes for Proxmox."""


from typing import Final


class PVECommandError(Exception):
    """Raised when a pvesh command fails."""

    def __init__(self, cmd: list[str], stderr: str) -> None:
        """Initialize PVECommandError with the command and its stderr output.

        Args:
            cmd (str): The command that failed.
            stderr (str): The standard error output from the command.
        """
        super().__init__(f"PVESH command failed: {cmd}\n{stderr}")
        self.cmd = cmd
        self.stderr = stderr


class HTTPConfigError(Exception):
    """Raised when the HTTP configuration is invalid."""

    def __init__(self, msg: str) -> None:
        """Initialize HTTPConfigError with an error message.

        Args:
            msg (str): The error message describing the configuration issue.
        """
        super().__init__(msg)
        self.msg = msg


class ApplianceNotFoundError(Exception):
    def __init__(self, appliance_id: str):
        super().__init__(f"Appliance '{appliance_id}' not found.")
        self.appliance_id = appliance_id


class ProxmoxClientError(Exception):
    EVPNControllerExists: Final = "EVPNControllerExists"

    def __init__(self, err: str, msg: str) -> None:
        super().__init__(f"{err}: {msg}")
        self.err = err
        self.msg = msg
