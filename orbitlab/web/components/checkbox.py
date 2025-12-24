import json
import uuid
from typing import Literal

import reflex as rx


@rx.event
async def set_input_value(_: rx.State, ref: str, current: str, value: str):
    if not current:
        current = "[]"
    selected: list[str] = json.loads(current)
    if value in selected:
        selected.remove(value)
    else:
        selected.append(value)
    return rx.set_value(ref, json.dumps(selected))


@rx.event
async def update_selections(_: rx.State, ref: str, value: str):
    get_element_by_id = rx.vars.FunctionStringVar.create("document.getElementById")
    return rx.run_script(get_element_by_id.call(ref).to(dict).value, lambda result: set_input_value(ref, result, value))


class CheckboxGroupItem:
    def __init__(self, label: str, value: str) -> rx.Component:
        self.label = label
        self.value = value

    def render(self, input_id: str) -> rx.Component:
        return rx.checkbox_group.item(
            self.label,
            value=self.value,
            on_click=update_selections(input_id, self.value),
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


class CheckboxGroup:
    """Group of OrbitLab-styled checkboxes that returns a list[str] when used in forms."""

    Item = staticmethod(CheckboxGroupItem)

    def __new__(
        cls,
        *options: CheckboxGroupItem,
        direction: Literal["row", "column"] = "column",
        **props: dict,
    ) -> rx.Component:
        """Create a CheckboxGroup.

        Args:
            name: The form field name (required for form integration).
            options: A list of labels or (label, value) tuples.
            direction: 'row' or 'column' layout.
            default: Optional list of initially checked values.
        """
        input_id = str(uuid.uuid4())
        name = props.pop("name", None)
        form = props.pop("form", None)
        return rx.el.div(
            rx.el.input(id=input_id, name=name, form=form, class_name="hidden"),
            rx.checkbox_group.root(
                *[option.render(input_id=input_id) for option in options],
                direction=direction,
                **props,
            ),
        )
