"""OrbitLab XTerm.js Implementation."""

from string import Template
from typing import Final

import reflex as rx

XTERM_CONSTANTS = Template(
"""
  const ref = useRef(null);
  const [ terminal, setTerminal ] = useState(null);
  const [ socket, setSocket ] = useState(null);
  const socketUrl = `${$socket_url}`;
  const termOptions = {
    rows: 34,
    cols: 197,
    fontFamily: "Fira Code, courier-new, courier, monospace",
    cursorBlink: true
  };
""",
)
SOCKET_HOOKS: Final = """
  useEffect(() => {
    if (!terminal && ref && socketUrl) {
      let term = new Terminal(termOptions);
      term.open(ref.current);
      term.onResize(function (size) {
        console.log("onResize", size);
        socket.send("1:" + size.cols + ":" + size.rows + ":");
      });
      setTerminal(term);
    }
    if (terminal && !socket) {
      let websocket = new WebSocket(`${socketUrl}`)
      websocket.binaryType = "arraybuffer";
      websocket.onmessage = (event) => {
        terminal.write(new Uint8Array(event.data));
      };
      terminal.onData((data) => {
        websocket.send(`0:${data.length}:${data}`);
      });
      setSocket(websocket)
    }
  }, [socketUrl, terminal, ref, socket])

  function runTerminal() {
    socket.onmessage = (event) => {
      terminal.write(new Uint8Array(event.data));
    };

    terminal.onData((data) => {
      socket.send(`0:${data.length}:${data}`);
    });
  }
"""

class Xterm(rx.Component):
    """A Reflex component that wraps the xterm.js library for terminal functionality."""
    library = "@xterm/xterm@5.5.0"
    tag = "Terminal"

    def add_imports(self) -> dict:
        """Add required imports for the xterm component."""
        return {"": "@xterm/xterm/css/xterm.css"}

    def add_hooks(self) -> list:
        """Add React hooks for terminal functionality."""
        return [
            rx.Var(
                XTERM_CONSTANTS.safe_substitute(socket_url=self.socket_url),
                _var_data=rx.vars.base.VarData(
                    imports={"react": ["useRef", "useState"]},
                    position=rx.constants.Hooks.HookPosition.PRE_TRIGGER,
                ),
            ),
            rx.Var(
                SOCKET_HOOKS,
                _var_data=rx.vars.base.VarData(
                    imports={"react": ["useEffect"]},
                    position=rx.constants.Hooks.HookPosition.PRE_TRIGGER,
                ),
            ),
        ]

    def render(self) -> dict:
        """Render the terminal component as a React element."""
        rendered = rx.el.div(
            rx.el.div(
                rx.el.div(
                    rx.el.strong(class_name="mr-auto"), rx.el.small(),
                ),
                class_name="toast-header",
            ),
            rx.el.div(
                class_name="toast-body",
                id=rx.Var.create("toastMessage"),
            ),
            class_name="w-full h-full overflow-hidden",
        ).render()
        rendered["props"].extend(["ref:ref"])
        return rendered

    socket_url: rx.Var[str]

Terminal = Xterm.create
