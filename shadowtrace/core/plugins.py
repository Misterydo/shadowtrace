from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from shadowtrace.modules.base import BaseExtractor
from shadowtrace.modules.registry import register_extractor


def load_plugin_module(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load plugin module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def discover_plugins(directory: str | Path = "plugins") -> list[str]:
    plugin_dir = Path(directory)
    if not plugin_dir.exists():
        return []
    loaded: list[str] = []
    for file_path in sorted(plugin_dir.glob("*.py")):
        if file_path.name.startswith("_"):
            continue
        module = load_plugin_module(file_path)
        extractor = getattr(module, "EXTRACTOR", None)
        site_name = getattr(module, "SITE_NAME", None)
        url_template = getattr(module, "URL_TEMPLATE", None)
        if isinstance(extractor, BaseExtractor) and isinstance(site_name, str) and isinstance(url_template, str):
            register_extractor(site_name, url_template, extractor)
            loaded.append(site_name)
    return loaded
