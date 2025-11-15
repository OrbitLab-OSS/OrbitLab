import inspect
from typing import TypeVar

import reflex as rx

T = TypeVar("T", bound=rx.state.BaseState)


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
