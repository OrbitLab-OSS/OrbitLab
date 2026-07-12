"""Components and types for implementing sortable lists using react-sortablejs in Reflex.

This module defines the SortableJS component, its properties, and helper types for drag-and-drop sortable lists.
"""

from collections.abc import Sequence
from typing import NotRequired, TypedDict, Unpack

import reflex as rx
from reflex.components.core.foreach import Foreach


class SortableItem(TypedDict):
    """Represents an item in the sortable list."""

    id: int
    chosen: NotRequired[bool]
    selected: NotRequired[bool]


SORT_ID = rx.vars.FunctionStringVar("item.id")


class SortableProps(TypedDict, total=False):
    """SortableJS Component Props."""

    class_name: str


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
        *children: rx.Component,
        data: rx.Var[Sequence[SortableItem]],
        on_change: rx.EventHandler[rx.event.passthrough_event_spec(list[SortableItem])] | rx.event.EventCallback,
        handle: str = ".drag-handle",
        **props: Unpack[SortableProps],
    ) -> "SortableJS":
        """Create a SortableJS component.

        Args:
            children: The component children to render for each item.
            data: The list of sortable items with id and optional properties.
            on_change: Event handler called when the sort order changes.
            handle: Optional CSS selector for drag handle element.
            props: Additional component props.

        Returns:
            A configured SortableJS component instance.
        """
        if len(children) != 1 or children[0].__class__ != Foreach:
            msg = "Sortable only takes one child of `rx.foreach(...)` type."
            raise RuntimeError(msg)
        props.setdefault("class_name", "max-h-[300px] overflow-auto flex flex-col space-y-2")
        return super().create(
            *children,
            sortable_list=data,
            on_change=on_change,
            handle=handle,
            **props,
        )

    def render(self) -> dict:
        """Perform custom render of the component."""
        if len(self.children) != 1:
            msg = "Sortable can only have a single Sortable.Item() child."
            raise ValueError(msg)

        if "on_change" in self.event_triggers:
            on_change = self.event_triggers.pop("on_change")
            self.event_triggers["set_list"] = on_change

        tag = self._render({"handle": self.handle, "list": rx.vars.FunctionStringVar.create("sortableData")})
        rendered_dict = dict(
            tag.set(
                children=[child.render() for child in self.children],
            ),
        )
        self._replace_prop_names(rendered_dict)
        return rendered_dict

    sortable_list: rx.Var[list[SortableItem]]
    handle: str
    on_change: rx.EventHandler[rx.event.passthrough_event_spec(list[SortableItem])]


Sortable = SortableJS.create
