from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def load_isolated_release_module(filename: str, module_name: str) -> ModuleType:
    """Load a proven 2.2.0 helper under an isolated module identity.

    Patch-release adapters may then replace version constants without mutating the
    imported 2.2.0 module or its immutable public-release verifier.
    """

    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing
    path = Path(__file__).with_name(filename)
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load isolated release helper: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(module_name, None)
        raise
    return module
