"""OrbitLab utilities."""

import importlib
import inspect
import os
from base64 import b64encode
from types import FunctionType
from typing import TYPE_CHECKING, Any, TypeVar, get_type_hints

import reflex as rx
from redis.asyncio import Redis
from reflex.utils.exceptions import StateValueError

if TYPE_CHECKING:
    from reflex.istate.manager.redis import StateManagerRedis

    from orbitlab.worker import Worker


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


def get_worker() -> "Worker":
    """Get the Worker module instance."""
    worker_module = importlib.import_module(name="orbitlab.worker.worker")
    return worker_module.Worker


def get_redis() -> Redis:
    """Get the Reflex Redis client."""
    manager: StateManagerRedis = rx.state.get_state_manager()
    return manager.redis


async def get_redis_value(name: str, key: str, default: str = "") -> str:
    """Retrieve a value from Redis for a given manifest and key."""
    manager: StateManagerRedis = rx.state.get_state_manager()
    try:
        value = await manager.redis.hget(name=name, key=key)
    except Exception as err:  # noqa: BLE001
        print(err)
        return ""
    else:
        if value and isinstance(value, bytes):
            value = value.decode()
        if not value:
            value = default
        return value


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
