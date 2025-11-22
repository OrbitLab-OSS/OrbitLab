from typing import Literal, Self, TypeAlias, overload
import reflex as rx


Languages: TypeAlias = Literal["shell"]


class CodeMirror(rx.Component):
    """@monaco-editor/react Library component."""

    # The React library to wrap.
    library = "@uiw/react-codemirror@4.25.3"

    lib_dependencies: list[str] = [
        "@codemirror/legacy-modes@6.5.2",
        "@codemirror/language@6.11.3"
        "codemirror-lang-hcl@0.1.0",
        "@replit/codemirror-indentation-markers@6.5.3"
    ]

    tag = "CodeMirror"

    is_default = True

    def add_imports(self):
        langauge_import = self.__handle_languages__(handle_for="imports")
        return {
            "@codemirror/language": rx.ImportVar(tag="StreamLanguage", is_default=False),
            "@replit/codemirror-indentation-markers": rx.ImportVar(tag="indentationMarkers", is_default=False),
            **langauge_import,
        }
    
    @overload
    def __handle_languages__(self, handle_for: Literal["imports"]) -> dict[str, rx.ImportVar]: ...

    @overload
    def __handle_languages__(self, handle_for: Literal["extensions"]) -> list[rx.vars.FunctionStringVar]: ...
    
    def __handle_languages__(self, handle_for: Literal["extensions", "imports"]):
        extensions = [
            rx.vars.FunctionStringVar("indentationMarkers()")
        ]
        match self.language:
            case "shell":
                extensions.append(rx.vars.FunctionStringVar("StreamLanguage.define(shell)"))
                language_import = {
                    "@codemirror/legacy-modes": rx.ImportVar(tag="shell", is_default=False, package_path="/mode/shell")
                }
            case "go":
                extensions.append(rx.vars.FunctionStringVar("StreamLanguage.define(go)"))
                language_import = {
                    "@codemirror/legacy-modes": rx.ImportVar(tag="go", is_default=False, package_path="/mode/go")
                }
            case "hcl":
                extensions.append(rx.vars.FunctionStringVar("hcl()"))
                language_import = {
                    "codemirror-lang-hcl": rx.ImportVar(tag="hcl", is_default=False)
                }
        if handle_for == "extensions":
            return extensions
        return language_import

    @classmethod
    def create(
        cls,
        value: str | rx.Var[str],

        language: Languages,
        theme: rx.Var[Literal["light", "dark"]] | None = None,
        **props: dict,
    ) -> Self:
        theme = theme or rx.color_mode_cond(light="light", dark="dark")
        return super().create(value=value, language=language, theme=theme, **props)

    def render(self):
        tag = self._render({
            "extensions": self.__handle_languages__(handle_for="extensions"),
            "value": self.value,
            "theme": self.theme
        })
        rendered_dict = dict(
            tag.set(
                children=[child.render() for child in self.children]
            )
        )
        return rendered_dict
    
    value: rx.Var[str]
    language: Literal["shell"]
    theme: rx.Var[Literal["light", "dark"]]

    on_change: rx.EventHandler[rx.event.passthrough_event_spec(str)]


Editor = CodeMirror.create
