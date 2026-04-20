"""OrbitLab XTerm.js Implementation."""

from string import Template
from typing import Final

import reflex as rx

XTERM_CONSTANTS = Template(
"""
  const ref = useRef(null);
  const terminalRef = useRef(null);
  const socketRef = useRef(null);
  const socketUrl = `${$socket_url}`;
  const termOptions = {
    rows: 34,
    cols: 197,
    fontFamily: "Fira Code, courier-new, courier, monospace",
    cursorBlink: true
  };
  const fitAddon = new FitAddon();
""",
)
SOCKET_HOOKS: Final = """
  useEffect(() => {
    if (!ref.current || !socketUrl) return;
    if (terminalRef.current) return;
    let term = new Terminal(termOptions)
    term.open(ref.current);
    terminalRef.current = term;
    let websocket = new WebSocket(`${socketUrl}`)
    websocket.binaryType = "arraybuffer";
    websocket.onopen = () => {
      term.loadAddon(fitAddon);
      term.loadAddon(new WebglAddon());
      fitAddon.fit();
    }
    websocket.onmessage = (event) => {
      term.write(new Uint8Array(event.data));
    };
    term.onResize(function (size) {
      websocket.send("1:" + size.cols + ":" + size.rows + ":");
    });
    term.onData((data) => {
      websocket.send(`0:${data.length}:${data}`);
    });
    window.addEventListener('resize', function() {
      fitAddon.fit();
    });
    socketRef.current = websocket;
  }, [socketUrl])
"""

class Xterm(rx.Component):
    """A Reflex component that wraps the xterm.js library for terminal functionality."""
    library = "@xterm/xterm@5.5.0"
    tag = "Terminal"

    def add_imports(self) -> dict:
        """Add required imports for the xterm component."""
        return {
          "@xterm/addon-fit": rx.ImportVar(tag="FitAddon", is_default=False),
          "@xterm/addon-webgl": rx.ImportVar(tag="WebglAddon", is_default=False),
          "": "@xterm/xterm/css/xterm.css",
        }

    def add_hooks(self) -> list:
        """Add React hooks for terminal functionality."""
        return [
            rx.Var(
                XTERM_CONSTANTS.safe_substitute(socket_url=self.socket_url),
                _var_data=rx.vars.base.VarData(
                    imports={"react": ["useRef"]},
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
            class_name="w-full h-full shrink grow",
        ).render()
        rendered["props"].extend(["ref:ref"])
        return rendered

    socket_url: rx.Var[str]

Terminal = Xterm.create
