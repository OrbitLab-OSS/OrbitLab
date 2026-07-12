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
""",
)
SOCKET_HOOKS: Final = r"""
  useEffect(() => {
    if (!ref.current || !socketUrl) return;
    if (terminalRef.current) return;
    
    let term = new Terminal({
      fontFamily: "Fira Code, courier-new, courier, monospace",
      cursorBlink: true,
      reflowCursorLine: false,
      scrollback: 1000,
    });
    
    const fitAddon = new FitAddon();
    term.loadAddon(fitAddon);
    term.open(ref.current);
    
    terminalRef.current = term;
    
    const websocket = new WebSocket(`${socketUrl}`)
    websocket.binaryType = "arraybuffer";
    socketRef.current = websocket;
    
    let isOpen = false;
    let lastCols = 0;
    let lastRows = 0;
    let resizeFrame = null;
    
    function sendResize() {
      if (!isOpen) return;

      const box = ref.current.getBoundingClientRect();

      fitAddon.fit();

      const cols = term.cols;
      const rows = term.rows;

      if (!cols || !rows) return;

      websocket.send(`1:${cols}:${rows}:`);
    }
    
    function scheduleResize() {
      if (resizeFrame !== null) {
        cancelAnimationFrame(resizeFrame);
      }

      resizeFrame = requestAnimationFrame(() => {
        resizeFrame = requestAnimationFrame(() => {
          resizeFrame = null;
          sendResize();
        });
      });
    }
    
    websocket.onopen = async () => {
      isOpen = true;
      
      if (document.fonts?.ready) {
        await document.fonts.ready;
      }
      
      scheduleResize();
    };
    
    websocket.onmessage = (event) => {
      term.write(new Uint8Array(event.data));
    };
    
    term.onResize(({ cols, rows }) => {
      if (!isOpen) return;
      if (!cols || !rows) return;
      if (cols === lastCols && rows === lastRows) return;

      lastCols = cols;
      lastRows = rows;

      websocket.send(`1:${cols}:${rows}:`);
    });
    
    term.onData((data) => {
      websocket.send(`0:${data.length}:${data}`);
    });
    
    const resizeObserver = new ResizeObserver(() => {
      scheduleResize();
    });
    
    resizeObserver.observe(ref.current);
    
    window.addEventListener("resize", scheduleResize);
    
    scheduleResize();
    
    return () => {
      window.removeEventListener("resize", scheduleResize);
      resizeObserver.disconnect();

      if (resizeFrame !== null) {
        cancelAnimationFrame(resizeFrame);
      }

      websocket.close();
      term.dispose();

      socketRef.current = null;
      terminalRef.current = null;
    };
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
            class_name="h-[85vh] min-h-0 w-full",
        ).render()
        rendered["props"].extend(["ref:ref"])
        return rendered

    socket_url: rx.Var[str]

Terminal = Xterm.create
