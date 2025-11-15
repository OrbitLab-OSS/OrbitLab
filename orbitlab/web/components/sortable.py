"""Components and types for implementing sortable lists using react-sortablejs in Reflex.

This module defines the SortableJS component, its properties, and helper types for drag-and-drop sortable lists.
"""

from typing import NotRequired, TypedDict

import reflex as rx


class SortableItem(TypedDict):
    """Represents an item in the sortable list.

    Attributes:
        id (int | str): Unique identifier for the item.
        chosen (bool, optional): Indicates if the item is currently chosen.
        selected (bool, optional): Indicates if the item is currently selected.
    """

    id: int | str
    chosen: NotRequired[bool]
    selected: NotRequired[bool]


SORT_ID = rx.vars.FunctionStringVar("item.id")


class SortableListItem:
    def __new__(cls, *children: rx.Component) -> rx.Component:
        return rx.el.div(
            rx.icon(
                "grip-vertical",
                class_name=(
                    "drag-handle ml-3 mr-4 cursor-grab text-gray-500 dark:text-gray-400 "
                    "hover:text-[#1E63E9] dark:hover:text-[#36E2F4] "
                    "active:cursor-grabbing transition-colors duration-200 ease-in-out"
                ),
            ),
            *children,
            key=SORT_ID,
            class_name=(
                "flex items-center gap-2 px-4 py-2 rounded-lg select-none "
                "border border-gray-200/60 dark:border-white/[0.08] "
                "bg-gradient-to-b from-gray-50/90 to-gray-100/80 "
                "dark:from-[#0E1015]/95 dark:to-[#181B22]/90 "
                "shadow-sm hover:shadow-md hover:ring-1 hover:ring-[#36E2F4]/30 "
                "transition-all duration-200 ease-in-out"
            ),
        )


class SortableJS(rx.Component):
    """A Reflex component wrapper for react-sortablejs providing drag-and-drop sortable lists."""

    library = "react-sortablejs@6.1.4"
    tag = "ReactSortable"

    def add_hooks(self) -> list[rx.Var]:
        """Add component function hooks."""
        reflex_data = rx.Var(
            f"const sortableData = {self.sortable_list};",
            _var_data=rx.vars.VarData(
                imports={"react": ["useState"]},
                position=rx.constants.Hooks.HookPosition.PRE_TRIGGER,
            ),
        )
        return [reflex_data]

    @classmethod
    def create(
        cls,
        item_component: SortableListItem,
        *,
        data: rx.Var[list[SortableItem]],
        on_change: rx.EventHandler[rx.event.passthrough_event_spec(list[SortableItem])],
        handle: str = ".drag-handle",
        class_name: str = "max-h-[300px] overflow-auto flex flex-col space-y-2",
        **props: dict,
    ) -> "SortableJS":
        """Create a SortableJS component.

        Args:
            item_component: The component to render for each item.
            data: The list of sortable items with id and optional properties.
            on_change: Event handler called when the sort order changes.
            handle: Optional CSS selector for drag handle element.

        Returns:
            A configured SortableJS component instance.
        """
        return super().create(
            item_component,
            sortable_list=data,
            on_change=on_change,
            handle=handle,
            class_name=class_name,
            **props,
        )

    def __handle_form_props__(self, component: rx.Component) -> None:
        for child in component.children:
            if isinstance(child, rx.Component) and hasattr(child, "name"):
                if isinstance(child.name, str | rx.vars.LiteralStringVar) and "item.id" not in str(child.name):
                    child.name = f"{child.name}-{SORT_ID}"
                self.__handle_form_props__(child)

    def render(self) -> dict:
        """Perform custom render of the component."""
        if len(self.children) != 1:
            msg = "Sortable can only have a single Sortable.Item() child."
            raise ValueError(msg)

        item_component = self.children[0]
        self.__handle_form_props__(item_component)

        if "on_change" in self.event_triggers:
            on_change = self.event_triggers.pop("on_change")
            self.event_triggers["set_list"] = on_change

        tag = self._render({"handle": self.handle, "list": rx.vars.FunctionStringVar.create("sortableData")})
        rendered_dict = dict(
            tag.set(
                children=[f"sortableData.map((item) => {item_component})"],
            ),
        )
        self._replace_prop_names(rendered_dict)
        return rendered_dict

    sortable_list: rx.Var[list[SortableItem]]
    item_component: rx.Component
    handle: str
    on_change: rx.EventHandler[rx.event.passthrough_event_spec(list[SortableItem])]


class SortableNamespace(rx.ComponentNamespace):
    """Namespace for SortableJS component with helper attributes.

    Args:
        Creates a SortableJS component instance via __call__.

    Attributes:
        SortID: Variable for accessing the item id in sortable components.
    """

    __call__ = staticmethod(SortableJS.create)
    Item = staticmethod(SortableListItem)
    SortID = SORT_ID


Sortable = SortableNamespace()
