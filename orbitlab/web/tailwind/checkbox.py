"""OrbitLab Checkbox Group Component."""

import json
import uuid
from typing import Literal, TypedDict, Unpack, cast

import reflex as rx
from reflex.event import EventSpec

from orbitlab.data_types import FrontendEvents
from orbitlab.web.utilities import EventGroup


class CheckboxGroupItem(EventGroup):
    """Represents an item in a checkbox group with a label and value."""

    @staticmethod
    @rx.event
    async def set_input_value(_: rx.State, ref: str, current: str, value: str) -> EventSpec:
        """Toggle the presence of a value in the current selection and update the input value."""
        if not current:
            current = "[]"
        selected: list[str] = json.loads(current)
        if value in selected:
            selected.remove(value)
        else:
            selected.append(value)
        return rx.set_value(ref, json.dumps(selected))

    @staticmethod
    @rx.event
    async def update_selections(_: rx.State, ref: str, value: str) -> EventSpec:
        """Update the checkbox selections by toggling the specified value."""
        get_element_by_id = rx.vars.FunctionStringVar.create("document.getElementById")
        return rx.run_script(
            javascript_code=get_element_by_id.call(ref).to(dict).value,
            callback=lambda result: CheckboxGroupItem.set_input_value(ref, result, value),
        )

    def __init__(self, label: str, value: str) -> None:
        """Initialize a CheckboxGroupItem with a label and value."""
        self.label = label
        self.value = value

    def render(self, input_id: str) -> rx.Component:
        """Render the checkbox group item as a Reflex component."""
        return rx.checkbox_group.item(
            self.label,
            value=self.value,
            on_click=CheckboxGroupItem.update_selections(input_id, self.value),
            class_name=(
                "flex items-center gap-2 px-2 py-1 rounded-md "
                "text-sm font-medium cursor-pointer select-none "
                "text-gray-800 dark:text-gray-200 "
                "hover:bg-gray-100 dark:hover:bg-white/[0.06] "
                "data-[state=checked]:bg-sky-100 dark:data-[state=checked]:bg-[#1E63E9]/20 "
                "data-[state=checked]:text-[#1E63E9] dark:data-[state=checked]:text-[#36E2F4] "
                "transition-all duration-150 ease-in-out"
            ),
        )


class CheckboxGroupProps(TypedDict, total=False):
    """TypedDict for properties of the CheckboxGroup component."""

    direction: Literal["row", "column"]
    form: str
    name: str
    required: bool


class CheckboxGroup:
    """Group of OrbitLab-styled checkboxes that returns a list[str] when used in forms."""

    Item = staticmethod(CheckboxGroupItem)

    def __new__(cls, *options: CheckboxGroupItem, **props: Unpack[CheckboxGroupProps]) -> rx.Component:
        """Create and return a checkbox group component."""
        props.setdefault("direction", "column")
        input_id = str(uuid.uuid4())
        name = props.pop("name", None)
        form = props.pop("form", None)
        return rx.el.div(
            rx.el.input(id=input_id, name=name, form=form, class_name="hidden"),
            rx.checkbox_group.root(
                *[option.render(input_id=input_id) for option in options],
                **props,
            ),
        )


class CheckboxProps(TypedDict, total=False):
    """TypedDict for properties of the Checkbox component."""

    text: str | rx.Var[str]
    checked: bool | rx.Var[bool]
    on_click: FrontendEvents
    form: str
    name: str
    required: bool
    class_name: str


class Checkbox:
    """OrbitLab-styled single checkbox component."""

    def __new__(cls, **props: Unpack[CheckboxProps]) -> rx.Component:
        """Create and return the component."""
        text = props.pop("text", "")
        checked = props.pop("checked", None)
        class_name = props.pop("class_name", "")
        form = props.pop("form", None)
        name = props.pop("name", None)
        required = props.pop("required", None)
        on_click = props.pop("on_click", None)
        return rx.checkbox(
            text=text,
            checked=checked,
            form=form,
            name=name,
            required=required,
            on_click=cast("rx.event.EventHandler", on_click),
            class_name=(
                "peer h-4 w-4 shrink-0 rounded-md "
                "transition-all duration-200 ease-in-out "
                "bg-gradient-to-b from-gray-50/95 to-gray-200/80 "
                "border border-gray-300 "
                "dark:from-[#0E1015]/95 dark:to-[#181B22]/90 "
                "dark:border-white/[0.12] "
                "hover:ring-1 hover:ring-[#36E2F4]/30 "
                "focus-visible:outline-none focus-visible:ring-2 "
                "focus-visible:ring-[#36E2F4]/40 "
                "data-[state=checked]:bg-[#1E63E9] "
                "data-[state=checked]:border-[#1E63E9] "
                "dark:data-[state=checked]:bg-[#36E2F4] "
                "dark:data-[state=checked]:border-[#36E2F4] "
                f"shadow-[inset_0_0_0.5px_rgba(255,255,255,0.25)] {class_name}"
            ),
        )
