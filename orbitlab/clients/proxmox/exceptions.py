"""Exception classes for Proxmox."""

class PVECommandError(Exception):
    """Raised when a pvesh command fails."""
    def __init__(self, cmd: str, stderr: str) -> None:
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
