# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from itertools import count
from typing import Any


MONITOR_REST_ROUTE_PREFIX = "/monitor/REST/"
DOCUMENTED_REST_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")


@dataclass(frozen=True)
class MonitorRestRouteDefinition:
    order: int
    method: str
    path: str
    handler_name: str

    def display_path(self, version: str) -> str:
        return self.path.replace("{version}", version)


@dataclass(frozen=True)
class MonitorRestRouteGroup:
    path: str
    anchor: str
    routes: tuple[MonitorRestRouteDefinition, ...]


class MonitorRestReferenceRegistry:
    def __init__(self) -> None:
        self._routes: list[MonitorRestRouteDefinition] = []
        self._route_keys: set[tuple[str, str, str]] = set()

    @property
    def routes(self) -> tuple[MonitorRestRouteDefinition, ...]:
        return tuple(self._routes)

    def clear(self) -> None:
        self._routes.clear()
        self._route_keys.clear()

    def record(self, route: MonitorRestRouteDefinition) -> None:
        route_key = (route.method, route.path, route.handler_name)
        if route_key in self._route_keys:
            return
        self._route_keys.add(route_key)
        self._routes.append(route)

    def record_route(self, method: str, path: object, handler: Callable[..., Any]) -> None:
        normalized_path = normalize_route_path(path)
        normalized_method = method.upper()
        if normalized_path is None:
            return
        if normalized_method not in DOCUMENTED_REST_METHODS:
            return
        if not normalized_path.startswith(MONITOR_REST_ROUTE_PREFIX):
            return

        self.record(
            MonitorRestRouteDefinition(
                order=next(_DOCUMENTED_REST_ROUTE_ORDER),
                method=normalized_method,
                path=normalized_path,
                handler_name=getattr(handler, "__name__", handler.__class__.__name__),
            )
        )

    def route_groups(self, version: str) -> tuple[MonitorRestRouteGroup, ...]:
        route_groups: list[MonitorRestRouteGroup] = []
        route_groups_by_path: dict[str, list[MonitorRestRouteDefinition]] = {}
        for route in self._routes:
            route_groups_by_path.setdefault(route.display_path(version), []).append(route)

        for path, routes in route_groups_by_path.items():
            route_groups.append(
                MonitorRestRouteGroup(
                    path=path,
                    anchor=slugify(path),
                    routes=tuple(routes),
                )
            )
        return tuple(route_groups)


MONITOR_REST_REFERENCE = MonitorRestReferenceRegistry()
_DOCUMENTED_REST_ROUTE_ORDER = count()


def monitor_rest_route_groups(version: str) -> tuple[MonitorRestRouteGroup, ...]:
    return MONITOR_REST_REFERENCE.route_groups(version)


def install_monitor_rest_route_collector(
    router: Any,
    registry: MonitorRestReferenceRegistry = MONITOR_REST_REFERENCE,
) -> None:
    for method in DOCUMENTED_REST_METHODS:
        add_method_name = f"add_{method.lower()}"
        original_add_method = getattr(router, add_method_name, None)
        if original_add_method is None:
            continue
        if getattr(original_add_method, "__rct_monitor_rest_collector__", False):
            continue

        def add_with_reference(
            path: object,
            handler: Callable[..., Any],
            *args: Any,
            _method: str = method,
            _original_add_method: Callable[..., Any] = original_add_method,
            **kwargs: Any,
        ) -> Any:
            registry.record_route(_method, path, handler)
            return _original_add_method(path, handler, *args, **kwargs)

        setattr(add_with_reference, "__rct_monitor_rest_collector__", True)
        setattr(router, add_method_name, add_with_reference)


def normalize_route_path(path: object) -> str | None:
    if not isinstance(path, str):
        return None
    return path.split("?", 1)[0]


def slugify(text: str) -> str:
    slug = text.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-") or "section"
