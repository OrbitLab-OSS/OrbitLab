"""OrbitLab utilities."""

import inspect
import os
from base64 import b64encode
from types import FunctionType
from typing import Any, TypeVar, get_type_hints

import reflex as rx
from reflex.utils.exceptions import StateValueError

T = TypeVar("T", bound=rx.state.BaseState)


class CacheBuster(rx.State, mixin=True):
    """Mixin class for managing cache invalidation of computed variables."""

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


async def _get_user_state(client_token: str, state: type[T]) -> T:
    manager = rx.state.get_state_manager()
    base_state = await manager.get_state(client_token)
    return await base_state.get_state(state)


async def emit_state_event(client_token: str, state: type[T], event_name: str, params: dict | None = None) -> None:
    """Emit an event on a specific state instance.

    Args:
        client_token: The client token to identify the session.
        state: The state class to get the instance from.
        event_name: The name of the event method to call.
        params: Parameters to pass to the event method, by default None.
    """
    if not params:
        params = {}
    user_state = await _get_user_state(client_token, state)
    await getattr(user_state, event_name)(**params)


async def emit_decentralized_event(client_token: str, event: rx.EventHandler, params: dict | None = None) -> None:
    """Emit a decentralized event by calling the event handler with the appropriate state instance.

    Args:
        client_token: The client token to identify the session.
        event: The event handler to call.
        params: Parameters to pass to the event handler, by default None.

    Raises:
        TypeError: If the event is not a decentralized event or the first argument is not a subclass of rx.State.
    """
    if not params:
        params = {}
    try:
        signature = inspect.signature(event.fn)
        param = next(iter(signature.parameters.values()))
    except StopIteration as err:
        msg = f"Event {event} is not a decentralized event."
        raise TypeError(msg) from err
    else:
        state = param.annotation
        if not issubclass(state, rx.state.BaseState):
            msg = f"The first argument to event {event} is not a subclass of rx.State."
            raise TypeError(msg)
    user_state = await _get_user_state(client_token, state)
    await event.fn(user_state, **params)


def custom_download(  # noqa: C901, PLR0912
    url: str | rx.Var | None = None,
    filename: str | rx.Var | None = None,
    data: str | bytes | rx.Var | None = None,
    mime_type: str | rx.Var | None = None,
) -> rx.event.EventSpec:
    """Download the file at a given path or with the specified data.

    Args:
        url: The URL to the file to download.
        filename: The name that the file should be saved as after download.
        data: The data to download.
        mime_type: The mime type of the data to download.

    Raises:
        ValueError: If the URL provided is invalid, both URL and data are provided,
            or the data is not an expected type.

    Returns:
        EventSpec: An event to download the associated file.
    """
    from reflex.components.core.cond import cond

    if isinstance(url, str):
        if not url.startswith("/"):
            msg = "The URL argument should start with a /"
            raise ValueError(msg)

        # if filename is not provided, infer it from url
        if filename is None:
            filename = url.rpartition("/")[-1]

    if filename is None:
        filename = ""

    if data is not None:
        if url is not None:
            msg = "Cannot provide both URL and data to download."
            raise ValueError(msg)

        if isinstance(data, str):
            if mime_type is None:
                mime_type = "text/plain"
            # Caller provided a plain text string to download.
            url = f"data:{mime_type};base64," + b64encode(data.encode("utf-8")).decode(
                "utf-8",
            )
        elif isinstance(data, rx.Var):
            if mime_type is None:
                mime_type = "text/plain"
            # Need to check on the frontend if the Var already looks like a data: URI.

            is_data_url = (data.js_type() == "string") & (data.to(str).startswith("data:"))
            # If it's a data: URI, use it as is, otherwise convert the Var to JSON in a data: URI.
            url = cond(
                is_data_url,
                data.to(str),
                (
                    CREATE_OBJECT_URL.call(create_new_blob(data, mime_type))  # pyright: ignore[reportArgumentType]
                    if isinstance(data, rx.vars.ArrayVar)
                    else f"data:{mime_type};base64,"
                    + BASE64_ENCODE.call(
                        data.to(str) if isinstance(data, rx.vars.StringVar) else data.to_string(),
                    ).to(str)
                ),
            )
        elif isinstance(data, bytes):
            if mime_type is None:
                mime_type = "application/octet-stream"
            # Caller provided bytes, so base64 encode it as a data: URI.
            b64_data = b64encode(data).decode("utf-8")
            url = f"data:{mime_type};base64," + b64_data
        else:
            msg = f"Invalid data type {type(data)} for download. Use `str` or `bytes`."
            raise ValueError(msg)

    return rx.event.server_side(
        "_download",
        rx.event.get_fn_signature(custom_download),
        url=url,
        filename=filename,
    )


BASE64_ENCODE = rx.vars.FunctionStringVar.create(
    "btoa",
    _var_type=rx.vars.function.ReflexCallable[[Any], str],
)
CREATE_OBJECT_URL = rx.vars.FunctionStringVar.create(
    "window.URL.createObjectURL",
    _var_type=rx.vars.function.ReflexCallable[[Any], str],
)


@rx.vars.var_operation
def create_new_blob(data: rx.vars.ArrayVar, mime_type: str):  # noqa: ANN201, D103
    return rx.vars.var_operation_return(
        js_expression=f"new Blob([new Uint8Array({data})], {{ type: '{mime_type}' }})",
    )


def is_production() -> bool:
    """Return True if the application is running in production mode, False otherwise."""
    return not bool(os.environ.get("ORBITLAB_DEV"))
