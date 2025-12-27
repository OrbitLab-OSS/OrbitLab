"""OrbitLab State Utilities."""

import inspect
from types import FunctionType
from typing import get_type_hints

import reflex as rx
from reflex.utils.exceptions import StateValueError


class EventGroup:
    """Base class for grouping event handlers."""

    def __init_subclass__(cls) -> None:
        """Initialize subclass and register event handlers for static methods."""
        events = {
            name: func.__get__(None, object)
            for name, func in vars(cls).items()
            if not name.startswith("_") and isinstance(func, staticmethod)
        }
        for event, func in events.items():
            if not isinstance(func, FunctionType):
                continue
            types = get_type_hints(func)
            state_arg_name = next(iter(inspect.signature(func).parameters), "")
            state_cls = types.get(state_arg_name, type[None])
            if not issubclass(state_cls, rx.state.BaseState):
                msg = f"Event {cls.__name__}.{event}'s first argument must be a state class."
                raise TypeError(msg)
            name = (
                (func.__module__ + "." + func.__qualname__).replace(".", "_").replace("<locals>", "_").removeprefix("_")
            )
            object.__setattr__(func, "__name__", name)
            object.__setattr__(func, "__qualname__", name)
            state_cls._add_event_handler(name, func)  # noqa: SLF001
            setattr(cls, event, getattr(state_cls, name))


class CacheBuster(rx.State, mixin=True):
    """Mixin class for managing cache invalidation of computed variables.

    This class provides functionality to selectively clear cached computed variables
    by toggling internal tracking variables that force recomputation.
    """

    def __init_subclass__(cls, **kwargs: bool) -> None:
        """Initialize subclass and add cached tracking variables for computed vars."""
        super().__init_subclass__(**kwargs)
        for var in cls.computed_vars:
            cls.add_var(f"_cached_{var}", bool, default_value=False)

    @rx.event
    async def cache_clear(self, var: str) -> None:
        """Clear the cache for a specific computed variable."""
        if var not in self.computed_vars:
            msg = f"State '{self.get_name()}' has no computed var named '{var}'."
            raise StateValueError(msg)

        tracked_var = f"_cached_{var}"
        if hasattr(self, tracked_var):
            current = getattr(self, tracked_var)
            setattr(self, tracked_var, not current)
