from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

from shadowtrace.modules.base import BaseExtractor
from shadowtrace.modules.registry import register_extractor, register_module


def load_plugin_module(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load plugin module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _iter_plugin_files(directories: str | Path | list[str | Path]) -> list[Path]:
    paths = [directories] if isinstance(directories, (str, Path)) else directories
    files: list[Path] = []
    for directory in paths:
        plugin_dir = Path(directory)
        if not plugin_dir.exists():
            continue
        files.extend(path for path in sorted(plugin_dir.glob("*.py")) if not path.name.startswith("_"))
    return files


def discover_plugins(directory: str | Path | list[str | Path] = "plugins") -> list[str]:
    loaded: list[str] = []
    for file_path in _iter_plugin_files(directory):
        module = load_plugin_module(file_path)
        site_name = getattr(module, "SITE_NAME", None)
        url_template = getattr(module, "URL_TEMPLATE", None)

        candidates = []
        if getattr(module, "MODULE", None) is not None:
            candidates.append(getattr(module, "MODULE"))
        if getattr(module, "EXTRACTOR", None) is not None:
            candidates.append(getattr(module, "EXTRACTOR"))
        candidates.extend(getattr(module, "MODULES", []))

        for candidate in candidates:
            if not isinstance(candidate, BaseExtractor):
                continue
            name = str(site_name or candidate.module_name)
            template = str(url_template or getattr(candidate, "url_template", "{}"))
            register_module(name, template, candidate)
            loaded.append(name)
    return loaded
