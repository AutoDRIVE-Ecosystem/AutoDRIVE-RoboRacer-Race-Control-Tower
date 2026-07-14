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
            "common_schemas": COMMON_SCHEMAS,
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
        "description": "Request input shape split by URL path parameters, query string parameters, and JSON body.",
        "properties": {
            "path": path
            or object_schema(
                {"version": string_schema(enum=("0.1", "latest"), description="Requested monitor protocol version.")},
                required=("version",),
                description="Path parameters captured from the route.",
            ),
            "query": query or object_schema({}, description="Query string parameters."),
            "body": body or {"type": "null", "description": "No JSON request body is expected."},
        },
        "required": ["path", "query", "body"],
        "additionalProperties": False,
    }


def object_schema(
    properties: dict[str, Any],
    *,
    required: tuple[str, ...] = (),
    additional_properties: bool | dict[str, Any] = True,
    description: str = "",
) -> dict[str, Any]:
    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": additional_properties,
    }
    if description:
        schema["description"] = description
    if required:
        schema["required"] = list(required)
    return schema


def array_schema(items: dict[str, Any], *, description: str = "") -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "array", "items": items}
    if description:
        schema["description"] = description
    return schema


def string_schema(*, enum: tuple[str, ...] = (), description: str = "") -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "string"}
    if description:
        schema["description"] = description
    if enum:
        schema["enum"] = list(enum)
    return schema


BOOLEAN_SCHEMA: dict[str, Any] = {"type": "boolean", "description": "Boolean true or false value."}
NUMBER_SCHEMA: dict[str, Any] = {"type": "number", "description": "Numeric value."}
INTEGER_SCHEMA: dict[str, Any] = {"type": "integer", "description": "Integer value."}
ANY_OBJECT_SCHEMA = object_schema({}, description="Object with endpoint-specific fields.")
OK_RESPONSE_SCHEMA = object_schema(
    {"ok": {"type": "boolean", "description": "Whether the command was accepted."}},
    required=("ok",),
    description="Generic command acknowledgement.",
)
BINARY_MCAP_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "string",
    "description": "Binary MCAP download. The response body is not JSON.",
    "contentEncoding": "binary",
    "contentMediaType": "application/octet-stream",
}


MONITOR_PROTOCOL_SCHEMA = object_schema(
    {
        "name": string_schema(description="Monitor protocol name."),
        "version": string_schema(description="Resolved monitor protocol version."),
    },
    required=("name", "version"),
    additional_properties=False,
    description="Monitor protocol identity included in status payloads.",
)


DEVKIT_STATE_SCHEMA = object_schema(
    {
        "name": string_schema(description="Internal DevKit slot name."),
        "vehicle_id": INTEGER_SCHEMA,
        "url": string_schema(description="Configured DevKit bridge URL."),
        "host": string_schema(description="Active DevKit bridge host."),
        "port": INTEGER_SCHEMA,
        "configured": BOOLEAN_SCHEMA,
        "enabled": BOOLEAN_SCHEMA,
        "connected": BOOLEAN_SCHEMA,
        "queued_messages": INTEGER_SCHEMA,
        "bridge_hz": NUMBER_SCHEMA,
        "bridge_per_minute": INTEGER_SCHEMA,
    },
    description="One configured DevKit bridge slot.",
)


ACCIDENT_RECORDER_SCHEMA = object_schema(
    {
        "pre_accident_seconds": NUMBER_SCHEMA,
        "include_camera": BOOLEAN_SCHEMA,
    },
    description="Accident recorder settings.",
)


PENALTY_RULE_SCHEMA = object_schema(
    {
        "restart_delay_seconds": NUMBER_SCHEMA,
        "decision_pack_version": string_schema(enum=("v1", "v2"), description="Active decision rule package."),
        "sw_analysis": object_schema({}, additional_properties=BOOLEAN_SCHEMA, description="Software-analysis rule toggles."),
        "decision_pack_v2": ANY_OBJECT_SCHEMA,
    },
    description="Penalty rule settings.",
)


