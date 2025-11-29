"""Core infrastructure for Nyl - DI, error handling, and framework code."""

from nyl.core.di import DIContainer
from nyl.core.errors import NylError

__all__ = ["DIContainer", "NylError"]
