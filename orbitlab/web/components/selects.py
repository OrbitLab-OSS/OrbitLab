"""OrbitLab Select Components."""

import json
import uuid
from types import FunctionType
from typing import Any, TypedDict, Unpack

import reflex as rx


class MultiSelectState(rx.State):
    """State management for multi-select components."""

    registered: rx.Field[dict[str, list[str]]] = rx.field(default_factory=dict)

    @rx.event
    async def toggle_multiselect_value(self, ref: str, current: str, value: str) -> rx.event.EventSpec:
        """Toggle an option in the selected list stored in a hidden input."""
        if not current:
            current = "[]"
        selected: list[str] = json.loads(current)
        if value in selected:
            selected.remove(value)
        else:
            selected.append(value)
        self.registered[ref] = selected
        return rx.set_value(ref, json.dumps(selected))

    @rx.event
    async def update_multiselect(self, ref: str, value: str) -> rx.event.EventSpec:
        """Helper to run a JS snippet to read the hidden input's value and update selections."""
        get_element_by_id = rx.vars.FunctionStringVar.create("document.getElementById")
        return rx.run_script(
            get_element_by_id.call(ref).to(dict).value,
            lambda result: MultiSelectState.toggle_multiselect_value(ref, result, value),
        )


class MultiSelectProps(TypedDict, total=False):
    """Type definition for Select component properties."""

    placeholder: str
    required: bool
    name: str
    form: str
    refresh_button: rx.Component


class MultiSelect:
    """OrbitLab-styled MultiSelect dropdown component."""

    @classmethod
    def __option__(cls, input_id: str, option: str | rx.Var[str]) -> rx.Component:
        """Create and return the multiselect option component."""
        return rx.select.item(
            option,
            value=option,
            disabled=MultiSelectState.registered.get(input_id, []).to(list).contains(option),
            class_name=(
                "flex items-center rounded-md cursor-pointer "
                "text-sm font-medium select-none "
                "text-gray-800 dark:text-gray-200 "
                "hover:bg-gray-100 dark:hover:bg-white/[0.06] "
                "disabled:bg-sky-100 dark:disabled:bg-[#1E63E9]/20 "
                "disabled:text-[#1E63E9] dark:disabled:text-[#36E2F4] "
                "transition-all duration-150 ease-in-out"
            ),
        )

    @classmethod
    def __chip__(cls, input_id: str, value: str) -> rx.Component:
        """Create and return the option chip."""
        return rx.el.div(
            value,
            rx.icon(
                "x",
                size=12,
                class_name="cursor-pointer",
                on_click=MultiSelectState.update_multiselect(input_id, value),
            ),
            class_name=(
                "flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium "
                "bg-[#1E63E9]/10 text-[#1E63E9] dark:bg-[#36E2F4]/10 dark:text-[#36E2F4] "
                "border border-[#1E63E9]/20 dark:border-[#36E2F4]/20 "
                "hover:bg-[#1E63E9]/20 dark:hover:bg-[#36E2F4]/20 "
                "transition-colors duration-150 ease-in-out"
            ),
        )

    def __new__(cls, options: list[str] | rx.Var[list[str]], **props: Unpack[MultiSelectProps]) -> rx.Component:
        """Create and return a MultiSelect component."""
        input_id = str(uuid.uuid4())
        name = props.pop("name", None)
        form = props.pop("form", None)
        placeholder = props.pop("placeholder", "Select items")
        refresh_button = props.pop("refresh_button", rx.fragment())

        class_name = (
            "px-3 py-2 outline-none rounded-lg grow "
            "text-sm font-medium transition-all duration-300 ease-in-out "
            "bg-gradient-to-b from-gray-50/95 to-gray-200/80 "
            "border border-gray-200 text-gray-800 "
            "dark:from-[#0E1015]/95 dark:to-[#181B22]/90 "
            "dark:text-gray-100 dark:border-white/[0.08] "
            "hover:ring-1 hover:ring-[#36E2F4]/30 "
            "focus:ring-2 focus:ring-[#36E2F4]/40 focus:border-[#36E2F4]/40 "
            "shadow-[inset_0_0_0.5px_rgba(255,255,255,0.1)]"
        )

        return rx.el.div(
            rx.el.input(id=input_id, name=name, form=form, class_name="hidden"),
            rx.el.div(
                rx.select.root(
                    rx.select.trigger(placeholder=placeholder, class_name=class_name),
                    rx.select.content(
                        rx.foreach(options, lambda opt: cls.__option__(input_id, opt)),
                    ),
                    value="",
                    on_change=lambda value: MultiSelectState.update_multiselect(input_id, value),
                    class_name=class_name,
                    **props,
                ),
                refresh_button,
                class_name="flex grow",
            ),
            rx.el.div(
                rx.foreach(
                    MultiSelectState.registered.get(input_id, []),
                    lambda value: cls.__chip__(input_id, value),
                ),
                class_name="flex flex-wrap gap-1 my-1 empty:hidden",
            ),
            class_name="group flex flex-col grow",
        )


