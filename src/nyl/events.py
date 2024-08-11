"""
Events that can be sent to observers in Nyl.
"""

from dataclasses import dataclass
from functools import wraps
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable
from typing_extensions import Literal

from loguru import logger

if TYPE_CHECKING:
    from nyl.profiles.tunnel import TunnelSpec, TunnelStatus
    from nyl.profiles.config import LocalKubeconfig, KubeconfigFromSsh, Profile
    from nyl.profiles import ActivatedProfile

EventListener = Callable[[Any], Any | None]


def wrap_event_listener(listener: EventListener | None) -> EventListener:
    """
    Wrap an event listener to catch any exceptions it may cause and log them. If *none* is specified, a function
    that does nothing will be returned to send events to the void.
    """

    is_wrapped_listener_attr = "__is_wrapped_event_listener__"

    if listener is None:

        def void_listener(_ev: Any) -> None:
            return None

        # Set the attribute to prevent the void listener from being wrapped.
        setattr(void_listener, is_wrapped_listener_attr, True)
        return void_listener

    if getattr(listener, is_wrapped_listener_attr, False):
        return listener

    @wraps(listener)
    def wrapper(event: Any, /) -> Any | None:
        try:
            return listener(event)
        except Exception:
            logger.exception("An unhandled exception occurred in event listener {!r}", listener)
            return None

    setattr(wrapper, is_wrapped_listener_attr, True)
    return wrapper


@dataclass
class TunnelReused:
    """
    Dispatched when a tunnel got reconciled and the previous tunnel was reused.
    """

    spec: "TunnelSpec"
    status: "TunnelStatus"


@dataclass
class TunnelStop:
    """
    Dispatched before a tunnel is closed.
    """

    spec: "TunnelSpec"
    status: "TunnelStatus"
    reason: Literal["requested", "outdated"]


@dataclass
class TunnelStart:
    """
    Dispatched when a new tunnel is created, once before the tunnel is created and once that it is complete.
    """

    spec: "TunnelSpec"
    status: "TunnelStatus"
    command: list[str]
    started: bool


@dataclass
class OnGetRawKubeConfig:
    """
    This event is sent when [KubeconfigManager.get_raw_kubeconfig()] is called.
    """

    source: "LocalKubeconfig | KubeconfigFromSsh"
    """ The source from which the Kubeconfig is getting fetched."""

    dest_path: Path
    """ The destination path where the raw Kubeconfig will be stored."""

    command: list[str] | None
    """ The command that is run to fetch the Kubeconfig, if applicable. """

    force_refresh: bool
    """ Whether a force refresh was requested. """

    skipped: bool
    """
    Whether the fetch operation will be skipped, usually because [dest_path] exists and [force_refresh]
    is `False`.
    """

    phase: Literal["before", "after"]
    """
    Whether this event is before or after the Kubeconfig was fetched.
    """


@dataclass
class ActivateProfile:
    """
    Dispatched before a Nyl profile is activated. Activating a profile means ensuring that its tunnel is open (if any),
    and ensuring that the Kubeconfig is accessible.
    """

    profile_name: str
    profile: "Profile"
    phase: Literal["start", "wait-for-api-server", "completed"]
    result: "ActivatedProfile | None" = None  # Not set for "start"
