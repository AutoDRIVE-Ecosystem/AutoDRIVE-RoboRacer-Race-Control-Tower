# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from itertools import count
from typing import Any


SUPPORTED_DEVELOP_VERSIONS = frozenset({"0.1", "latest"})
MONITOR_REST_ROUTE_PREFIX = "/monitor/REST/"
MONITOR_WS_ROUTE_PREFIX = "/monitor/WS/"
DOCUMENTED_ROUTE_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")


@dataclass(frozen=True)
class MonitorRouteDefinition:
    order: int
    transport: str
    method: str
    path: str
    handler_name: str
    description: str
    input_schema: dict[str, Any] | None
    output_schema: dict[str, Any] | None

    def display_path(self, version: str) -> str:
        return self.path.replace("{version}", version)


class DevelopReferenceRegistry:
    def __init__(self) -> None:
        self._routes: list[MonitorRouteDefinition] = []
        self._route_keys: set[tuple[str, str, str, str]] = set()

    @property
    def routes(self) -> tuple[MonitorRouteDefinition, ...]:
        return tuple(self._routes)

    def clear(self) -> None:
        self._routes.clear()
        self._route_keys.clear()

    def record_route(
        self,
        method: str,
        path: object,
        handler: Callable[..., Any],
        description: str,
        input_schema: dict[str, Any] | None = None,
        output_schema: dict[str, Any] | None = None,
    ) -> None:
        normalized_path = normalize_route_path(path)
        normalized_method = method.upper()
        if normalized_path is None or not description:
            return
        if normalized_method not in DOCUMENTED_ROUTE_METHODS:
            return

        transport = transport_for_path(normalized_path)
        if transport is None:
            return

        route = MonitorRouteDefinition(
            order=next(_DOCUMENTED_ROUTE_ORDER),
            transport=transport,
            method=normalized_method,
            path=normalized_path,
            handler_name=getattr(handler, "__name__", handler.__class__.__name__),
            description=description,
            input_schema=input_schema,
            output_schema=output_schema,
        )
        route_key = (route.transport, route.method, route.path, route.handler_name)
        if route_key in self._route_keys:
            return
        self._route_keys.add(route_key)
        self._routes.append(route)

    def reference(self, version: str) -> dict[str, Any]:
        if version not in SUPPORTED_DEVELOP_VERSIONS:
            raise ValueError(f"unsupported develop reference version: {version}")
        return {
            "version": version,
            "rest_routes": self._route_groups("REST", version),
            "ws_routes": self._route_groups("WS", version),
            "ws_messages": MONITOR_WS_MESSAGES,
        }

    def _route_groups(self, transport: str, version: str) -> tuple[dict[str, Any], ...]:
        groups: list[dict[str, Any]] = []
        grouped_routes: dict[str, list[MonitorRouteDefinition]] = {}
        for route in self._routes:
            if route.transport != transport:
                continue
            grouped_routes.setdefault(route.display_path(version), []).append(route)

        for path, routes in grouped_routes.items():
            groups.append(
                {
                    "path": path,
                    "anchor": slugify(path),
                    "methods": tuple(
                        {
                            "method": route.method,
                            "description": route.description,
                            "input_schema": route.input_schema,
                            "output_schema": route.output_schema,
                            "handler": route.handler_name,
                        }
                        for route in routes
                    ),
                }
            )
        return tuple(groups)


DEVELOP_REFERENCE = DevelopReferenceRegistry()
_DOCUMENTED_ROUTE_ORDER = count()


