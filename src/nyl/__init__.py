from importlib.metadata import version

from .templating import LookupError, NylTemplateEngine, register

__version__ = version("nyl")

__all__ = [
    "LookupError",
    "NylTemplateEngine",
    "register",
    "__version__", # Add existing __version__ to __all__
]