RACING_RULE_SCHEMA = object_schema(
    {
        "total_lap_count": INTEGER_SCHEMA,
        "maximum_penalty_count": INTEGER_SCHEMA,
        "celebration_with_confetti": BOOLEAN_SCHEMA,
    },
    description="Race completion and celebration settings.",
)


AUDIT_RULE_SCHEMA = object_schema(
    {
        "bridge_hz_maximum": NUMBER_SCHEMA,
        "bridge_hz_minimum": NUMBER_SCHEMA,
        "bridge_hz_drop_percent": NUMBER_SCHEMA,
    },
    description="Bridge-rate audit thresholds.",
)


PENALTY_DECISION_SCHEMA = object_schema(
    {
        "active": BOOLEAN_SCHEMA,
        "collision_vehicle_ids": array_schema(INTEGER_SCHEMA, description="Vehicles involved in the pending collision."),
        "filtered_vehicle_ids": array_schema(INTEGER_SCHEMA, description="Vehicles currently filtered by penalty control."),
        "penalty_vehicle_id": {"type": ["integer", "null"], "description": "Vehicle selected to receive a penalty."},
        "victim_vehicle_id": {"type": ["integer", "null"], "description": "Vehicle selected as the victim, if known."},
        "release_delay_seconds": NUMBER_SCHEMA,
    },
    description="Manual penalty-decision workflow state.",
)


RACE_RESULT_SCHEMA = object_schema(
    {
        "active": BOOLEAN_SCHEMA,
        "winner_vehicle_id": {"type": ["integer", "null"], "description": "Race winner vehicle id."},
        "loser_vehicle_id": {"type": ["integer", "null"], "description": "Race loser vehicle id."},
        "reason": {"type": ["string", "null"], "description": "Reason the race result was decided."},
    },
    description="Race result state.",
)


STATUS_STATE_SCHEMA = object_schema(
    {
        "monitor_protocol": MONITOR_PROTOCOL_SCHEMA,
        "trace_lidar_vehicle_ids": array_schema(INTEGER_SCHEMA, description="Vehicles with decoded LiDAR telemetry enabled."),
        "revision": INTEGER_SCHEMA,
        "simulator_clients": INTEGER_SCHEMA,
        "monitor_clients": INTEGER_SCHEMA,
        "devkits": array_schema(DEVKIT_STATE_SCHEMA, description="Configured DevKit slots."),
        "accident_recorder": ACCIDENT_RECORDER_SCHEMA,
        "penalty_rule": PENALTY_RULE_SCHEMA,
        "racing_rule": RACING_RULE_SCHEMA,
        "audit_rule": AUDIT_RULE_SCHEMA,
        "penalty_decision": PENALTY_DECISION_SCHEMA,
        "vehicle_penalties": object_schema({}, additional_properties=INTEGER_SCHEMA, description="Penalty count by vehicle id string."),
        "race_result": RACE_RESULT_SCHEMA,
        "review_time_seconds": NUMBER_SCHEMA,
        "simulator_socketio_path": string_schema(description="Socket.IO path used by simulator clients."),
    },
    description="Full status payload shared by REST metadata and WebSocket status events.",
)


COMMON_SCHEMAS: tuple[dict[str, Any], ...] = (
    {
        "name": "Status State",
        "anchor": "common-schema-status-state",
        "description": "Full monitor state object returned as REST metadata state and sent in full status events.",
        "schema": STATUS_STATE_SCHEMA,
    },
    {
        "name": "DevKit State",
        "anchor": "common-schema-devkit-state",
        "description": "Shape of one entry in status.devkits.",
        "schema": DEVKIT_STATE_SCHEMA,
    },
    {
        "name": "Penalty Decision",
        "anchor": "common-schema-penalty-decision",
        "description": "Manual penalty-decision workflow object included in status payloads.",
        "schema": PENALTY_DECISION_SCHEMA,
    },
    {
        "name": "Race Result",
        "anchor": "common-schema-race-result",
        "description": "Race result object included in status payloads.",
        "schema": RACE_RESULT_SCHEMA,
    },
)


