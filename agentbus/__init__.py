"""Public package exports for agent-bus."""
from importlib import import_module

__version__ = "0.1.0"
__all__ = ["a2a", "assessment", "bus", "__version__"]


def __getattr__(name):
    if name in {"a2a", "assessment", "bus"}:
        module = import_module(f"{__name__}.{name}")
        globals()[name] = module
        return module
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
