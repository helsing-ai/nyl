from importlib.metadata import version

__version__ = version("nyl")


from nyl.tools.pyroscope import init_pyroscope as _init_pyroscope

_init_pyroscope()
