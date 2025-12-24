"""CodeMirror Editor."""
from typing import Literal, NotRequired, Self, TypedDict, Unpack, overload

import reflex as rx

type Languages = Literal["shell"]


class CodeMirrorProps(TypedDict):
    """CodeMirror Editor Props."""

    value: rx.Var[str]
    language: Languages
    on_change: rx.EventHandler[rx.event.passthrough_event_spec(str)] | rx.event.EventCallback
    theme: NotRequired[rx.Var[Literal["light", "dark"]]]


class CodeMirror(rx.Component):
    """@monaco-editor/react Library component."""

    # The React library to wrap.
    library = "@uiw/react-codemirror@4.25.3"

    lib_dependencies: list[str] = [  # noqa: RUF012
        "@codemirror/legacy-modes@6.5.2",
        "@codemirror/language@6.11.3"
        "@replit/codemirror-indentation-markers@6.5.3",
    ]

    tag = "CodeMirror"

    is_default = True

    def add_imports(self) -> dict[str, rx.ImportVar]:
        """Add all imports."""
        return {
            "@codemirror/language": rx.ImportVar(tag="StreamLanguage", is_default=False),
            "@replit/codemirror-indentation-markers": rx.ImportVar(tag="indentationMarkers", is_default=False),
            **self.__handle_languages__(handle_for="imports"),
        }

    def add_hooks(self) -> list[rx.Var]:
        """Add reflex hooks."""
        set_default = rx.Var(
            (
                f"const reflexStateValue = {self.value};"
                "const [ value, setValue ] = useState(reflexStateValue);"
                """useEffect(() => {
                    setValue(reflexStateValue);
                }, [reflexStateValue])"""
            ),
            _var_data=rx.vars.VarData(
                imports={"react": ["useState", "useEffect"]},
                position=rx.constants.Hooks.HookPosition.PRE_TRIGGER,
            ),
        )
        return [set_default]

    @overload
    def __handle_languages__(self, handle_for: Literal["imports"]) -> dict[str, rx.ImportVar]: ...

    @overload
    def __handle_languages__(self, handle_for: Literal["extensions"]) -> list[rx.vars.FunctionStringVar]: ...

    def __handle_languages__(self, handle_for: Literal["extensions", "imports"]):
        """Handle language-specific imports and extensions based on the specified language."""
        extensions = [rx.vars.FunctionStringVar("indentationMarkers()")]
        match self.language:
            case "shell":
                extensions.append(rx.vars.FunctionStringVar("StreamLanguage.define(shell)"))
                language_import = {
                    "@codemirror/legacy-modes": rx.ImportVar(tag="shell", is_default=False, package_path="/mode/shell"),
                }
        if handle_for == "extensions":
            return extensions
        return language_import

    @classmethod
    def create(cls, **props: Unpack[CodeMirrorProps]) -> Self:
        """Create a CodeMirror component instance."""
        props.setdefault("theme", rx.color_mode_cond(light="light", dark="dark"))
        return super().create(**props)

    def render(self) -> dict:
        """Render the CodeMirror component with appropriate extensions and properties."""
        tag = self._render({
            "value": rx.vars.FunctionStringVar("value"),
            "extensions": self.__handle_languages__(handle_for="extensions"),
            "theme": self.theme,
        })
        rendered_dict = dict(
            tag.set(
                children=[child.render() for child in self.children],
            ),
        )
        if on_change := next(iter([prop for prop in rendered_dict["props"] if prop.startswith("onChange:")]), None):
            rendered_dict["props"].remove(on_change)
            on_change = f"{on_change[:-2]},setValue(_ev_0)))"
            rendered_dict["props"].append(on_change)
        return rendered_dict

    value: rx.Var[str]
    language: Literal["shell"]
    theme: rx.Var[Literal["light", "dark"]]

    on_change: rx.EventHandler[rx.event.passthrough_event_spec(str)]


Editor = CodeMirror.create