STATUS_RESPONSE_SCHEMA = object_schema(
    {
        "protocol": string_schema(description="Monitor protocol name."),
        "transport": string_schema(description="Transport used for this response."),
        "requested_version": string_schema(description="Version segment requested by the client."),
        "version": string_schema(description="Resolved monitor protocol version."),
        "latest": string_schema(description="Latest concrete protocol version supported by RCT."),
        "aliases": object_schema({}, description="Convenience URLs for latest, versioned, and WebSocket endpoints."),
        "state": STATUS_STATE_SCHEMA,
    },
    required=("protocol", "transport", "requested_version", "version", "latest", "aliases", "state"),
    description="Protocol metadata and full monitor state snapshot.",
)


TOPICS_RESPONSE_SCHEMA = object_schema(
    {
        "protocol": string_schema(description="Monitor protocol name."),
        "version": string_schema(description="Resolved monitor protocol version."),
        "topics": array_schema(ANY_OBJECT_SCHEMA, description="Available simulator bridge topics."),
        "topic_selections": object_schema(
            {},
            additional_properties={"type": "boolean", "description": "Whether the topic is enabled."},
            description="Map from topic name to frontend selection state.",
        ),
    },
    required=("protocol", "version", "topics", "topic_selections"),
    description="Topic options and current topic selections.",
)


TOPICS_UPDATE_INPUT_SCHEMA = monitor_input_schema(
    body=object_schema(
        {
            "topic_selections": object_schema(
                {},
                additional_properties={"type": "boolean", "description": "Whether the topic should be enabled."},
                description="Preferred map from topic name to enabled state.",
            ),
            "topics": object_schema(
                {},
                additional_properties={"type": "boolean", "description": "Whether the topic should be enabled."},
                description="Alias for topic_selections.",
            ),
        },
        description="JSON body for updating one or more topic selections.",
    )
)


SETTINGS_RESPONSE_SCHEMA = object_schema(
    {
        "protocol": string_schema(description="Monitor protocol name."),
        "version": string_schema(description="Resolved monitor protocol version."),
    },
    required=("protocol", "version"),
    description="Common prefix for settings GET responses. Endpoint-specific settings are included as additional fields.",
)


ACCIDENT_LOGS_RESPONSE_SCHEMA = object_schema(
    {
        "protocol": string_schema(description="Monitor protocol name."),
        "version": string_schema(description="Resolved monitor protocol version."),
        "accident_logs": array_schema(ANY_OBJECT_SCHEMA, description="Accident log records newest first."),
    },
    required=("protocol", "version", "accident_logs"),
    description="Accident log listing response.",
)


AUDIT_LOG_RESPONSE_SCHEMA = object_schema(
    {
        "protocol": string_schema(description="Monitor protocol name."),
        "version": string_schema(description="Resolved monitor protocol version."),
        "audit_log": array_schema(ANY_OBJECT_SCHEMA, description="Audit log entries in recorded order."),
    },
    required=("protocol", "version", "audit_log"),
    description="Audit log response.",
)


STATE_COMMAND_RESPONSE_SCHEMA = object_schema(
    {
        "ok": {"type": "boolean", "description": "Whether the command was accepted."},
        "state": object_schema({}, description="Updated monitor state snapshot."),
    },
    required=("ok", "state"),
    description="Command response that includes updated monitor state.",
)


ACCIDENT_LOG_FILENAME_PATH_SCHEMA = object_schema(
    {
        "version": string_schema(enum=("0.1", "latest"), description="Requested monitor protocol version."),
        "filename": string_schema(description="Accident log basename from accident_logs[].filename."),
    },
    required=("version", "filename"),
    additional_properties=False,
    description="Path parameters for endpoints operating on one accident log file.",
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