class SelectProps(TypedDict, total=False):
    """Type definition for Select component properties."""

    value: Any | rx.Var[Any]
    default_value: Any | rx.Var[Any]
    on_change: rx.EventHandler[str] | rx.event.EventCallback | FunctionType
    placeholder: str
    name: str
    form: str
    required: bool
    disabled: bool | rx.Var[bool]


class Select:
    """OrbitLab-styled Select dropdown component."""

    @classmethod
    def __option__(cls, option: rx.vars.StringVar | rx.vars.ArrayVar) -> rx.Component:
        """Create a select option item component."""
        class_name = (
            "bg-gradient-to-b from-gray-50/95 to-gray-200/80 text-gray-800 dark:from-[#0E1015]/95 dark:to-[#181B22]/90 "
            "dark:text-gray-100"
        )
        if isinstance(option, rx.vars.StringVar):
            return rx.select.item(option, value=option, class_name=class_name)
        return rx.select.item(option[0], value=option[1], class_name=class_name)

    def __new__(
        cls,
        options: rx.Var[list[str] | dict[str, str]] | rx.vars.ArrayVar,
        **props: Unpack[SelectProps],
    ) -> rx.Component:
        """Create and return the select component."""
        error = props.pop("error", "Invalid selection")
        wrapper_class = props.pop("class_name", "")
        refresh_button = props.pop("refresh_button", rx.fragment())
        class_name = (
            "px-3 py-2 outline-none rounded-lg grow "
            "text-sm font-medium transition-all duration-300 ease-in-out "
            "bg-gradient-to-b from-gray-50/95 to-gray-200/80 "
            "border border-gray-200 text-gray-800 "
            "dark:from-[#0E1015]/95 dark:to-[#181B22]/90 "
            "dark:text-gray-100 dark:border-white/[0.08] "
            "hover:ring-1 hover:ring-[#36E2F4]/30 "
            "focus:ring-2 focus:ring-[#36E2F4]/40 focus:border-[#36E2F4]/40 "
            "shadow-[inset_0_0_0.5px_rgba(255,255,255,0.1)] disabled:opacity-50"
        )
        return rx.el.div(
            rx.el.div(
                rx.select.root(
                    rx.select.trigger(placeholder=props.pop("placeholder", "Select Item"), class_name=class_name),
                    rx.select.content(rx.foreach(options, lambda opt: cls.__option__(opt))),
                    align=props.pop("align", "center"),
                    class_name=class_name,
                    **props,
                ),
                refresh_button,
                class_name="flex grow",
            ),
            rx.el.p(error, class_name="hidden mt-1 text-sm text-rose-400 group-has-user-invalid:block"),
            class_name=f"group flex flex-col {wrapper_class}",
        )
