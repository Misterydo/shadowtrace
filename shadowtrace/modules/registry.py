from __future__ import annotations

from collections.abc import Iterable

from shadowtrace.core.models import TargetType
from shadowtrace.modules.base import BaseExtractor
from shadowtrace.modules.github import GitHubExtractor
from shadowtrace.modules.instagram import InstagramExtractor
from shadowtrace.modules.reddit import RedditExtractor
from shadowtrace.modules.twitter import TwitterExtractor


class ModuleRegistry:
    """Runtime registry for built-in and dynamically loaded modules."""

    def __init__(self) -> None:
        self._url_templates: dict[str, str] = {}
        self._modules: dict[str, BaseExtractor] = {}

    def register(self, name: str, url_template: str, module: BaseExtractor) -> None:
        module.url_template = url_template
        self._url_templates[name] = url_template
        self._modules[name] = module

    def unregister(self, name: str) -> None:
        self._url_templates.pop(name, None)
        self._modules.pop(name, None)

    def names(self) -> list[str]:
        return list(self._modules)

    def url_template(self, name: str) -> str:
        return self._url_templates[name]

    def module(self, name: str) -> BaseExtractor:
        return self._modules[name]

    def items(self) -> Iterable[tuple[str, str, BaseExtractor]]:
        for name, url_template in self._url_templates.items():
            yield name, url_template, self._modules[name]

    def modules_for_target(self, target_type: TargetType) -> list[BaseExtractor]:
        return sorted(
            (module for module in self._modules.values() if target_type in module.target_types),
            key=lambda module: int(module.priority),
            reverse=True,
        )

    def find_extractor_for_url(self, url: str) -> BaseExtractor | None:
        for module in self._modules.values():
            if module.is_url_match(url):
                return module
        return None

    def describe(self) -> list[dict[str, object]]:
        return [module.platform_profile() for module in self._modules.values()]


MODULE_REGISTRY = ModuleRegistry()
MODULE_REGISTRY.register("GitHub", "https://github.com/{}", GitHubExtractor())
MODULE_REGISTRY.register("Instagram", "https://www.instagram.com/{}/", InstagramExtractor())
MODULE_REGISTRY.register("Twitter", "https://twitter.com/{}", TwitterExtractor())
MODULE_REGISTRY.register("Reddit", "https://www.reddit.com/user/{}", RedditExtractor())

# Backward-compatible maps used by older code and third-party scripts.
SITES: dict[str, str] = MODULE_REGISTRY._url_templates
EXTRACTORS: dict[str, BaseExtractor] = MODULE_REGISTRY._modules


def find_extractor_for_url(url: str) -> BaseExtractor | None:
    return MODULE_REGISTRY.find_extractor_for_url(url)


def register_extractor(name: str, url_template: str, extractor: BaseExtractor) -> None:
    MODULE_REGISTRY.register(name, url_template, extractor)


def register_module(name: str, url_template: str, module: BaseExtractor) -> None:
    MODULE_REGISTRY.register(name, url_template, module)