MONITOR_WS_MESSAGES: tuple[dict[str, str], ...] = (
    {
        "kind": "Server Event",
        "name": "status",
        "anchor": "ws-event-status",
        "description": (
            "Sent immediately after WebSocket connection with full status. Later status events are "
            "lightweight unless a command explicitly publishes full status."
        ),
    },
    {
        "kind": "Server Event",
        "name": "telemetry",
        "anchor": "ws-event-telemetry",
        "description": (
            "Sent from cached simulator telemetry when RCT extracts monitor fields from simulator "
            "Bridge payloads. RCT_MONITOR_WS_HZ controls whether telemetry is immediate or periodic."
        ),
    },
    {
        "kind": "Server Event",
        "name": "frame",
        "anchor": "ws-event-frame",
        "description": (
            "Observation event for Socket.IO bridge traffic. It is disabled by default and enabled "
            "with RCT_MONITOR_FRAME_EVENTS=true."
        ),
    },
    {
        "kind": "Server Event",
        "name": "accident-logs",
        "anchor": "ws-event-accident-logs",
        "description": "Published after accident log state changes or decision record updates.",
    },
    {
        "kind": "Server Event",
        "name": "audit-log",
        "anchor": "ws-event-audit-log",
        "description": "Published either as a full audit log list or as one new audit entry.",
    },
    {
        "kind": "Server Event",
        "name": "penalty-decision",
        "anchor": "ws-event-penalty-decision",
        "description": (
            "Published when a manual penalty-decision workflow starts, changes, completes, or is "
            "reset for a new simulator session."
        ),
    },
    {
        "kind": "Client Command",
        "name": "configure-devkits",
        "anchor": "ws-command-configure-devkits",
        "description": "Configures one or more DevKit endpoints from browser monitor clients.",
    },
    {
        "kind": "Client Command",
        "name": "connect-devkit",
        "anchor": "ws-command-connect-devkit",
        "description": "Connects one configured DevKit bridge slot.",
    },
    {
        "kind": "Client Command",
        "name": "disconnect-devkit",
        "anchor": "ws-command-disconnect-devkit",
        "description": "Disconnects one configured DevKit bridge slot.",
    },
)


def build_develop_reference(version: str) -> dict[str, Any]:
    return DEVELOP_REFERENCE.reference(version)


def install_develop_reference_route_collector(
    router: Any,
    registry: DevelopReferenceRegistry = DEVELOP_REFERENCE,
) -> None:
    for method in DOCUMENTED_ROUTE_METHODS:
        add_method_name = f"add_{method.lower()}"
        original_add_method = getattr(router, add_method_name, None)
        if original_add_method is None:
            continue
        if getattr(original_add_method, "__rct_develop_reference_collector__", False):
            continue

        def add_with_reference(
            path: object,
            handler: Callable[..., Any],
            *args: Any,
            _method: str = method,
            _original_add_method: Callable[..., Any] = original_add_method,
            **kwargs: Any,
        ) -> Any:
            documentation, route_args = split_documentation_arg(args)
            registry.record_route(
                _method,
                path,
                handler,
                documentation["description"],
                documentation.get("input_schema"),
                documentation.get("output_schema"),
            )
            return _original_add_method(path, handler, *route_args, **kwargs)

        setattr(add_with_reference, "__rct_develop_reference_collector__", True)
        setattr(router, add_method_name, add_with_reference)


def split_documentation_arg(args: tuple[Any, ...]) -> tuple[dict[str, Any], tuple[Any, ...]]:
    if args and isinstance(args[0], str):
        return {"description": args[0]}, args[1:]
    if args and is_route_documentation(args[0]):
        return dict(args[0]), args[1:]
    return {"description": ""}, args


def is_route_documentation(value: object) -> bool:
    return isinstance(value, dict) and isinstance(value.get("description"), str)


def route_doc(
    description: str,
    *,
    input_schema: dict[str, Any] | None = None,
    output_schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    documentation: dict[str, Any] = {"description": description}
    if input_schema is not None:
        documentation["input_schema"] = input_schema
    if output_schema is not None:
        documentation["output_schema"] = output_schema
    return documentation


def monitor_input_schema(
    *,
    path: dict[str, Any] | None = None,
    query: dict[str, Any] | None = None,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "path": path or object_schema({"version": string_schema(enum=("0.1", "latest"))}, required=("version",)),
            "query": query or object_schema({}),
            "body": body or {"type": "null"},
        },
        "required": ["path", "query", "body"],
        "additionalProperties": False,
    }


def object_schema(
    properties: dict[str, Any],
    *,
    required: tuple[str, ...] = (),
    additional_properties: bool | dict[str, Any] = True,
) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": additional_properties,
    }
    if required:
        schema["required"] = list(required)
    return schema


def array_schema(items: dict[str, Any]) -> dict[str, Any]:
    return {"type": "array", "items": items}


def string_schema(*, enum: tuple[str, ...] = ()) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "string"}
    if enum:
        schema["enum"] = list(enum)
    return schema


BOOLEAN_SCHEMA: dict[str, str] = {"type": "boolean"}
NUMBER_SCHEMA: dict[str, str] = {"type": "number"}
INTEGER_SCHEMA: dict[str, str] = {"type": "integer"}
ANY_OBJECT_SCHEMA = object_schema({})
OK_RESPONSE_SCHEMA = object_schema({"ok": BOOLEAN_SCHEMA}, required=("ok",))
BINARY_MCAP_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "string",
    "contentEncoding": "binary",
    "contentMediaType": "application/octet-stream",
}


STATUS_RESPONSE_SCHEMA = object_schema(
    {
        "protocol": string_schema(),
        "transport": string_schema(),
        "requested_version": string_schema(),
        "version": string_schema(),
        "latest": string_schema(),
        "aliases": object_schema({}),
        "state": ANY_OBJECT_SCHEMA,
    },
    required=("protocol", "transport", "requested_version", "version", "latest", "aliases", "state"),
)


TOPICS_RESPONSE_SCHEMA = object_schema(
    {
        "protocol": string_schema(),
        "version": string_schema(),
        "topics": array_schema(ANY_OBJECT_SCHEMA),
        "topic_selections": object_schema({}, additional_properties=BOOLEAN_SCHEMA),
    },
    required=("protocol", "version", "topics", "topic_selections"),
)


TOPICS_UPDATE_INPUT_SCHEMA = monitor_input_schema(
    body=object_schema(
        {
            "topic_selections": object_schema({}, additional_properties=BOOLEAN_SCHEMA),
            "topics": object_schema({}, additional_properties=BOOLEAN_SCHEMA),
        }
    )
)


SETTINGS_RESPONSE_SCHEMA = object_schema(
    {
        "protocol": string_schema(),
        "version": string_schema(),
    },
    required=("protocol", "version"),
)


ACCIDENT_LOGS_RESPONSE_SCHEMA = object_schema(
    {
        "protocol": string_schema(),
        "version": string_schema(),
        "accident_logs": array_schema(ANY_OBJECT_SCHEMA),
    },
    required=("protocol", "version", "accident_logs"),
)


AUDIT_LOG_RESPONSE_SCHEMA = object_schema(
    {
        "protocol": string_schema(),
        "version": string_schema(),
        "audit_log": array_schema(ANY_OBJECT_SCHEMA),
    },
    required=("protocol", "version", "audit_log"),
)


STATE_COMMAND_RESPONSE_SCHEMA = object_schema(
    {
        "ok": BOOLEAN_SCHEMA,
        "state": ANY_OBJECT_SCHEMA,
    },
    required=("ok", "state"),
)


ACCIDENT_LOG_FILENAME_PATH_SCHEMA = object_schema(
    {
        "version": string_schema(enum=("0.1", "latest")),
        "filename": string_schema(),
    },
    required=("version", "filename"),
    additional_properties=False,
)


def normalize_route_path(path: object) -> str | None:
    if not isinstance(path, str):
        return None
    return path.split("?", 1)[0]


def transport_for_path(path: str) -> str | None:
    if path.startswith(MONITOR_REST_ROUTE_PREFIX):
        return "REST"
    if path.startswith(MONITOR_WS_ROUTE_PREFIX):
        return "WS"
    return None


def slugify(text: str) -> str:
    slug = text.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-") or "section"
