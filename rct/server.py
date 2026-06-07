# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

import asyncio
import base64
import gzip
import inspect
import json
import logging
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic
from typing import Any
from urllib.parse import quote, urlparse, urlunparse

import socketio
from socketio import packet as socketio_packet
from aiohttp import WSMsgType, web

from .accident_recorder import AccidentRecorder, list_accident_logs
from .audit_recorder import AuditLogRecord, AuditRecorder, list_audit_logs
from .accident_summary import accident_log_compact_summary_from_mcap, accident_log_summary_from_mcap, replay_lidar_ranges_payload
from .bridge import (
    BridgeHistory,
    BridgeRateTracker,
    ControlCache,
    extract_collision_counts,
    extract_lidar_range_arrays,
    extract_lidar_scans,
    extract_monitor_telemetry,
)
from .config import Settings, load_settings
from .decision import (
    load_decision_record,
    save_decision_record,
)
from .monitor import MonitorEventHub, safe_send
from .monitor_protocol import (
    MONITOR_PROTOCOL_LATEST,
    MONITOR_PROTOCOL_VERSION,
    MONITOR_REST_TRANSPORT,
    MONITOR_WS_TRANSPORT,
    is_monitor_rest_path,
    is_monitor_ws_path,
    parse_monitor_path,
)
from .protocol import (
    DROP_VALUE,
    rewrite_devkit_payload_to_simulator,
    rewrite_simulator_payload_to_devkit,
)
from .ros2_mcap import convert_accident_mcap_to_ros2_mcap
from .state import (
    DEFAULT_DECISION_PACK_V2_COLLISION_TYPE_SETTINGS,
    DEFAULT_DECISION_PACK_V2_GRAPH_SETTINGS,
    DEFAULT_PENALTY_SW_ANALYSIS_SETTINGS,
    AccidentLogMonitorState,
    AuditLogMonitorState,
    DevKitMonitorState,
    RaceControlState,
)
from .static_files import build_static_file_response

LOGGER = logging.getLogger("rct")
FRONTEND_ROOT = Path(__file__).resolve().parent.parent / "frontend"
SOCKETIO_PATH = "socket.io"
BRIDGE_OMITTED_KEY_PARTS = ("lidar", "camera", "array", "image")
FRONT_CAMERA_IMAGE_KEYS = ("V1 Front Camera Image", "V2 Front Camera Image")
DEFAULT_BRIDGE_HZ_SPIKE_PERCENT = 25.0
BRIDGE_HZ_SPIKE_LOOKBACK_SECONDS = 1.0
BRIDGE_HZ_AUDIT_HISTORY_SECONDS = 3.0
WHITE_FRONT_CAMERA_JPEG_BASE64 = (
"/9j/4AAQSkZJRgABAQEBLAEsAAD/2wBDAP//////////////////////////////////////////"
"////////////////////////////////////////////2wBDAf//////////////////////////"
"////////////////////////////////////////////////////////////wgARCAAQABADAREA"
"AhEBAxEB/8QAFQABAQAAAAAAAAAAAAAAAAAAAAL/xAAUAQEAAAAAAAAAAAAAAAAAAAAA/9oADAMB"
"AAIQAxAAAAGgAf/EABQQAQAAAAAAAAAAAAAAAAAAACD/2gAIAQEAAQUCH//EABQRAQAAAAAAAAAA"
"AAAAAAAAACD/2gAIAQMBAT8BH//EABQRAQAAAAAAAAAAAAAAAAAAACD/2gAIAQIBAT8BH//EABQQ"
"AQAAAAAAAAAAAAAAAAAAACD/2gAIAQEABj8CH//EABQQAQAAAAAAAAAAAAAAAAAAACD/2gAIAQEA"
"AT8hH//aAAwDAQACAAMAAAAQAA//xAAUEQEAAAAAAAAAAAAAAAAAAAAg/9oACAEDAQE/EB//xAAU"
"EQEAAAAAAAAAAAAAAAAAAAAg/9oACAECAQE/EB//xAAUEAEAAAAAAAAAAAAAAAAAAAAg/9oACAEB"
"AAE/EB//2Q=="
)
PENALTY_RELEASE_DELAY_SECONDS = 2.0
CONTROL_FILTER_FIELDS = ("Throttle", "Steering")
ANSI_RED = "\033[31m"
ANSI_BLUE = "\033[34m"
ANSI_GRAY = "\033[90m"
ANSI_RESET = "\033[0m"
TOPIC_OPTIONS: tuple[dict[str, Any], ...] = (
    {"topic": "/autodrive/roboracer_1/best_lap_time", "access": "restricted"},
    {"topic": "/autodrive/roboracer_1/collision_count", "access": "restricted"},
    {"topic": "/autodrive/roboracer_1/front_camera", "access": "input"},
    {"topic": "/autodrive/roboracer_1/imu", "access": "input"},
    {"topic": "/autodrive/roboracer_1/ips", "access": "restricted"},
    {"topic": "/autodrive/roboracer_1/lap_count", "access": "restricted"},
    {"topic": "/autodrive/roboracer_1/lap_time", "access": "restricted"},
    {"topic": "/autodrive/roboracer_1/last_lap_time", "access": "restricted"},
    {"topic": "/autodrive/roboracer_1/left_encoder", "access": "input"},
    {"topic": "/autodrive/roboracer_1/lidar", "access": "input"},
    {"topic": "/autodrive/roboracer_1/right_encoder", "access": "input"},
    {"topic": "/autodrive/roboracer_1/speed", "access": "restricted"},
    {"topic": "/autodrive/roboracer_1/steering", "access": "input"},
    {"topic": "/autodrive/roboracer_1/steering_command", "access": "output"},
    {"topic": "/autodrive/roboracer_1/throttle", "access": "input"},
    {"topic": "/autodrive/roboracer_1/throttle_command", "access": "output"},
    {"topic": "/autodrive/reset_command", "access": "restricted"},
    {"topic": "/tf", "access": "restricted"},
)
RECOMMENDED_OFF_TOPICS = frozenset({"/autodrive/roboracer_1/front_camera"})
TOPIC_TO_BRIDGE_FIELD_SUFFIXES: dict[str, tuple[str, ...]] = {
    "/autodrive/roboracer_1/throttle": ("Throttle",),
    "/autodrive/roboracer_1/steering": ("Steering",),
    "/autodrive/roboracer_1/imu": (
        "Orientation Quaternion",
        "Orientation Euler Angles",
        "Linear Velocity",
        "Angular Velocity",
        "Linear Acceleration",
    ),
    "/autodrive/roboracer_1/lidar": (
        "LIDAR Scan Rate",
        "LIDAR Range Array",
        "LIDAR Intensity Array",
    ),
    "/autodrive/roboracer_1/ips": ("Position",),
    "/autodrive/roboracer_1/lap_count": ("Lap Count",),
    "/autodrive/roboracer_1/lap_time": ("Lap Time",),
    "/autodrive/roboracer_1/last_lap_time": ("Last Lap Time",),
    "/autodrive/roboracer_1/best_lap_time": ("Best Lap Time",),
    "/autodrive/roboracer_1/collision_count": ("Collisions",),
}
TOPICS_IGNORED_FOR_DEVKIT_BRIDGE = frozenset(
    {
        "/autodrive/roboracer_1/left_encoder",
        "/autodrive/roboracer_1/right_encoder",
        "/autodrive/roboracer_1/speed",
        "/autodrive/roboracer_1/steering_command",
        "/autodrive/roboracer_1/throttle_command",
        "/autodrive/reset_command",
        "/tf",
    }
)
KNOWN_DECISION_PACKAGE_IDS = frozenset(
    [
        *DEFAULT_PENALTY_SW_ANALYSIS_SETTINGS,
        *DEFAULT_DECISION_PACK_V2_COLLISION_TYPE_SETTINGS,
    ]
)
ZERO_LIDAR_RANGE_ARRAY_BASE64 = base64.b64encode(
    gzip.compress("\n".join(["0.0"] * 1080).encode("utf-8"))
).decode("ascii")
EMPTY_GZIP_BASE64 = base64.b64encode(gzip.compress(b"")).decode("ascii")
BRIDGE_FIELD_DEFAULTS_BY_SUFFIX: dict[str, str] = {
    "Throttle": "0.0",
    "Steering": "0.0",
    "Position": "0.0 0.0 0.0",
    "Orientation Quaternion": "0.0 0.0 0.0 0.0",
    "Orientation Euler Angles": "0.0 0.0 0.0",
    "Linear Velocity": "0.0 0.0 0.0",
    "Angular Velocity": "0.0 0.0 0.0",
    "Linear Acceleration": "0.0 0.0 0.0",
    "LIDAR Scan Rate": "40.0",
    "LIDAR Range Array": ZERO_LIDAR_RANGE_ARRAY_BASE64,
    "LIDAR Intensity Array": EMPTY_GZIP_BASE64,
    "Lap Count": "0",
    "Lap Time": "0.0",
    "Last Lap Time": "0.0",
    "Best Lap Time": "0.0",
    "Collisions": "0",
}


def configure_socketio_logging(settings: Settings) -> None:
    library_loggers = {
        "socketio.client": settings.debug_socketio_client,
        "engineio.client": settings.debug_engineio_client,
        "socketio.server": settings.debug_socketio_server,
        "engineio.server": settings.debug_engineio_server,
    }
    for logger_name, debug_enabled in library_loggers.items():
        logging.getLogger(logger_name).setLevel(logging.INFO if debug_enabled else logging.WARNING)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def other_vehicle_id(vehicle_id: int) -> int:
    return 2 if vehicle_id == 1 else 1


def envelope(event: str, **fields: Any) -> str:
    return json.dumps(
        {
            "event": event,
            "timestamp": utc_now(),
            **fields,
        },
        separators=(",", ":"),
    )


def normalize_socketio_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme == "ws":
        parsed = parsed._replace(scheme="http")
    elif parsed.scheme == "wss":
        parsed = parsed._replace(scheme="https")
    return urlunparse(parsed)


def socketio_data_from_args(args: tuple[Any, ...]) -> Any:
    if not args:
        return None
    if len(args) == 1:
        return args[0]
    return args


def encode_socketio_arg(value: Any) -> dict[str, Any]:
    if isinstance(value, bytes):
        return {
            "encoding": "base64",
            "payload": base64.b64encode(value).decode("ascii"),
        }

    try:
        json.dumps(value)
    except (TypeError, ValueError):
        return {"encoding": "text", "payload": str(value)}
    return {"encoding": "json", "payload": value}


def preview_debug_value(value: Any, max_chars: int) -> str:
    if isinstance(value, bytes):
        preview = f"<bytes len={len(value)}>"
    else:
        preview = str(value)

    if max_chars > 0 and len(preview) > max_chars:
        return f"{preview[:max_chars]}... <truncated {len(preview) - max_chars} chars>"
    return preview


def bridge_log_payload(args: tuple[Any, ...], max_chars: int) -> str:
    payload: Any
    if len(args) == 1:
        payload = args[0]
    else:
        payload = list(args)

    redacted = redact_bridge_payload(payload)
    try:
        preview = json.dumps(redacted, ensure_ascii=False, indent=2, default=repr)
    except (TypeError, ValueError):
        preview = repr(redacted)

    if max_chars > 0 and len(preview) > max_chars:
        return f"{preview[:max_chars]}\n... <truncated {len(preview) - max_chars} chars>"
    return preview


def redact_bridge_payload(value: Any, parent_key: str = "") -> Any:
    if should_omit_bridge_value(parent_key):
        return omitted_bridge_value(value)

    if isinstance(value, dict):
        redacted: dict[Any, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            redacted[key] = (
                omitted_bridge_value(item)
                if should_omit_bridge_value(key_text)
                else redact_bridge_payload(item, key_text)
            )
        return redacted

    if isinstance(value, list):
        return [redact_bridge_payload(item, parent_key) for item in value]
    if isinstance(value, tuple):
        return [redact_bridge_payload(item, parent_key) for item in value]
    if isinstance(value, bytes):
        return f"<bytes omitted len={len(value)}>"
    return value


def should_omit_bridge_value(key: str) -> bool:
    key = key.lower()
    return any(part in key for part in BRIDGE_OMITTED_KEY_PARTS)


def omitted_bridge_value(value: Any) -> str:
    try:
        size = len(value)
    except TypeError:
        return "<omitted>"
    return f"<omitted len={size}>"


def bridge_field_size(payload: Any, key: str) -> int | None:
    if not isinstance(payload, dict):
        return None
    value = payload.get(key)
    try:
        return len(value)
    except TypeError:
        return None


def bridge_front_camera_fields(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    return {key: payload[key] for key in FRONT_CAMERA_IMAGE_KEYS if key in payload}


def replace_front_camera_fields(payload: Any, value: str) -> Any:
    if not isinstance(payload, dict):
        return payload
    if not any(key in payload for key in FRONT_CAMERA_IMAGE_KEYS):
        return payload

    replaced_payload = dict(payload)
    for key in FRONT_CAMERA_IMAGE_KEYS:
        if key in replaced_payload:
            replaced_payload[key] = value
    return replaced_payload


def bridge_history_payload(payload: Any, empty_front_camera: bool = False) -> Any:
    if not empty_front_camera:
        return payload
    return replace_front_camera_fields(payload, "")


def color_arrow(text: str, color: str) -> str:
    return f"{color}{text}{ANSI_RESET}"


def decode_monitor_arg(value: Any, encoding: str = "json") -> Any:
    if encoding == "base64":
        if not isinstance(value, str):
            raise ValueError("base64 payload must be a string")
        return base64.b64decode(value)
    if encoding == "text":
        return str(value)
    return value


def rewrite_args_for_devkit(args: tuple[Any, ...], vehicle_id: int) -> tuple[Any, ...] | None:
    rewritten: list[Any] = []
    for arg in args:
        item = rewrite_simulator_payload_to_devkit(arg, vehicle_id)
        if item is DROP_VALUE:
            return None
        rewritten.append(item)
    return tuple(rewritten)


def rewrite_args_for_simulator(args: tuple[Any, ...], vehicle_id: int) -> tuple[Any, ...]:
    return tuple(rewrite_devkit_payload_to_simulator(arg, vehicle_id) for arg in args)


def audit_monitor_state_from_record(record: AuditLogRecord) -> AuditLogMonitorState:
    return AuditLogMonitorState(
        index=record.index,
        timestamp_ns=record.timestamp_ns,
        time=record.time,
        event_type=record.event_type,
        text=record.text,
        race_number=record.race_number,
        kind=record.kind,
        accident_log_filename=record.accident_log_filename,
        accident_log_time=record.accident_log_time,
        decision_mode=record.decision_mode,
        decision_result=record.decision_result,
        memo=record.memo,
    )


def devkit_url_from_host_port(host: str, port: int) -> str:
    return f"ws://{host}:{port}"


def devkit_endpoint_key(host: str, port: int) -> tuple[str, int]:
    return (host.strip().lower(), port)


def devkit_endpoint_from_url(url: str) -> tuple[str, int] | None:
    parsed = urlparse(url)
    try:
        port = parsed.port
    except ValueError:
        return None
    if parsed.hostname is None or port is None:
        return None
    return parsed.hostname, port


def default_topic_selections() -> dict[str, bool]:
    return {
        option["topic"]: option["access"] != "restricted" and option["topic"] not in RECOMMENDED_OFF_TOPICS
        for option in TOPIC_OPTIONS
    }


def ros2_mcap_download_filename(filename: str) -> str:
    if filename.endswith(".mcap"):
        return f"{filename[:-5]}_ros2.mcap"
    return f"{filename}_ros2.mcap"


def remote_mcap_cors_headers() -> dict[str, str]:
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
        "Access-Control-Allow-Headers": "Accept, Content-Type, Range",
        "Access-Control-Expose-Headers": "Accept-Ranges, Content-Length, Content-Range",
        "Accept-Ranges": "bytes",
    }


def mcap_range_response(body: bytes, request: web.Request, headers: dict[str, str]) -> web.Response | None:
    range_header = request.headers.get("Range")
    if not range_header:
        return None
    if not range_header.startswith("bytes="):
        return web.Response(status=416, headers={**headers, "Content-Range": f"bytes */{len(body)}"})
    range_spec = range_header.removeprefix("bytes=").split(",", 1)[0].strip()
    start_text, separator, end_text = range_spec.partition("-")
    if separator != "-":
        return web.Response(status=416, headers={**headers, "Content-Range": f"bytes */{len(body)}"})
    try:
        if start_text:
            start = int(start_text)
            end = int(end_text) if end_text else len(body) - 1
        else:
            suffix_length = int(end_text)
            start = max(0, len(body) - suffix_length)
            end = len(body) - 1
    except ValueError:
        return web.Response(status=416, headers={**headers, "Content-Range": f"bytes */{len(body)}"})
    if start < 0 or end < start or start >= len(body):
        return web.Response(status=416, headers={**headers, "Content-Range": f"bytes */{len(body)}"})
    end = min(end, len(body) - 1)
    partial = body[start : end + 1]
    return web.Response(
        body=partial,
        status=206,
        headers={
            **headers,
            "Content-Length": str(len(partial)),
            "Content-Range": f"bytes {start}-{end}/{len(body)}",
        },
    )


@dataclass
class BridgeHzAuditVehicleState:
    history: deque[tuple[float, float]] = field(default_factory=deque)
    high_active: bool = False
    low_active: bool = False
    spike_direction: str | None = None


@dataclass(frozen=True)
class BridgeHzAuditEvent:
    event_type: str
    text: str


class BridgeHzAuditTracker:
    def __init__(
        self,
        *,
        history_seconds: float = BRIDGE_HZ_AUDIT_HISTORY_SECONDS,
        spike_lookback_seconds: float = BRIDGE_HZ_SPIKE_LOOKBACK_SECONDS,
    ) -> None:
        self.history_seconds = history_seconds
        self.spike_lookback_seconds = spike_lookback_seconds
        self._states: dict[int, BridgeHzAuditVehicleState] = {}

    def evaluate(
        self,
        *,
        vehicle_id: int,
        vehicle_label: str,
        bridge_hz: float,
        connected: bool,
        settings: dict[str, Any],
        now: float,
    ) -> list[BridgeHzAuditEvent]:
        state = self._states.setdefault(vehicle_id, BridgeHzAuditVehicleState())
        if not connected:
            state.history.clear()
            state.high_active = False
            state.low_active = False
            state.spike_direction = None
            return []

        maximum = float(settings["bridge_hz_maximum"])
        minimum = float(settings["bridge_hz_minimum"])
        spike_ratio = float(settings["bridge_hz_spike_percent"]) / 100.0
        events: list[BridgeHzAuditEvent] = []

        if bridge_hz >= maximum:
            if not state.high_active:
                events.append(
                    BridgeHzAuditEvent(
                        "bridge_hz",
                        f"Bridge Hz above maximum: {vehicle_label} {bridge_hz:.1f} Hz >= {maximum:.1f} Hz.",
                    )
                )
            state.high_active = True
        else:
            state.high_active = False

        if bridge_hz <= minimum:
            if not state.low_active:
                events.append(
                    BridgeHzAuditEvent(
                        "bridge_hz",
                        f"Bridge Hz below minimum: {vehicle_label} {bridge_hz:.1f} Hz <= {minimum:.1f} Hz.",
                    )
                )
            state.low_active = True
        else:
            state.low_active = False

        baseline = self._sample_at_or_before(state.history, now - self.spike_lookback_seconds)
        if baseline is not None:
            baseline_time, baseline_hz = baseline
            if now - baseline_time >= self.spike_lookback_seconds * 0.75 and baseline_hz > 0:
                delta = bridge_hz - baseline_hz
                ratio = abs(delta) / baseline_hz
                direction = "increase" if delta > 0 else "decrease"
                if ratio >= spike_ratio and direction != state.spike_direction:
                    events.append(
                        BridgeHzAuditEvent(
                            "bridge_hz",
                            (
                                f"Bridge Hz spike: {vehicle_label} {baseline_hz:.1f} Hz -> "
                                f"{bridge_hz:.1f} Hz ({delta / baseline_hz:+.1%}) over {now - baseline_time:.1f}s."
                            ),
                        )
                    )
                    state.spike_direction = direction
                elif ratio < spike_ratio:
                    state.spike_direction = None
            else:
                state.spike_direction = None

        state.history.append((now, bridge_hz))
        self._prune(state.history, now)
        return events

    def _sample_at_or_before(
        self,
        history: deque[tuple[float, float]],
        target_time: float,
    ) -> tuple[float, float] | None:
        sample = None
        for entry in history:
            if entry[0] > target_time:
                break
            sample = entry
        return sample

    def _prune(self, history: deque[tuple[float, float]], now: float) -> None:
        cutoff = now - self.history_seconds
        while history and history[0][0] < cutoff:
            history.popleft()


@dataclass
class DevKitConnection:
    name: str
    vehicle_id: int
    url: str
    settings: Settings
    tower: "RaceControlTower"
    queue: asyncio.Queue[tuple[str, tuple[Any, ...]]] = field(init=False)
    control_queue: asyncio.Queue[tuple[float, tuple[Any, ...]]] = field(init=False)
    client: socketio.AsyncClient = field(init=False)
    host: str = ""
    port: int | None = None
    configured: bool = False
    enabled: bool = True
    connected: bool = False
    awaiting_initial_bridge: bool = False
    _run_task: asyncio.Task[None] | None = None
    _send_task: asyncio.Task[None] | None = None
    _control_task: asyncio.Task[None] | None = None

    def __post_init__(self) -> None:
        self.queue = asyncio.Queue(maxsize=self.settings.client_queue_size)
        self.control_queue = asyncio.Queue(maxsize=self.settings.client_queue_size)
        self.client = socketio.AsyncClient(
            logger=self.settings.debug_socketio_client,
            engineio_logger=self.settings.debug_engineio_client,
            reconnection=False,
        )
        self._register_handlers()

    def _register_handlers(self) -> None:
        async def on_connect() -> None:
            connected_changed = self.tower.set_devkit_connected(self, True)
            LOGGER.info("%s connected to %s", self.name, self.url)
            if connected_changed:
                await self.tower.record_devkit_connection_audit(self, connected=True)
            self.awaiting_initial_bridge = not await self.tower.send_cached_incoming_bridge(self)
            await self.tower.publish_status()

        async def on_disconnect(*_: Any) -> None:
            connected_changed = self.tower.set_devkit_connected(self, False)
            if connected_changed:
                LOGGER.info("%s disconnected from %s", self.name, self.url)
                await self.tower.record_devkit_connection_audit(self, connected=False)
                await self.tower.publish_status()

        async def on_message(data: Any) -> None:
            await self.tower.handle_devkit_event(self, "message", (data,))

        async def on_bridge(*args: Any) -> None:
            await self.tower.handle_devkit_event(self, "Bridge", args)

        async def on_any_event(event: str, *args: Any) -> None:
            await self.tower.handle_devkit_event(self, event, args)

        self.client.on("connect", on_connect)
        self.client.on("disconnect", on_disconnect)
        self.client.on("message", on_message)
        self.client.on("Bridge", on_bridge)
        self.client.on("*", on_any_event)

    def start(self) -> None:
        if not self.configured or not self.enabled or not self.tower.has_simulators:
            return
        if self._run_task is None or self._run_task.done():
            self._run_task = asyncio.create_task(self.run(), name=f"{self.name}:connect")
        if self._send_task is None or self._send_task.done():
            self._send_task = asyncio.create_task(self.send_loop(), name=f"{self.name}:send")
        if self._control_task is None or self._control_task.done():
            self._control_task = asyncio.create_task(self.control_loop(), name=f"{self.name}:control")

    def _client_connected(self) -> bool:
        connected = getattr(self.client, "connected", None)
        if connected is True:
            return True

        namespaces = getattr(self.client, "namespaces", None)
        if isinstance(namespaces, dict):
            return "/" in namespaces or bool(namespaces)
        if namespaces:
            return True

        eio_connected = getattr(self.client.eio, "state", "disconnected") == "connected"
        if connected is False:
            return False
        return eio_connected

    async def configure(self, host: str, port: int) -> None:
        url = devkit_url_from_host_port(host, port)
        if self.url != url:
            await self.stop()
        self.host = host
        self.port = port
        self.url = url
        self.configured = True
        self.tower.set_devkit_endpoint(self)

    async def stop(self) -> None:
        tasks = [task for task in (self._run_task, self._send_task, self._control_task) if task is not None]
        for task in tasks:
            task.cancel()

        if self._client_connected():
            await self.client.disconnect()

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        self._run_task = None
        self._send_task = None
        self._control_task = None
        self.awaiting_initial_bridge = False
        if self.connected:
            connected_changed = self.tower.set_devkit_connected(self, False)
            if connected_changed:
                await self.tower.record_devkit_connection_audit(self, connected=False)
            await self.tower.publish_status()

    async def enqueue(self, event: str, args: tuple[Any, ...]) -> None:
        if self.queue.full():
            _ = self.queue.get_nowait()
            self.queue.task_done()
            LOGGER.warning("%s outbound queue full; dropped oldest event", self.name)

        await self.queue.put((event, args))
        self.tower.update_devkit_queue(self)

    async def enqueue_control(self, timestamp: float, args: tuple[Any, ...]) -> None:
        if self.control_queue.full():
            _ = self.control_queue.get_nowait()
            self.control_queue.task_done()
            LOGGER.warning("%s control queue full; dropped oldest Bridge event", self.name)

        await self.control_queue.put((timestamp, args))

    async def run(self) -> None:
        while self.tower.has_simulators and self.configured and self.enabled:
            if not self._client_connected():
                eio_state = getattr(self.client.eio, "state", "disconnected")
                if eio_state != "disconnected":
                    LOGGER.warning(
                        "%s has Engine.IO state %s without Socket.IO namespace; disconnecting before reconnect",
                        self.name,
                        eio_state,
                    )
                    await self.client.disconnect()

                try:
                    connect_kwargs: dict[str, Any] = {
                        "url": normalize_socketio_url(self.url),
                        "transports": ["websocket"],
                        "socketio_path": SOCKETIO_PATH,
                    }
                    if "wait_timeout" in inspect.signature(self.client.connect).parameters:
                        connect_kwargs["wait_timeout"] = self.settings.ping_timeout_seconds
                    await self.client.connect(**connect_kwargs)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self.tower.set_devkit_connected(self, False)
                    LOGGER.warning("%s could not connect to %s: %s", self.name, self.url, exc)

            await asyncio.sleep(self.settings.reconnect_delay_seconds)

    async def send_loop(self) -> None:
        while True:
            event, args = await self.queue.get()
            try:
                while not self._client_connected():
                    await asyncio.sleep(0.05)

                data = socketio_data_from_args(args)
                if event == "message":
                    await self.client.send(data)
                else:
                    await self.client.emit(event, data=data)
            finally:
                self.queue.task_done()
                self.tower.update_devkit_queue(self)

    async def control_loop(self) -> None:
        while True:
            timestamp, args = await self.control_queue.get()
            try:
                await self.tower.process_devkit_bridge_control(self, timestamp, args)
            finally:
                self.control_queue.task_done()


class RaceControlTower:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.state = RaceControlState()
        self.simulator_sids: set[str] = set()
        self.monitor_hub = MonitorEventHub()
        self.bridge_history = BridgeHistory(settings.bridge_history_seconds)
        self.accident_recorder = AccidentRecorder()
        self.audit_recorder = AuditRecorder(self.accident_recorder.output_dir)
        self.control_cache = ControlCache()
        self.bridge_rates = BridgeRateTracker()
        self.bridge_hz_audit = BridgeHzAuditTracker()
        self.latest_front_camera_fields: dict[str, Any] = {}
        self.collision_counts: dict[int, int] = {}
        self.filtered_control_vehicle_ids: set[int] = set()
        self._penalty_release_tasks: dict[int, asyncio.Task[None]] = {}
        self.trace_lidar_vehicle_ids: set[int] = set()
        self.monitor_vehicle_positions: dict[int, dict[str, Any]] = {}
        self.monitor_vehicle_telemetry: dict[int, dict[str, Any]] = {}
        self.monitor_ws_interval = 1.0 / settings.monitor_ws_hz if settings.monitor_ws_hz > 0 else 0.0
        self.bridge_rate_refresh_interval = 0.25
        self._monitor_stream_task: asyncio.Task[None] | None = None
        self._bridge_rate_refresh_task: asyncio.Task[None] | None = None
        self._audit_lock = asyncio.Lock()
        self.sio = socketio.AsyncServer(
            async_mode="aiohttp",
            cors_allowed_origins="*",
            logger=settings.debug_socketio_server,
            engineio_logger=settings.debug_engineio_server,
            max_http_buffer_size=settings.max_message_size or 100_000_000,
            ping_interval=(settings.ping_interval_seconds, settings.ping_timeout_seconds),
            ping_timeout=settings.ping_timeout_seconds,
        )
        self.devkits = [
            DevKitConnection(f"devkit:{index}", vehicle_id, url, settings, self)
            for index, (url, vehicle_id) in enumerate(
                zip(settings.devkit_urls, settings.devkit_vehicle_ids, strict=True),
                start=1,
            )
        ]
        for devkit in self.devkits:
            endpoint = devkit_endpoint_from_url(devkit.url)
            if endpoint is None:
                LOGGER.warning("%s URL %r does not include a valid host and port", devkit.name, devkit.url)
                continue
            devkit.host, devkit.port = endpoint
            devkit.configured = True
        self.state.configure_devkits(
            DevKitMonitorState(
                devkit.name,
                devkit.vehicle_id,
                devkit.url,
                devkit.host,
                devkit.port,
                devkit.configured,
                devkit.enabled,
            )
            for devkit in self.devkits
        )
        self.state.set_topic_selections(default_topic_selections())
        self.refresh_accident_logs_from_disk()
        self.refresh_audit_log_from_disk()
        self._register_socketio_handlers()
        self._register_engineio_compat_handlers()

    @property
    def has_simulators(self) -> bool:
        return bool(self.simulator_sids)

    def start_monitor_stream(self) -> None:
        if self.monitor_ws_interval <= 0:
            return
        if self._monitor_stream_task is None or self._monitor_stream_task.done():
            self._monitor_stream_task = asyncio.create_task(
                self.monitor_stream_loop(),
                name="monitor-ws-stream",
            )

    def start_bridge_rate_refresh(self) -> None:
        if self._bridge_rate_refresh_task is None or self._bridge_rate_refresh_task.done():
            self._bridge_rate_refresh_task = asyncio.create_task(
                self.bridge_rate_refresh_loop(),
                name="bridge-rate-refresh",
            )

    async def monitor_stream_loop(self) -> None:
        while True:
            await asyncio.sleep(self.monitor_ws_interval)
            if not self.monitor_hub.client_count:
                continue
            await self.send_monitor_now(self.status_message(full=False))
            telemetry_message = self.cached_telemetry_message()
            if telemetry_message is not None:
                await self.send_monitor_now(telemetry_message)

    async def bridge_rate_refresh_loop(self) -> None:
        while True:
            await asyncio.sleep(self.bridge_rate_refresh_interval)
            now = monotonic()
            changed = self.refresh_bridge_rates(now=now)
            await self.audit_bridge_rates(now=now)
            if changed and self.monitor_hub.client_count:
                await self.publish_status()

    async def start(self) -> None:
        app = self.create_app()
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, self.settings.host, self.settings.port)
        await site.start()
        LOGGER.info("RCT aiohttp/socket.io server listening on %s:%s", self.settings.host, self.settings.port)
        try:
            self.start_monitor_stream()
            self.start_bridge_rate_refresh()
            await asyncio.Future()
        finally:
            if self._monitor_stream_task is not None:
                self._monitor_stream_task.cancel()
            if self._bridge_rate_refresh_task is not None:
                self._bridge_rate_refresh_task.cancel()
            await self.disconnect_all_devkits()
            await runner.cleanup()

    def create_app(self) -> web.Application:
        app = web.Application(
            client_max_size=self.settings.max_message_size or 1024**3,
            middlewares=[self.log_socketio_request],
        )
        self.sio.attach(app, socketio_path=SOCKETIO_PATH)
        app.router.add_get("/monitor/WS/{version}", self.handle_monitor_ws)
        app.router.add_get("/monitor/REST/{version}", self.handle_monitor_rest)
        app.router.add_get("/monitor/REST/{version}/topics", self.handle_monitor_topics_get)
        app.router.add_post("/monitor/REST/{version}/topics", self.handle_monitor_topics_post)
        app.router.add_get(
            "/monitor/REST/{version}/accident-recorder",
            self.handle_monitor_accident_recorder_get,
        )
        app.router.add_post(
            "/monitor/REST/{version}/accident-recorder",
            self.handle_monitor_accident_recorder_post,
        )
        app.router.add_get(
            "/monitor/REST/{version}/penalty-rule",
            self.handle_monitor_penalty_rule_get,
        )
        app.router.add_post(
            "/monitor/REST/{version}/penalty-rule",
            self.handle_monitor_penalty_rule_post,
        )
        app.router.add_get(
            "/monitor/REST/{version}/racing-rule",
            self.handle_monitor_racing_rule_get,
        )
        app.router.add_post(
            "/monitor/REST/{version}/racing-rule",
            self.handle_monitor_racing_rule_post,
        )
        app.router.add_get(
            "/monitor/REST/{version}/audit-rule",
            self.handle_monitor_audit_rule_get,
        )
        app.router.add_post(
            "/monitor/REST/{version}/audit-rule",
            self.handle_monitor_audit_rule_post,
        )
        app.router.add_get(
            "/monitor/REST/{version}/accident-logs",
            self.handle_monitor_accident_logs_get,
        )
        app.router.add_get(
            "/monitor/REST/{version}/accident-logs/ros2-mcap",
            self.handle_monitor_accident_log_ros2_mcap_get,
        )
        app.router.add_get(
            "/monitor/REST/{version}/accident-logs/{filename}/rct.mcap",
            self.handle_monitor_accident_log_rct_mcap_file_get,
        )
        app.router.add_get(
            "/monitor/REST/{version}/accident-logs/{filename}",
            self.handle_monitor_accident_log_ros2_mcap_file_get,
        )
        app.router.add_get(
            "/monitor/REST/{version}/accident-logs/{filename}/ros2.mcap",
            self.handle_monitor_accident_log_ros2_mcap_file_get,
        )
        app.router.add_options(
            "/monitor/REST/{version}/accident-logs/ros2-mcap",
            self.handle_monitor_accident_log_ros2_mcap_options,
        )
        app.router.add_options(
            "/monitor/REST/{version}/accident-logs/{filename}",
            self.handle_monitor_accident_log_ros2_mcap_options,
        )
        app.router.add_options(
            "/monitor/REST/{version}/accident-logs/{filename}/ros2.mcap",
            self.handle_monitor_accident_log_ros2_mcap_options,
        )
        app.router.add_options(
            "/monitor/REST/{version}/accident-logs/{filename}/rct.mcap",
            self.handle_monitor_accident_log_ros2_mcap_options,
        )
        app.router.add_get(
            "/monitor/REST/{version}/accident-logs/{filename}/summary",
            self.handle_monitor_accident_log_summary_get,
        )
        app.router.add_post(
            "/monitor/REST/{version}/accident-logs/{filename}/decision-record",
            self.handle_monitor_accident_log_decision_record_post,
        )
        app.router.add_delete(
            "/monitor/REST/{version}/accident-logs",
            self.handle_monitor_accident_logs_delete,
        )
        app.router.add_get(
            "/monitor/REST/{version}/audit-log",
            self.handle_monitor_audit_log_get,
        )
        app.router.add_post(
            "/monitor/REST/{version}/devkits/{vehicle_id}/endpoint",
            self.handle_monitor_devkit_endpoint_command,
        )
        app.router.add_post(
            "/monitor/REST/{version}/devkits/{vehicle_id}/{action}",
            self.handle_monitor_devkit_command,
        )
        app.router.add_post(
            "/monitor/REST/{version}/vehicles/{vehicle_id}/trace-lidar",
            self.handle_monitor_trace_lidar_command,
        )
        app.router.add_route("*", "/monitor/{tail:.*}", self.handle_unknown_monitor_path)
        app.router.add_get("/{tail:.*}", self.handle_static)
        return app

    @web.middleware
    async def log_socketio_request(
        self,
        request: web.Request,
        handler: web.RequestHandler,
    ) -> web.StreamResponse:
        if request.path.rstrip("/") == f"/{SOCKETIO_PATH}":
            LOGGER.info(
                "socket.io request remote=%s method=%s path=%s query=%s upgrade=%s",
                request.remote or "unknown",
                request.method,
                request.path,
                request.query_string,
                request.headers.get("Upgrade", ""),
            )
        return await handler(request)

    def _register_socketio_handlers(self) -> None:
        async def connect(sid: str, environ: dict[str, Any], auth: Any = None) -> bool:
            first_simulator = not self.simulator_sids
            self.simulator_sids.add(sid)
            self.state.set_simulator_clients(len(self.simulator_sids))
            if first_simulator:
                self.state.start_race_time()
                await self.record_audit_event(
                    event_type="race_start",
                    text="Race started: simulator connected.",
                )
            reset_penalty_decision = self.reset_penalty_decision_for_simulator_session()
            LOGGER.info("simulator connected via Socket.IO sid=%s", sid)
            if reset_penalty_decision:
                LOGGER.info("cleared pending penalty decision for new simulator session")
            self.connect_all_devkits()
            await self.publish_status()
            if reset_penalty_decision:
                await self.broadcast_monitor(
                    envelope(
                        "penalty-decision",
                        source="rct",
                        active=False,
                        collision_vehicle_ids=[],
                        filtered_vehicle_ids=[],
                        reset_reason="simulator-connected",
                        review_time_seconds=self.state.review_time_seconds(),
                        release_delay_seconds=float(
                            self.state.penalty_rule_settings()["restart_delay_seconds"]
                        ),
                    )
                )
                await self.broadcast_monitor(
                    envelope(
                        "race-result",
                        source="rct",
                        active=False,
                        winner_vehicle_id=None,
                        loser_vehicle_id=None,
                        reason=None,
                        reset_reason="simulator-connected",
                    )
                )
            return True

        async def disconnect(sid: str, reason: str | None = None) -> None:
            self.simulator_sids.discard(sid)
            self.state.set_simulator_clients(len(self.simulator_sids))
            LOGGER.info("simulator disconnected sid=%s reason=%s", sid, reason)
            if not self.simulator_sids:
                race_ended_by_disconnect = not self.state.race_result().get("active")
                self.state.stop_race_time()
                self.state.stop_review_time()
                if race_ended_by_disconnect:
                    await self.record_audit_event(
                        event_type="race_end",
                        text="Race ended: simulator disconnected.",
                    )
                await self.disconnect_all_devkits()
            await self.publish_status()

        async def message(sid: str, data: Any) -> None:
            await self.handle_simulator_event(sid, "message", (data,))

        async def bridge(sid: str, *args: Any) -> None:
            await self.handle_simulator_event(sid, "Bridge", args)

        async def any_event(event: str, sid: str, *args: Any) -> None:
            await self.handle_simulator_event(sid, event, args)

        self.sio.on("connect", connect)
        self.sio.on("disconnect", disconnect)
        self.sio.on("message", message)
        self.sio.on("Bridge", bridge)
        self.sio.on("*", any_event)

    def _register_engineio_compat_handlers(self) -> None:
        original_message_handler = self.sio.eio.handlers["message"]

        async def compat_message(eio_sid: str, data: Any) -> Any:
            if self.settings.debug_engineio_messages:
                LOGGER.info(
                    "engine.io message sid=%s data=%s",
                    eio_sid,
                    preview_debug_value(data, self.settings.debug_engineio_max_chars),
                )

            await self._ensure_socketio_namespace_for_event(eio_sid, data)
            result = original_message_handler(eio_sid, data)
            if inspect.isawaitable(result):
                return await result
            return result

        self.sio.eio.handlers["message"] = compat_message

    async def _ensure_socketio_namespace_for_event(self, eio_sid: str, data: Any) -> None:
        try:
            packet_class = getattr(self.sio, "packet_class", socketio_packet.Packet)
            packet = packet_class(encoded_packet=data)
        except (TypeError, ValueError):
            return

        if packet.packet_type != socketio_packet.EVENT:
            return

        namespace = packet.namespace or "/"
        sid = self._socketio_sid_from_eio_sid(eio_sid, namespace)
        if sid is not None and self.sio.manager.is_connected(sid, namespace):
            return

        event = packet.data[0] if isinstance(packet.data, list) and packet.data else "unknown"
        LOGGER.info(
            "implicit Socket.IO connect for event-before-connect eio_sid=%s namespace=%s event=%s",
            eio_sid,
            namespace,
            event,
        )
        await self._handle_implicit_socketio_connect(eio_sid, namespace)

    def _socketio_sid_from_eio_sid(self, eio_sid: str, namespace: str) -> str | None:
        sid_from_eio_sid = getattr(self.sio.manager, "sid_from_eio_sid", None)
        if callable(sid_from_eio_sid):
            return sid_from_eio_sid(eio_sid, namespace)
        return eio_sid

    async def _handle_implicit_socketio_connect(self, eio_sid: str, namespace: str) -> None:
        handle_connect = self.sio._handle_connect
        parameters = inspect.signature(handle_connect).parameters
        if len(parameters) >= 3:
            result = handle_connect(eio_sid, namespace, None)
        else:
            result = handle_connect(eio_sid, namespace)
        if inspect.isawaitable(result):
            await result

    async def handle_static(self, request: web.Request) -> web.Response:
        static_response = build_static_file_response(request.rel_url.raw_path, FRONTEND_ROOT)
        return web.Response(
            status=static_response.status_code,
            reason=static_response.reason_phrase,
            headers=dict(static_response.headers),
            body=static_response.body,
        )

    async def handle_unknown_monitor_path(self, request: web.Request) -> web.Response:
        return web.json_response({"error": "unsupported monitor protocol path"}, status=404)

    async def handle_monitor_rest(self, request: web.Request) -> web.Response:
        if not is_monitor_rest_path(request.path):
            return web.json_response({"error": "unsupported monitor protocol path"}, status=404)

        monitor_path = parse_monitor_path(request.path)
        if monitor_path is None:
            return web.json_response({"error": "unsupported monitor protocol path"}, status=404)

        return web.json_response(
            {
                "protocol": "autodrive-rct-monitor",
                "transport": MONITOR_REST_TRANSPORT,
                "requested_version": monitor_path.requested_version,
                "version": monitor_path.resolved_version,
                "latest": MONITOR_PROTOCOL_VERSION,
                "aliases": {
                    "latest": f"/monitor/{MONITOR_REST_TRANSPORT}/{MONITOR_PROTOCOL_LATEST}",
                    "versioned": f"/monitor/{MONITOR_REST_TRANSPORT}/{MONITOR_PROTOCOL_VERSION}",
                    "events": f"/monitor/{MONITOR_WS_TRANSPORT}/{MONITOR_PROTOCOL_LATEST}",
                },
                "state": self.status_payload(full=True),
            }
        )

    async def handle_monitor_topics_get(self, request: web.Request) -> web.Response:
        version_path = f"/monitor/REST/{request.match_info['version']}"
        if not is_monitor_rest_path(version_path):
            return web.json_response({"error": "unsupported monitor protocol version"}, status=404)

        return web.json_response(
            {
                "protocol": "autodrive-rct-monitor",
                "version": MONITOR_PROTOCOL_VERSION,
                "topics": self.topic_options_payload(),
                "topic_selections": self.state.topic_selections(),
            }
        )

    async def handle_monitor_topics_post(self, request: web.Request) -> web.Response:
        version_path = f"/monitor/REST/{request.match_info['version']}"
        if not is_monitor_rest_path(version_path):
            return web.json_response({"error": "unsupported monitor protocol version"}, status=404)

        try:
            body = await request.json()
        except (json.JSONDecodeError, ValueError):
            body = {}

        topic_selections = body.get("topic_selections", body.get("topics"))
        if not isinstance(topic_selections, dict):
            return web.json_response({"error": "topic_selections must be an object"}, status=400)

        try:
            validated_topic_selections = self.validate_topic_selections(topic_selections)
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400)

        self.state.update_topic_selections(validated_topic_selections)
        await self.publish_full_status()
        return web.json_response(
            {
                "ok": True,
                "topics": self.topic_options_payload(),
                "topic_selections": self.state.topic_selections(),
            }
        )

    async def handle_monitor_accident_recorder_get(self, request: web.Request) -> web.Response:
        version_path = f"/monitor/REST/{request.match_info['version']}"
        if not is_monitor_rest_path(version_path):
            return web.json_response({"error": "unsupported monitor protocol version"}, status=404)

        return web.json_response(
            {
                "protocol": "autodrive-rct-monitor",
                "version": MONITOR_PROTOCOL_VERSION,
                "accident_recorder": self.state.accident_recorder_settings(),
            }
        )

    async def handle_monitor_accident_recorder_post(self, request: web.Request) -> web.Response:
        version_path = f"/monitor/REST/{request.match_info['version']}"
        if not is_monitor_rest_path(version_path):
            return web.json_response({"error": "unsupported monitor protocol version"}, status=404)

        try:
            body = await request.json()
        except (json.JSONDecodeError, ValueError):
            body = {}

        try:
            settings = self.validate_accident_recorder_settings(body)
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400)

        self.state.set_accident_recorder_settings(**settings)
        await self.publish_full_status()
        return web.json_response(
            {
                "ok": True,
                "accident_recorder": self.state.accident_recorder_settings(),
            }
        )

    async def handle_monitor_penalty_rule_get(self, request: web.Request) -> web.Response:
        version_path = f"/monitor/REST/{request.match_info['version']}"
        if not is_monitor_rest_path(version_path):
            return web.json_response({"error": "unsupported monitor protocol version"}, status=404)

        return web.json_response(
            {
                "protocol": "autodrive-rct-monitor",
                "version": MONITOR_PROTOCOL_VERSION,
                "penalty_rule": self.state.penalty_rule_settings(),
            }
        )

    async def handle_monitor_penalty_rule_post(self, request: web.Request) -> web.Response:
        version_path = f"/monitor/REST/{request.match_info['version']}"
        if not is_monitor_rest_path(version_path):
            return web.json_response({"error": "unsupported monitor protocol version"}, status=404)

        try:
            body = await request.json()
        except (json.JSONDecodeError, ValueError):
            body = {}

        try:
            settings = self.validate_penalty_rule_settings(body)
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400)

        self.state.set_penalty_rule_settings(**settings)
        await self.publish_full_status()
        return web.json_response(
            {
                "ok": True,
                "penalty_rule": self.state.penalty_rule_settings(),
            }
        )

    async def handle_monitor_racing_rule_get(self, request: web.Request) -> web.Response:
        version_path = f"/monitor/REST/{request.match_info['version']}"
        if not is_monitor_rest_path(version_path):
            return web.json_response({"error": "unsupported monitor protocol version"}, status=404)

        return web.json_response(
            {
                "protocol": "autodrive-rct-monitor",
                "version": MONITOR_PROTOCOL_VERSION,
                "racing_rule": self.state.racing_rule_settings(),
            }
        )

    async def handle_monitor_racing_rule_post(self, request: web.Request) -> web.Response:
        version_path = f"/monitor/REST/{request.match_info['version']}"
        if not is_monitor_rest_path(version_path):
            return web.json_response({"error": "unsupported monitor protocol version"}, status=404)

        try:
            body = await request.json()
        except (json.JSONDecodeError, ValueError):
            body = {}

        try:
            settings = self.validate_racing_rule_settings(body)
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400)

        self.state.set_racing_rule_settings(**settings)
        await self.publish_full_status()
        return web.json_response(
            {
                "ok": True,
                "racing_rule": self.state.racing_rule_settings(),
            }
        )

    async def handle_monitor_audit_rule_get(self, request: web.Request) -> web.Response:
        version_path = f"/monitor/REST/{request.match_info['version']}"
        if not is_monitor_rest_path(version_path):
            return web.json_response({"error": "unsupported monitor protocol version"}, status=404)

        return web.json_response(
            {
                "protocol": "autodrive-rct-monitor",
                "version": MONITOR_PROTOCOL_VERSION,
                "audit_rule": self.state.audit_rule_settings(),
            }
        )

    async def handle_monitor_audit_rule_post(self, request: web.Request) -> web.Response:
        version_path = f"/monitor/REST/{request.match_info['version']}"
        if not is_monitor_rest_path(version_path):
            return web.json_response({"error": "unsupported monitor protocol version"}, status=404)

        try:
            body = await request.json()
        except (json.JSONDecodeError, ValueError):
            body = {}

        try:
            settings = self.validate_audit_rule_settings(body)
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400)

        self.state.set_audit_rule_settings(**settings)
        await self.publish_full_status()
        return web.json_response(
            {
                "ok": True,
                "audit_rule": self.state.audit_rule_settings(),
            }
        )

    async def handle_monitor_accident_logs_get(self, request: web.Request) -> web.Response:
        version_path = f"/monitor/REST/{request.match_info['version']}"
        if not is_monitor_rest_path(version_path):
            return web.json_response({"error": "unsupported monitor protocol version"}, status=404)

        self.refresh_accident_logs_from_disk()
        return web.json_response(
            {
                "protocol": "autodrive-rct-monitor",
                "version": MONITOR_PROTOCOL_VERSION,
                "accident_logs": self.state.accident_logs(),
            }
        )

    async def handle_monitor_accident_log_ros2_mcap_get(self, request: web.Request) -> web.Response:
        version_path = f"/monitor/REST/{request.match_info['version']}"
        if not is_monitor_rest_path(version_path):
            return web.json_response({"error": "unsupported monitor protocol version"}, status=404)

        path_param = request.query.get("path")
        if not path_param:
            return web.json_response({"error": "path is required"}, status=400)

        try:
            path = self.resolve_accident_log_path(path_param)
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400)

        if not path.is_file():
            return web.json_response({"error": "accident log not found"}, status=404)

        return await self.ros2_mcap_response_for_path(path, request)

    async def handle_monitor_accident_log_ros2_mcap_file_get(self, request: web.Request) -> web.Response:
        version_path = f"/monitor/REST/{request.match_info['version']}"
        if not is_monitor_rest_path(version_path):
            return web.json_response({"error": "unsupported monitor protocol version"}, status=404)

        try:
            path = self.accident_log_path_from_filename(request.match_info["filename"])
        except ValueError as exc:
            status = 404 if str(exc) == "accident log not found" else 400
            return web.json_response({"error": str(exc)}, status=status)

        return await self.ros2_mcap_response_for_path(path, request)

    async def handle_monitor_accident_log_rct_mcap_file_get(self, request: web.Request) -> web.Response:
        version_path = f"/monitor/REST/{request.match_info['version']}"
        if not is_monitor_rest_path(version_path):
            return web.json_response({"error": "unsupported monitor protocol version"}, status=404)

        try:
            path = self.accident_log_path_from_filename(request.match_info["filename"])
        except ValueError as exc:
            status = 404 if str(exc) == "accident log not found" else 400
            return web.json_response({"error": str(exc)}, status=status)

        body = await asyncio.to_thread(path.read_bytes)
        headers = {
            "Content-Type": "application/octet-stream",
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(path.name)}",
            **remote_mcap_cors_headers(),
        }
        range_response = mcap_range_response(body, request, headers)
        if range_response is not None:
            return range_response
        return web.Response(body=body, headers=headers)

    async def ros2_mcap_response_for_path(self, path: Path, request: web.Request) -> web.Response:
        try:
            body = await asyncio.to_thread(convert_accident_mcap_to_ros2_mcap, path)
        except Exception:
            LOGGER.exception("failed to convert accident log to ROS2 MCAP from %s", path)
            return web.json_response({"error": "failed to convert accident log to ROS2 MCAP"}, status=500)

        filename = ros2_mcap_download_filename(path.name)
        quoted_filename = quote(filename)
        headers = {
            **remote_mcap_cors_headers(),
            "Content-Type": "application/octet-stream",
            "Content-Disposition": f"attachment; filename=\"{filename}\"; filename*=UTF-8''{quoted_filename}",
        }
        range_response = mcap_range_response(body, request, headers)
        if range_response is not None:
            return range_response
        return web.Response(
            body=body,
            headers={**headers, "Content-Length": str(len(body))},
        )

    async def handle_monitor_accident_log_ros2_mcap_options(self, request: web.Request) -> web.Response:
        version_path = f"/monitor/REST/{request.match_info['version']}"
        if not is_monitor_rest_path(version_path):
            return web.json_response({"error": "unsupported monitor protocol version"}, status=404)
        return web.Response(status=204, headers=remote_mcap_cors_headers())

    async def handle_monitor_accident_log_summary_get(self, request: web.Request) -> web.Response:
        version_path = f"/monitor/REST/{request.match_info['version']}"
        if not is_monitor_rest_path(version_path):
            return web.json_response({"error": "unsupported monitor protocol version"}, status=404)

        try:
            path = self.accident_log_path_from_filename(request.match_info["filename"])
        except ValueError as exc:
            status = 404 if str(exc) == "accident log not found" else 400
            return web.json_response({"error": str(exc)}, status=status)

        compact = request.query.get("frames", "").lower() in {"0", "false", "no"}
        try:
            include_lidar_scan = request.query.get("lidar", "").lower() not in {"0", "false", "no"}
            summary = (
                await asyncio.to_thread(accident_log_compact_summary_from_mcap, path)
                if compact
                else await asyncio.to_thread(self.accident_log_summary_from_mcap, path, include_lidar_scan=include_lidar_scan)
            )
        except Exception:
            LOGGER.exception("failed to read accident log summary from %s", path)
            return web.json_response({"error": "failed to read accident log summary"}, status=500)

        response = web.json_response(
            {
                "protocol": "autodrive-rct-monitor",
                "version": MONITOR_PROTOCOL_VERSION,
                **summary,
            }
        )
        response.enable_compression()
        return response

    async def handle_monitor_accident_log_decision_record_post(self, request: web.Request) -> web.Response:
        version_path = f"/monitor/REST/{request.match_info['version']}"
        if not is_monitor_rest_path(version_path):
            return web.json_response({"error": "unsupported monitor protocol version"}, status=404)

        try:
            path = self.accident_log_path_from_filename(request.match_info["filename"])
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400)

        try:
            body = await request.json()
        except (json.JSONDecodeError, ValueError):
            return web.json_response({"error": "request body must be JSON"}, status=400)

        package_ids = body.get("decision_package_ids", [])
        if not isinstance(package_ids, list) or not all(isinstance(item, str) and item in KNOWN_DECISION_PACKAGE_IDS for item in package_ids):
            return web.json_response({"error": "decision_package_ids must be known decision rule ids"}, status=400)
        decision_results = body.get("decision_results", {})
        if not isinstance(decision_results, dict):
            return web.json_response({"error": "decision_results must be an object"}, status=400)
        decision_io_version = body.get("decision_io_version", "0.1")
        if decision_io_version != "0.1":
            return web.json_response({"error": "unsupported decision_io_version"}, status=400)
        memo = body.get("memo", "")
        if not isinstance(memo, str):
            return web.json_response({"error": "memo must be a string"}, status=400)
        decision_mode = body.get("decision_mode", "manual")
        if decision_mode not in {"manual", "auto"}:
            return web.json_response({"error": "decision_mode must be manual or auto"}, status=400)
        no_decision = bool(body.get("no_decision", False))
        penalty_vehicle_id = body.get("penalty_vehicle_id")
        fault_vehicle_id = body.get("fault_vehicle_id", penalty_vehicle_id)
        if no_decision:
            penalty_vehicle_id = None
            fault_vehicle_id = None
        elif penalty_vehicle_id is not None:
            try:
                penalty_vehicle_id = int(penalty_vehicle_id)
            except (TypeError, ValueError):
                return web.json_response({"error": "penalty_vehicle_id must be an integer"}, status=400)
            if penalty_vehicle_id not in {1, 2}:
                return web.json_response({"error": "penalty_vehicle_id must be 1 or 2"}, status=400)
        if fault_vehicle_id is not None:
            try:
                fault_vehicle_id = int(fault_vehicle_id)
            except (TypeError, ValueError):
                return web.json_response({"error": "fault_vehicle_id must be an integer"}, status=400)
            if fault_vehicle_id not in {1, 2}:
                return web.json_response({"error": "fault_vehicle_id must be 1 or 2"}, status=400)

        penalty = None
        if penalty_vehicle_id is not None:
            delay_seconds = float(self.state.penalty_rule_settings()["restart_delay_seconds"])
            penalty = {
                "type": "late_start_delay",
                "vehicle_id": penalty_vehicle_id,
                "delay_seconds": delay_seconds,
                "label": f"{delay_seconds:g}s late start delay",
            }

        try:
            record = await asyncio.to_thread(
                save_decision_record,
                path,
                fault_vehicle_id=fault_vehicle_id,
                penalty=penalty,
                penalty_vehicle_id=penalty_vehicle_id,
                no_decision=no_decision,
                decision_package_ids=package_ids,
                decision_results=decision_results,
                memo=memo,
                decision_io_version=decision_io_version,
            )
        except Exception:
            LOGGER.exception("failed to save decision record for %s", path)
            return web.json_response({"error": "failed to save decision record"}, status=500)

        self.refresh_accident_logs_from_disk()
        await self.publish_accident_logs()
        await self.record_decision_audit(
            path,
            record,
            decision_mode=decision_mode,
        )
        return web.json_response({"ok": True, "decision_record": record})

    async def handle_monitor_accident_logs_delete(self, request: web.Request) -> web.Response:
        version_path = f"/monitor/REST/{request.match_info['version']}"
        if not is_monitor_rest_path(version_path):
            return web.json_response({"error": "unsupported monitor protocol version"}, status=404)

        deleted = 0
        output_dir = self.accident_recorder.output_dir
        keep_filename = request.query.get("keep", "")
        if output_dir.exists():
            for path in output_dir.glob("autodrive *.mcap"):
                if not path.is_file():
                    continue
                if keep_filename and path.name == keep_filename:
                    continue
                path.unlink()
                decision_path = path.with_suffix(".json")
                if decision_path.is_file():
                    decision_path.unlink()
                deleted += 1
        self.refresh_accident_logs_from_disk()
        await self.publish_accident_logs()
        await self.publish_status()
        return web.json_response(
            {
                "ok": True,
                "deleted": deleted,
                "accident_logs": self.state.accident_logs(),
            }
        )

    async def handle_monitor_audit_log_get(self, request: web.Request) -> web.Response:
        version_path = f"/monitor/REST/{request.match_info['version']}"
        if not is_monitor_rest_path(version_path):
            return web.json_response({"error": "unsupported monitor protocol version"}, status=404)

        self.refresh_audit_log_from_disk()
        return web.json_response(
            {
                "protocol": "autodrive-rct-monitor",
                "version": MONITOR_PROTOCOL_VERSION,
                "audit_log": self.state.audit_log(),
            }
        )

    async def handle_monitor_devkit_command(self, request: web.Request) -> web.Response:
        version_path = f"/monitor/REST/{request.match_info['version']}"
        if not is_monitor_rest_path(version_path):
            return web.json_response({"error": "unsupported monitor protocol version"}, status=404)

        try:
            vehicle_id = int(request.match_info["vehicle_id"])
        except ValueError:
            return web.json_response({"error": "vehicle_id must be an integer"}, status=400)

        devkit = self._get_devkit_by_vehicle_id(vehicle_id)
        if devkit is None:
            return web.json_response({"error": f"unknown vehicle_id {vehicle_id}"}, status=404)

        action = request.match_info["action"]
        if action == "connect":
            await self.connect_devkit(devkit)
        elif action == "disconnect":
            await self.disconnect_devkit(devkit)
        else:
            return web.json_response({"error": f"unsupported devkit action {action!r}"}, status=404)

        await self.publish_status()
        return web.json_response({"ok": True, "state": self.status_payload(full=True)})

    async def handle_monitor_devkit_endpoint_command(self, request: web.Request) -> web.Response:
        version_path = f"/monitor/REST/{request.match_info['version']}"
        if not is_monitor_rest_path(version_path):
            return web.json_response({"error": "unsupported monitor protocol version"}, status=404)

        try:
            vehicle_id = int(request.match_info["vehicle_id"])
        except ValueError:
            return web.json_response({"error": "vehicle_id must be an integer"}, status=400)

        devkit = self._get_devkit_by_vehicle_id(vehicle_id)
        if devkit is None:
            return web.json_response({"error": f"unknown vehicle_id {vehicle_id}"}, status=404)

        try:
            body = await request.json()
        except (json.JSONDecodeError, ValueError):
            body = {}

        enabled = body.get("enabled", True)
        if not isinstance(enabled, bool):
            return web.json_response({"error": "enabled must be a boolean"}, status=400)

        host = body.get("host", body.get("hostname"))
        port = body.get("port")
        if host is None or port is None:
            if enabled:
                return web.json_response({"error": "endpoint update requires host and port"}, status=400)
            await self.disconnect_devkit(devkit)
            await self.publish_full_status()
            return web.json_response({"ok": True, "state": self.status_payload(full=True)})

        if not isinstance(host, str) or not host.strip():
            return web.json_response({"error": "devkit host must be a non-empty string"}, status=400)

        try:
            port_number = int(port)
        except (TypeError, ValueError):
            return web.json_response({"error": "devkit port must be an integer"}, status=400)

        if port_number < 1 or port_number > 65535:
            return web.json_response({"error": "devkit port must be between 1 and 65535"}, status=400)

        try:
            if enabled:
                await self.configure_devkit(devkit, host.strip(), port_number, enabled=True)
            else:
                await devkit.configure(host.strip(), port_number)
                devkit.enabled = False
                self.state.set_devkit_enabled(devkit.name, False)
                await devkit.stop()
        except ValueError as exc:
            LOGGER.warning("monitor devkit endpoint update rejected: %s", exc)
            await self.broadcast_monitor(envelope("error", source="monitor", message=str(exc)))
            return web.json_response({"error": str(exc)}, status=400)

        await self.publish_full_status()
        return web.json_response({"ok": True, "state": self.status_payload(full=True)})

    async def handle_monitor_trace_lidar_command(self, request: web.Request) -> web.Response:
        version_path = f"/monitor/REST/{request.match_info['version']}"
        if not is_monitor_rest_path(version_path):
            return web.json_response({"error": "unsupported monitor protocol version"}, status=404)

        try:
            vehicle_id = int(request.match_info["vehicle_id"])
        except ValueError:
            return web.json_response({"error": "vehicle_id must be an integer"}, status=400)

        if self._get_devkit_by_vehicle_id(vehicle_id) is None:
            return web.json_response({"error": f"unknown vehicle_id {vehicle_id}"}, status=404)

        try:
            body = await request.json()
        except (json.JSONDecodeError, ValueError):
            body = {}

        enabled = body.get("enabled", body.get("trace_lidar", body.get("value")))
        if not isinstance(enabled, bool):
            return web.json_response({"error": "trace-lidar command requires boolean enabled"}, status=400)

        if enabled:
            self.trace_lidar_vehicle_ids.add(vehicle_id)
        else:
            self.trace_lidar_vehicle_ids.discard(vehicle_id)

        LOGGER.info("trace LiDAR V%s %s", vehicle_id, "enabled" if enabled else "disabled")
        await self.publish_status()
        return web.json_response({"ok": True, "vehicle_id": vehicle_id, "trace_lidar": enabled})

    async def handle_monitor_ws(self, request: web.Request) -> web.WebSocketResponse:
        if not is_monitor_ws_path(request.path):
            raise web.HTTPNotFound(text='{"error":"unsupported monitor protocol path"}')

        ws = web.WebSocketResponse()
        await ws.prepare(request)

        self.monitor_hub.add(ws)
        self.state.set_monitor_clients(self.monitor_hub.client_count)
        self.start_monitor_stream()
        self.start_bridge_rate_refresh()
        peer = request.remote or "unknown"
        LOGGER.info("monitor connected from %s", peer)
        await safe_send(ws, self.status_message(full=True))

        try:
            async for message in ws:
                if message.type == WSMsgType.TEXT:
                    await self.handle_monitor_message(message.data)
                elif message.type == WSMsgType.BINARY:
                    await self.broadcast_monitor(
                        envelope("error", source="monitor", message="binary monitor commands are not supported")
                    )
                elif message.type == WSMsgType.ERROR:
                    LOGGER.warning("monitor websocket error: %s", ws.exception())
        finally:
            self.monitor_hub.discard(ws)
            self.state.set_monitor_clients(self.monitor_hub.client_count)
            LOGGER.info("monitor disconnected from %s", peer)
            await self.publish_status()

        return ws

    def connect_all_devkits(self) -> None:
        for devkit in self.devkits:
            devkit.start()

    async def disconnect_all_devkits(self) -> None:
        await asyncio.gather(*(devkit.stop() for devkit in self.devkits), return_exceptions=True)

    def reset_penalty_decision_for_simulator_session(self) -> bool:
        self.collision_counts.clear()
        had_race_result = bool(self.state.race_result().get("active"))
        had_vehicle_penalties = bool(self.state.vehicle_penalties())
        decision = self.state.penalty_decision()
        had_pending_decision = bool(
            decision.get("active")
            or decision.get("collision_vehicle_ids")
            or decision.get("filtered_vehicle_ids")
            or self.filtered_control_vehicle_ids
            or self._penalty_release_tasks
        )
        if not had_pending_decision and not had_race_result and not had_vehicle_penalties:
            return False

        for task in self._penalty_release_tasks.values():
            task.cancel()
        self._penalty_release_tasks.clear()
        self.filtered_control_vehicle_ids.clear()
        self.state.reset_vehicle_penalties()
        self.state.set_race_result(active=False)
        self.state.stop_review_time()
        self.state.set_penalty_decision(
            active=False,
            collision_vehicle_ids=[],
            filtered_vehicle_ids=[],
            release_delay_seconds=float(self.state.penalty_rule_settings()["restart_delay_seconds"]),
        )
        return True

    async def configure_devkit(
        self,
        devkit: DevKitConnection,
        host: str,
        port: int,
        enabled: bool,
    ) -> None:
        if enabled:
            self.ensure_unique_devkit_endpoint(devkit, host, port)
        await devkit.configure(host, port)
        devkit.enabled = enabled
        self.state.set_devkit_enabled(devkit.name, enabled)
        if enabled:
            devkit.start()

    async def connect_devkit(
        self,
        devkit: DevKitConnection,
        host: str | None = None,
        port: int | None = None,
    ) -> None:
        if host is not None and port is not None:
            self.ensure_unique_devkit_endpoint(devkit, host, port)
            await devkit.configure(host, port)
        elif devkit.configured and devkit.port is not None:
            self.ensure_unique_devkit_endpoint(devkit, devkit.host, devkit.port)
        devkit.enabled = True
        self.state.set_devkit_enabled(devkit.name, True)
        devkit.start()

    async def disconnect_devkit(self, devkit: DevKitConnection) -> None:
        devkit.enabled = False
        self.state.set_devkit_enabled(devkit.name, False)
        await devkit.stop()

    def set_devkit_endpoint(self, devkit: DevKitConnection) -> None:
        if devkit.port is None:
            return
        self.state.set_devkit_endpoint(
            devkit.name,
            devkit.url,
            devkit.host,
            devkit.port,
            devkit.configured,
        )

    def ensure_unique_devkit_endpoint(self, target: DevKitConnection, host: str, port: int) -> None:
        target_key = devkit_endpoint_key(host, port)
        for devkit in self.devkits:
            if devkit is target or not devkit.enabled or not devkit.configured or devkit.port is None:
                continue
            if devkit_endpoint_key(devkit.host, devkit.port) == target_key:
                raise ValueError(
                    f"{target.name} endpoint {host.strip()}:{port} is already assigned to {devkit.name}"
                )

    async def handle_simulator_event(self, sid: str, event: str, args: tuple[Any, ...]) -> None:
        if sid not in self.simulator_sids:
            return

        if event == "Bridge":
            await self.handle_simulator_bridge_event(sid, args)
            return

        for devkit in self.devkits:
            rewritten_args = rewrite_args_for_devkit(args, devkit.vehicle_id)
            if rewritten_args is None:
                continue
            await devkit.enqueue(event, rewritten_args)

        await self.publish_simulator_telemetry(socketio_data_from_args(args), event)

    async def handle_simulator_bridge_event(self, sid: str, args: tuple[Any, ...]) -> None:
        if self.settings.log_bridge_messages:
            LOGGER.info(
                "simulator Bridge data sid=%s\n%s",
                sid,
                bridge_log_payload(args, self.settings.log_bridge_max_chars),
            )

        self.log_bridge_flow("sim-to-rct")
        raw_payload = socketio_data_from_args(args)
        self.latest_front_camera_fields = bridge_front_camera_fields(raw_payload)
        payload = raw_payload
        if self.settings.replace_front_camera_with_white_jpeg:
            payload = replace_front_camera_fields(raw_payload, WHITE_FRONT_CAMERA_JPEG_BASE64)
        if self.settings.log_bridge_field_sizes:
            LOGGER.info(
                "bridge sizes FC=(%s, %s) LR=(%s, %s) LA=(%s, %s)",
                bridge_field_size(payload, "V1 Front Camera Image"),
                bridge_field_size(payload, "V2 Front Camera Image"),
                bridge_field_size(payload, "V1 LIDAR Range Array"),
                bridge_field_size(payload, "V2 LIDAR Range Array"),
                bridge_field_size(payload, "V1 LIDAR Intensity Array"),
                bridge_field_size(payload, "V2 LIDAR Intensity Array"),
            )
        settings = self.state.accident_recorder_settings()
        pre_accident_seconds = float(settings["pre_accident_seconds"])
        include_camera = bool(settings["include_camera"])
        self.accident_recorder.record_bridge_payload(
            raw_payload,
            pre_accident_seconds=pre_accident_seconds,
            include_camera=include_camera,
            event="simulator/Bridge",
        )
        collision_triggers = self.record_collision_count_changes(payload)
        bridge_history_payload_value = bridge_history_payload(
            payload,
            empty_front_camera=self.settings.empty_front_camera_in_bridge_history,
        )
        devkit_payloads: dict[int, Any] = {}
        if self.settings.enable_presplit_bridge_cache:
            devkit_payloads = {
                devkit.vehicle_id: self.prebuilt_devkit_bridge_payload(raw_payload, devkit.vehicle_id)
                for devkit in self.devkits
            }
        await self.bridge_history.append(
            bridge_history_payload_value,
            payloads=devkit_payloads,
        )
        for devkit in self.devkits:
            if not devkit.connected or not devkit.awaiting_initial_bridge:
                continue
            devkit.awaiting_initial_bridge = not await self.send_cached_incoming_bridge(devkit)
        await self.publish_simulator_telemetry(payload, "Bridge")
        if collision_triggers and not self.state.race_result().get("active"):
            await self.handle_collision_triggers(collision_triggers, pre_accident_seconds)
        await self.emit_control_cache_to_simulator()

    async def send_cached_incoming_bridge(self, devkit: DevKitConnection) -> bool:
        record = await self.bridge_history.latest()
        if record is None:
            return False
        prebuilt_payload = record.payloads.get(devkit.vehicle_id)
        if prebuilt_payload is None:
            rewritten_payload = self.prebuilt_devkit_bridge_payload(record.payload, devkit.vehicle_id)
            if rewritten_payload is DROP_VALUE:
                return False
            rewritten_args = (rewritten_payload,)
        else:
            rewritten_args = (prebuilt_payload,)
        if rewritten_args is None:
            return False

        await devkit.enqueue("Bridge", rewritten_args)
        self.log_bridge_flow("rct-to-devkit", devkit.vehicle_id, cached=True)
        return True

    async def publish_simulator_telemetry(
        self,
        payload: Any,
        socketio_event: str,
        source: str = "simulator",
    ) -> None:
        telemetry = extract_monitor_telemetry(payload)
        for vehicle_id, values in telemetry.items():
            if isinstance(values.get("ips"), dict):
                self.monitor_vehicle_positions[vehicle_id] = {"ips": values["ips"]}

        lidar_positions = {
            **self.monitor_vehicle_positions,
            **{
                vehicle_id: {"ips": values["ips"]}
                for vehicle_id, values in telemetry.items()
                if isinstance(values.get("ips"), dict)
            },
        }
        lidar_scans: dict[int, Any] = {
            vehicle_id: replay_lidar_ranges_payload(ranges)
            for vehicle_id, ranges in extract_lidar_range_arrays(payload, self.trace_lidar_vehicle_ids).items()
        }
        for vehicle_id, points in extract_lidar_scans(payload, self.trace_lidar_vehicle_ids, lidar_positions).items():
            lidar_scans.setdefault(vehicle_id, points)
        for vehicle_id, points in lidar_scans.items():
            telemetry.setdefault(vehicle_id, {})["lidar_scan"] = points

        if not telemetry:
            return

        for vehicle_id, values in telemetry.items():
            cached = self.monitor_vehicle_telemetry.setdefault(vehicle_id, {})
            cached.update(values)
            cached["socketio_event"] = socketio_event
            cached["source"] = source

        await self.check_race_result(telemetry)

        if self.monitor_ws_interval <= 0:
            telemetry_message = self.cached_telemetry_message()
            if telemetry_message is not None:
                await self.broadcast_monitor(telemetry_message)

    async def handle_devkit_event(self, devkit: DevKitConnection, event: str, args: tuple[Any, ...]) -> None:
        if event == "Bridge":
            await self.handle_devkit_bridge_event(devkit, args)
            return

        rewritten_args = rewrite_args_for_simulator(args, devkit.vehicle_id)
        await self.emit_to_simulators(event, rewritten_args)
        await self.publish_monitor_frame(
            source=devkit.name,
            vehicle_id=devkit.vehicle_id,
            target="simulator",
            socketio_event=event,
            args=rewritten_args,
        )

    async def handle_devkit_bridge_event(self, devkit: DevKitConnection, args: tuple[Any, ...]) -> None:
        await devkit.enqueue_control(monotonic(), args)

    async def process_devkit_bridge_control(
        self,
        devkit: DevKitConnection,
        received_at: float,
        args: tuple[Any, ...],
    ) -> None:
        self.log_bridge_flow("devkit-to-rct", devkit.vehicle_id)
        self.record_bridge_rate(devkit)
        rewritten_args = rewrite_args_for_simulator(args, devkit.vehicle_id)
        rewritten_payload = self.filter_control_payload_for_penalty_decision(
            socketio_data_from_args(rewritten_args)
        )
        rewritten_payload = self.filter_control_payload_for_race_result(rewritten_payload)
        await self.control_cache.merge(
            rewritten_payload,
            received_at,
            origin_vehicle_id=devkit.vehicle_id,
            include_origin=self.settings.enable_origin,
        )
        await self.publish_monitor_frame(
            source=devkit.name,
            vehicle_id=devkit.vehicle_id,
            target="simulator",
            socketio_event="Bridge",
            args=rewritten_args,
        )
        await self.send_next_bridge_after(devkit, received_at)

    async def emit_control_cache_to_simulator(self) -> None:
        _timestamp, outgoing_payload = await self.control_cache.snapshot(
            include_origin=self.settings.enable_origin,
        )
        outgoing_payload = self.filter_control_payload_for_penalty_decision(outgoing_payload)
        outgoing_payload = self.filter_control_payload_for_race_result(outgoing_payload)
        outgoing_args = (outgoing_payload,)
        await self.emit_to_simulators("Bridge", outgoing_args)
        self.log_bridge_flow("rct-to-sim")
        await self.publish_monitor_frame(
            source="rct-control-cache",
            target="simulator",
            socketio_event="Bridge",
            args=outgoing_args,
        )

    async def send_next_bridge_after(self, devkit: DevKitConnection, timestamp: float) -> None:
        record = await self.bridge_history.wait_for_oldest_after(timestamp)
        prebuilt_payload = record.payloads.get(devkit.vehicle_id)
        if prebuilt_payload is None:
            rewritten_payload = self.prebuilt_devkit_bridge_payload(record.payload, devkit.vehicle_id)
            if rewritten_payload is DROP_VALUE:
                return
            rewritten_args = (rewritten_payload,)
        else:
            rewritten_args = (prebuilt_payload,)
        if rewritten_args is None:
            return
        await devkit.enqueue("Bridge", rewritten_args)
        self.log_bridge_flow("rct-to-devkit", devkit.vehicle_id)

    def prebuilt_devkit_bridge_payload(self, payload: Any, vehicle_id: int) -> Any:
        filtered_payload = self.filter_simulator_bridge_payload_for_devkit(payload, vehicle_id)
        return rewrite_simulator_payload_to_devkit(filtered_payload, vehicle_id)

    def filter_simulator_bridge_payload_for_devkit(self, payload: Any, vehicle_id: int) -> Any:
        if not isinstance(payload, dict):
            return payload

        vehicle_prefix = f"V{vehicle_id} "
        merged_payload = dict(payload)
        for key, value in self.latest_front_camera_fields.items():
            if key.startswith(vehicle_prefix):
                merged_payload[key] = value

        topic_selections = self.resolved_topic_selections()
        default_selections = default_topic_selections()
        filtered_payload = dict(merged_payload)

        front_camera_topic = "/autodrive/roboracer_1/front_camera"
        front_camera_key = f"{vehicle_prefix}Front Camera Image"
        if front_camera_key in merged_payload:
            if topic_selections.get(front_camera_topic, default_selections.get(front_camera_topic, False)):
                filtered_payload[front_camera_key] = merged_payload[front_camera_key]
            else:
                filtered_payload[front_camera_key] = WHITE_FRONT_CAMERA_JPEG_BASE64

        for topic, suffixes in TOPIC_TO_BRIDGE_FIELD_SUFFIXES.items():
            if topic_selections.get(topic, default_selections.get(topic, False)):
                continue
            for suffix in suffixes:
                default_value = BRIDGE_FIELD_DEFAULTS_BY_SUFFIX.get(suffix)
                if default_value is None:
                    filtered_payload.pop(f"{vehicle_prefix}{suffix}", None)
                    continue
                filtered_payload[f"{vehicle_prefix}{suffix}"] = default_value

        return filtered_payload

    def record_bridge_rate(self, devkit: DevKitConnection) -> None:
        rates = self.bridge_rates.record(devkit.vehicle_id)
        self.state.set_devkit_bridge_rate(
            devkit.name,
            bridge_hz=float(rates["bridge_hz"]),
            bridge_per_minute=int(rates["bridge_per_minute"]),
        )

    def record_collision_count_changes(self, payload: Any) -> list[tuple[int, int]]:
        triggers: list[tuple[int, int]] = []
        for vehicle_id, count in sorted(extract_collision_counts(payload).items()):
            previous_count = self.collision_counts.get(vehicle_id)
            self.collision_counts[vehicle_id] = count
            if previous_count is not None and count > previous_count:
                triggers.append((vehicle_id, count))
                if self.settings.debug_bridge_flow:
                    LOGGER.info("%s", color_arrow(f"COLLISION DETECTED [V{vehicle_id}]", ANSI_RED))
        return triggers

    async def handle_collision_triggers(
        self,
        collision_triggers: list[tuple[int, int]],
        pre_accident_seconds: float,
    ) -> None:
        if self.state.race_result().get("active"):
            return
        if self.state.penalty_decision().get("active"):
            return

        vehicle_id, count = collision_triggers[0]
        records = self.accident_recorder.snapshot(pre_accident_seconds=pre_accident_seconds)
        if len(collision_triggers) >= 2:
            await self.start_manual_penalty_decision(collision_triggers)
            self.start_accident_record_save(
                vehicle_id,
                count,
                records,
            )
            return

        self.start_accident_record_save(
            vehicle_id,
            count,
            records,
            auto_fault_vehicle_id=vehicle_id,
        )

    async def start_manual_penalty_decision(self, collision_triggers: list[tuple[int, int]]) -> None:
        collision_vehicle_ids = sorted({vehicle_id for vehicle_id, _count in collision_triggers})
        if len(collision_vehicle_ids) < 2 or self.state.penalty_decision().get("active"):
            return

        for task in self._penalty_release_tasks.values():
            task.cancel()
        self._penalty_release_tasks.clear()
        self.filtered_control_vehicle_ids = set(collision_vehicle_ids)
        self.state.start_review_time()
        self.state.set_penalty_decision(
            active=True,
            collision_vehicle_ids=collision_vehicle_ids,
            filtered_vehicle_ids=self.filtered_control_vehicle_ids,
            release_delay_seconds=PENALTY_RELEASE_DELAY_SECONDS,
        )
        LOGGER.info("manual penalty decision pending for vehicles %s", collision_vehicle_ids)
        await self.publish_status()
        await self.broadcast_monitor(
            envelope(
                "penalty-decision",
                source="rct",
                active=True,
                collision_vehicle_ids=collision_vehicle_ids,
                filtered_vehicle_ids=sorted(self.filtered_control_vehicle_ids),
                review_time_seconds=self.state.review_time_seconds(),
                release_delay_seconds=PENALTY_RELEASE_DELAY_SECONDS,
            )
        )

    async def apply_manual_penalty_decision(self, penalty_vehicle_id: int) -> None:
        decision = self.state.penalty_decision()
        collision_vehicle_ids = [int(vehicle_id) for vehicle_id in decision.get("collision_vehicle_ids", [])]
        if penalty_vehicle_id not in collision_vehicle_ids:
            raise ValueError(f"penalty vehicle {penalty_vehicle_id} is not part of the active accident")
        victim_vehicle_ids = [vehicle_id for vehicle_id in collision_vehicle_ids if vehicle_id != penalty_vehicle_id]
        victim_vehicle_id = victim_vehicle_ids[0] if victim_vehicle_ids else None

        for task in self._penalty_release_tasks.values():
            task.cancel()
        self._penalty_release_tasks.clear()
        self.state.stop_review_time()

        penalty_count = self.state.increment_vehicle_penalty(penalty_vehicle_id)
        await self.check_penalty_loss(penalty_vehicle_id, penalty_count)
        penalty_rule = self.state.penalty_rule_settings()
        release_delay_seconds = float(penalty_rule["restart_delay_seconds"])
        restart_delay_active = release_delay_seconds > 0 and not self.state.race_result().get("active")
        self.filtered_control_vehicle_ids = {penalty_vehicle_id} if restart_delay_active else set()
        self.state.set_penalty_decision(
            active=restart_delay_active,
            collision_vehicle_ids=collision_vehicle_ids,
            filtered_vehicle_ids=self.filtered_control_vehicle_ids,
            penalty_vehicle_id=penalty_vehicle_id,
            victim_vehicle_id=victim_vehicle_id,
            release_delay_seconds=release_delay_seconds,
        )
        await self.publish_status()
        await self.broadcast_monitor(
            envelope(
                "penalty-decision",
                source="monitor",
                active=restart_delay_active,
                collision_vehicle_ids=collision_vehicle_ids,
                filtered_vehicle_ids=sorted(self.filtered_control_vehicle_ids),
                penalty_vehicle_id=penalty_vehicle_id,
                victim_vehicle_id=victim_vehicle_id,
                review_time_seconds=self.state.review_time_seconds(),
                release_delay_seconds=release_delay_seconds,
            )
        )

        if restart_delay_active:
            task = asyncio.create_task(
                self.release_penalty_vehicle_after_delay(
                    penalty_vehicle_id,
                    collision_vehicle_ids,
                    release_delay_seconds,
                    victim_vehicle_id,
                )
            )
            self._penalty_release_tasks[penalty_vehicle_id] = task
            task.add_done_callback(self._log_penalty_release_failure)

    async def apply_manual_no_decision(self) -> None:
        decision = self.state.penalty_decision()
        collision_vehicle_ids = [int(vehicle_id) for vehicle_id in decision.get("collision_vehicle_ids", [])]
        if not decision.get("active"):
            raise ValueError("manual no decision requires an active penalty decision")

        for task in self._penalty_release_tasks.values():
            task.cancel()
        self._penalty_release_tasks.clear()
        self.state.stop_review_time()

        self.filtered_control_vehicle_ids.clear()
        self.state.set_penalty_decision(
            active=False,
            collision_vehicle_ids=collision_vehicle_ids,
            filtered_vehicle_ids=self.filtered_control_vehicle_ids,
            release_delay_seconds=PENALTY_RELEASE_DELAY_SECONDS,
        )
        await self.publish_status()
        await self.broadcast_monitor(
            envelope(
                "penalty-decision",
                source="monitor",
                active=False,
                collision_vehicle_ids=collision_vehicle_ids,
                filtered_vehicle_ids=[],
                no_decision=True,
                review_time_seconds=self.state.review_time_seconds(),
                release_delay_seconds=PENALTY_RELEASE_DELAY_SECONDS,
            )
        )

    async def release_penalty_vehicle_after_delay(
        self,
        penalty_vehicle_id: int,
        collision_vehicle_ids: list[int],
        delay_seconds: float,
        victim_vehicle_id: int | None,
    ) -> None:
        await asyncio.sleep(delay_seconds)
        self.filtered_control_vehicle_ids.discard(penalty_vehicle_id)
        self._penalty_release_tasks.pop(penalty_vehicle_id, None)
        self.state.set_penalty_decision(
            active=False,
            collision_vehicle_ids=collision_vehicle_ids,
            filtered_vehicle_ids=self.filtered_control_vehicle_ids,
            penalty_vehicle_id=penalty_vehicle_id,
            victim_vehicle_id=victim_vehicle_id,
            release_delay_seconds=delay_seconds,
        )
        await self.publish_status()
        await self.broadcast_monitor(
            envelope(
                "penalty-decision",
                source="rct",
                active=False,
                collision_vehicle_ids=collision_vehicle_ids,
                filtered_vehicle_ids=sorted(self.filtered_control_vehicle_ids),
                penalty_vehicle_id=penalty_vehicle_id,
                victim_vehicle_id=victim_vehicle_id,
                review_time_seconds=self.state.review_time_seconds(),
                release_delay_seconds=delay_seconds,
            )
        )

    def _log_penalty_release_failure(self, task: asyncio.Task[None]) -> None:
        try:
            task.result()
        except asyncio.CancelledError:
            return
        except Exception:
            LOGGER.exception("penalty vehicle release failed")

    async def check_race_result(self, telemetry: dict[int, dict[str, Any]]) -> None:
        if self.state.race_result().get("active"):
            return

        settings = self.state.racing_rule_settings()
        total_lap_count = int(settings["total_lap_count"])
        for vehicle_id in sorted(telemetry):
            lap_count = telemetry[vehicle_id].get("lap_count")
            if isinstance(lap_count, int | float) and int(lap_count) >= total_lap_count:
                await self.finish_race(
                    winner_vehicle_id=vehicle_id,
                    loser_vehicle_id=other_vehicle_id(vehicle_id),
                    reason="total_lap_count",
                )
                return

    async def check_penalty_loss(self, penalty_vehicle_id: int, penalty_count: int) -> None:
        if self.state.race_result().get("active"):
            return

        settings = self.state.racing_rule_settings()
        maximum_penalty_count = int(settings["maximum_penalty_count"])
        if maximum_penalty_count <= 0 or penalty_count < maximum_penalty_count:
            return

        await self.finish_race(
            winner_vehicle_id=other_vehicle_id(penalty_vehicle_id),
            loser_vehicle_id=penalty_vehicle_id,
            reason="maximum_penalty_count",
        )

    async def finish_race(self, winner_vehicle_id: int, loser_vehicle_id: int, reason: str) -> None:
        if self.state.race_result().get("active"):
            return

        for task in self._penalty_release_tasks.values():
            task.cancel()
        self._penalty_release_tasks.clear()
        self.filtered_control_vehicle_ids.clear()
        self.state.stop_review_time()
        self.state.set_penalty_decision(
            active=False,
            collision_vehicle_ids=[],
            filtered_vehicle_ids=[],
            release_delay_seconds=float(self.state.penalty_rule_settings()["restart_delay_seconds"]),
        )
        self.state.set_race_result(
            active=True,
            winner_vehicle_id=winner_vehicle_id,
            loser_vehicle_id=loser_vehicle_id,
            reason=reason,
        )
        self.state.stop_race_time()
        LOGGER.info("race finished: winner=V%s loser=V%s reason=%s", winner_vehicle_id, loser_vehicle_id, reason)
        await self.record_audit_event(
            event_type="race_end",
            text=self.race_end_audit_text(
                winner_vehicle_id=winner_vehicle_id,
                loser_vehicle_id=loser_vehicle_id,
                reason=reason,
            ),
        )
        await self.publish_status()
        await self.broadcast_monitor(
            envelope(
                "race-result",
                source="rct",
                active=True,
                winner_vehicle_id=winner_vehicle_id,
                loser_vehicle_id=loser_vehicle_id,
                reason=reason,
                celebration_with_confetti=bool(
                    self.state.racing_rule_settings()["celebration_with_confetti"]
                ),
            )
        )

    def filter_control_payload_for_penalty_decision(self, payload: Any) -> Any:
        if not isinstance(payload, dict) or not self.filtered_control_vehicle_ids:
            return payload

        filtered_payload = dict(payload)
        for vehicle_id in self.filtered_control_vehicle_ids:
            for field in CONTROL_FILTER_FIELDS:
                filtered_payload[f"V{vehicle_id} {field}"] = "0.0"
        return filtered_payload

    def filter_control_payload_for_race_result(self, payload: Any) -> Any:
        if not isinstance(payload, dict) or not self.state.race_result().get("active"):
            return payload

        filtered_payload = dict(payload)
        for vehicle_id in (1, 2):
            for field in CONTROL_FILTER_FIELDS:
                filtered_payload[f"V{vehicle_id} {field}"] = "0.0"
        return filtered_payload

    def start_accident_record_save(
        self,
        trigger_vehicle_id: int,
        collision_count: int,
        records: list[Any],
        *,
        auto_fault_vehicle_id: int | None = None,
    ) -> None:
        task = asyncio.create_task(
            self.save_accident_record(
                trigger_vehicle_id,
                collision_count,
                records,
                auto_fault_vehicle_id=auto_fault_vehicle_id,
            ),
        )
        task.add_done_callback(self._log_accident_record_save_failure)

    async def save_accident_record(
        self,
        trigger_vehicle_id: int,
        collision_count: int,
        records: list[Any],
        *,
        auto_fault_vehicle_id: int | None = None,
    ) -> None:
        try:
            accident_log = await asyncio.to_thread(
                self.accident_recorder.write_mcap,
                records,
                trigger_vehicle_id=trigger_vehicle_id,
                collision_count=collision_count,
            )
        except ModuleNotFoundError:
            LOGGER.exception("mcap package is not installed; cannot save accident record")
            return
        decision_record = None
        if auto_fault_vehicle_id is not None:
            penalty_rule = self.state.penalty_rule_settings()
            sw_analysis = penalty_rule.get("sw_analysis", {})
            v2_collision_types = penalty_rule.get("decision_pack_v2", {}).get("collision_types", {})
            configured_package_ids = v2_collision_types if penalty_rule.get("decision_pack_version") == "v2" else sw_analysis
            decision_package_ids = [
                package_id
                for package_id, enabled in configured_package_ids.items()
                if enabled and package_id in KNOWN_DECISION_PACKAGE_IDS
            ]
            decision_record = await asyncio.to_thread(
                save_decision_record,
                Path(accident_log.path),
                fault_vehicle_id=auto_fault_vehicle_id,
                penalty=None,
                penalty_vehicle_id=None,
                no_decision=False,
                decision_package_ids=decision_package_ids,
                decision_results={},
                memo="Automatically recorded: single-vehicle collision.",
            )
        monitor_log = AccidentLogMonitorState(
            filename=accident_log.filename,
            path=accident_log.path,
            time=accident_log.time,
            size_bytes=accident_log.size_bytes,
            decision_record=decision_record,
        )
        self.state.add_accident_log(monitor_log)
        await self.publish_accident_logs()
        await self.publish_status()
        await self.record_audit_event(
            event_type="accident_record",
            text=(
                "Accident record created: "
                f"{self.accident_record_audit_time(accident_log.time)} "
                f"(trigger V{trigger_vehicle_id}, collision count {collision_count})."
            ),
            accident_log_filename=accident_log.filename,
            accident_log_time=accident_log.time,
        )
        if decision_record is not None:
            await self.record_decision_audit(
                Path(accident_log.path),
                decision_record,
                decision_mode="auto",
            )

    def _log_accident_record_save_failure(self, task: asyncio.Task[None]) -> None:
        try:
            task.result()
        except Exception:
            LOGGER.exception("accident record save failed")

    def log_bridge_flow(
        self,
        action: str,
        vehicle_id: int | None = None,
        cached: bool = False,
    ) -> None:
        if not self.settings.debug_bridge_flow:
            return

        sim = "SIM"
        rct = "RCT"
        v1 = "V1"
        v2 = "V2"
        s2r = "    "
        r2v1 = "    "
        v12v2 = "    "
        arrow_color = ANSI_GRAY if cached else ANSI_RED

        if action == "sim-to-rct":
            sim = f"SIM {color_arrow('->', arrow_color)} "
            s2r = ""
        elif action == "rct-to-devkit":
            if vehicle_id == 1:
                rct = f"RCT {color_arrow('->', arrow_color)} "
                r2v1 = ""
            elif vehicle_id == 2:
                v1 = f"V1 {color_arrow('->', arrow_color)} "
                v12v2 = ""
        elif action == "devkit-to-rct":
            blue_arrow = color_arrow("<-", ANSI_BLUE)
            if vehicle_id == 1:
                rct = f"RCT {blue_arrow} "
                r2v1 = ""
            elif vehicle_id == 2:
                v1 = f"V1 {blue_arrow} "
                v12v2 = ""
        elif action == "rct-to-sim":
            sim = f"SIM {color_arrow('<-', ANSI_BLUE)} "
            s2r = ""
        LOGGER.info("%s%s%s%s%s%s%s", sim, s2r, rct, r2v1, v1, v12v2, v2)

    async def handle_monitor_message(self, message: str) -> None:
        try:
            command = json.loads(message)
        except json.JSONDecodeError:
            await self.broadcast_monitor(
                envelope("error", source="monitor", message="monitor command must be JSON")
            )
            return

        if await self.handle_monitor_command(command):
            return

        target = command.get("target", "simulator")
        event = command.get("event", "message")
        if not isinstance(event, str) or not event:
            await self.broadcast_monitor(
                envelope("error", source="monitor", message="monitor command event must be a non-empty string")
            )
            return

        try:
            args = self._command_args(command)
        except ValueError as exc:
            await self.broadcast_monitor(envelope("error", source="monitor", message=str(exc)))
            return

        if target == "simulator":
            await self.emit_to_simulators(event, args)
        elif target == "all-devkits":
            for devkit in self.devkits:
                rewritten_args = rewrite_args_for_devkit(args, devkit.vehicle_id)
                if rewritten_args is not None:
                    await devkit.enqueue(event, rewritten_args)
        elif isinstance(target, str) and target.startswith("devkit:"):
            devkit = self._get_devkit(target)
            if devkit is None:
                await self.broadcast_monitor(
                    envelope("error", source="monitor", message=f"unknown target {target!r}")
                )
                return
            rewritten_args = rewrite_args_for_devkit(args, devkit.vehicle_id)
            if rewritten_args is not None:
                await devkit.enqueue(event, rewritten_args)
        else:
            await self.broadcast_monitor(
                envelope("error", source="monitor", message=f"unsupported target {target!r}")
            )
            return

        await self.broadcast_monitor(envelope("command", source="monitor", target=target, socketio_event=event))

    async def handle_monitor_command(self, command: dict[str, Any]) -> bool:
        command_name = command.get("command")
        if command_name is None:
            return False

        publish_full_status = False
        publish_light_status = False
        try:
            if command_name == "configure-devkits":
                devkit_configs = command.get("devkits", [])
                if not isinstance(devkit_configs, list):
                    raise ValueError("configure-devkits command requires a devkits list")
                for devkit_config in devkit_configs:
                    devkit, host, port = self._devkit_endpoint_from_payload(devkit_config)
                    await self.configure_devkit(devkit, host, port, enabled=True)
                publish_full_status = True
            elif command_name == "connect-devkit":
                devkit, host, port = self._devkit_endpoint_from_payload(command, require_endpoint=False)
                await self.connect_devkit(devkit, host, port)
                publish_light_status = True
            elif command_name == "disconnect-devkit":
                devkit = self._devkit_from_payload(command)
                await self.disconnect_devkit(devkit)
                publish_light_status = True
            elif command_name == "manual-penalty-decision":
                penalty_vehicle_id = self._penalty_vehicle_id_from_payload(command)
                await self.apply_manual_penalty_decision(penalty_vehicle_id)
            elif command_name == "manual-no-decision":
                await self.apply_manual_no_decision()
            else:
                raise ValueError(f"unsupported monitor command {command_name!r}")
        except ValueError as exc:
            LOGGER.warning("monitor command %s rejected: %s", command_name, exc)
            await self.broadcast_monitor(envelope("error", source="monitor", message=str(exc)))
            return True

        if publish_full_status:
            await self.publish_full_status()
        elif publish_light_status:
            await self.publish_status()
        await self.broadcast_monitor(envelope("command", source="monitor", command=command_name))
        return True

    def _penalty_vehicle_id_from_payload(self, payload: dict[str, Any]) -> int:
        try:
            vehicle_id = int(payload.get("penalty_vehicle_id", payload.get("vehicle_id")))
        except (TypeError, ValueError) as exc:
            raise ValueError("manual penalty decision requires penalty_vehicle_id") from exc

        if self._get_devkit_by_vehicle_id(vehicle_id) is None:
            raise ValueError(f"unknown penalty_vehicle_id {vehicle_id}")
        return vehicle_id

    def _devkit_endpoint_from_payload(
        self,
        payload: Any,
        require_endpoint: bool = True,
    ) -> tuple[DevKitConnection, str | None, int | None]:
        if not isinstance(payload, dict):
            raise ValueError("devkit command payload must be an object")

        devkit = self._devkit_from_payload(payload)
        host = payload.get("host", payload.get("hostname"))
        port = payload.get("port")
        if host is None or port is None:
            if require_endpoint:
                raise ValueError("devkit command requires host and port")
            return devkit, None, None

        if not isinstance(host, str) or not host.strip():
            raise ValueError("devkit host must be a non-empty string")

        try:
            port_number = int(port)
        except (TypeError, ValueError) as exc:
            raise ValueError("devkit port must be an integer") from exc

        if port_number < 1 or port_number > 65535:
            raise ValueError("devkit port must be between 1 and 65535")

        return devkit, host.strip(), port_number

    def _devkit_from_payload(self, payload: dict[str, Any]) -> DevKitConnection:
        try:
            vehicle_id = int(payload["vehicle_id"])
        except KeyError as exc:
            raise ValueError("devkit command requires vehicle_id") from exc
        except (TypeError, ValueError) as exc:
            raise ValueError("devkit vehicle_id must be an integer") from exc

        devkit = self._get_devkit_by_vehicle_id(vehicle_id)
        if devkit is None:
            raise ValueError(f"unknown vehicle_id {vehicle_id}")
        return devkit

    def _command_args(self, command: dict[str, Any]) -> tuple[Any, ...]:
        if "args" in command:
            args = command["args"]
            if not isinstance(args, list):
                raise ValueError("monitor command args must be a list")
            return tuple(args)

        return (
            decode_monitor_arg(command.get("payload", ""), command.get("encoding", "json")),
        )

    async def emit_to_simulators(self, event: str, args: tuple[Any, ...]) -> None:
        data = socketio_data_from_args(args)
        for sid in tuple(self.simulator_sids):
            await self.emit_to_simulator_sid(sid, event, data)

    async def emit_to_simulator_sid(self, sid: str, event: str, data: Any) -> None:
        emit_internal = getattr(self.sio, "_emit_internal", None)
        if callable(emit_internal):
            await emit_internal(sid, event, data, namespace="/")
            return

        if event == "message":
            await self.sio.send(data, to=sid)
        else:
            await self.sio.emit(event, data=data, to=sid)

    def _get_devkit(self, name: str) -> DevKitConnection | None:
        return next((devkit for devkit in self.devkits if devkit.name == name), None)

    def _get_devkit_by_vehicle_id(self, vehicle_id: int) -> DevKitConnection | None:
        return next((devkit for devkit in self.devkits if devkit.vehicle_id == vehicle_id), None)

    async def broadcast_monitor(self, message: str) -> None:
        await self.send_monitor_now(message)

    async def publish_monitor_frame(
        self,
        *,
        source: str,
        target: str,
        socketio_event: str,
        args: tuple[Any, ...],
        vehicle_id: int | None = None,
    ) -> None:
        if not self.settings.monitor_frame_events:
            return

        fields: dict[str, Any] = {
            "source": source,
            "target": target,
            "socketio_event": socketio_event,
            "args": [encode_socketio_arg(arg) for arg in args],
        }
        if vehicle_id is not None:
            fields["vehicle_id"] = vehicle_id
        await self.broadcast_monitor(envelope("frame", **fields))

    async def send_monitor_now(self, message: str) -> None:
        if message is None:
            return
        await self.monitor_hub.broadcast(message)
        self.state.set_monitor_clients(self.monitor_hub.client_count)

    def status_message(self, *, full: bool = False) -> str:
        return envelope("status", **self.status_payload(full=full))

    def accident_logs_message(self) -> str:
        return envelope(
            "accident-logs",
            source="rct",
            accident_logs=self.state.accident_logs(),
        )

    def audit_log_entry_message(self, record: AuditLogRecord) -> str:
        return envelope(
            "audit-log",
            source="rct",
            audit_entry=asdict(audit_monitor_state_from_record(record)),
        )

    def cached_telemetry_message(self) -> str | None:
        if not self.monitor_vehicle_telemetry:
            return None

        vehicles: dict[str, dict[str, Any]] = {}
        for vehicle_id, values in sorted(self.monitor_vehicle_telemetry.items()):
            vehicle_values = {
                key: value
                for key, value in values.items()
                if key not in {"source", "socketio_event"}
            }
            if vehicle_values:
                vehicles[str(vehicle_id)] = vehicle_values

        if not vehicles:
            return None

        return envelope(
            "telemetry",
            source="rct-cache",
            socketio_event="cached",
            race_time_seconds=self.state.race_time_seconds(),
            review_time_seconds=self.state.review_time_seconds(),
            vehicles=vehicles,
        )

    async def publish_status(self) -> None:
        await self.broadcast_monitor(self.status_message(full=False))

    async def publish_full_status(self) -> None:
        await self.broadcast_monitor(self.status_message(full=True))

    async def publish_accident_logs(self) -> None:
        await self.broadcast_monitor(self.accident_logs_message())

    async def publish_audit_log_entry(self, record: AuditLogRecord) -> None:
        await self.broadcast_monitor(self.audit_log_entry_message(record))

    async def record_audit_event(
        self,
        *,
        event_type: str,
        text: str,
        accident_log_filename: str | None = None,
        accident_log_time: str | None = None,
        decision_mode: str | None = None,
        decision_result: dict[str, Any] | None = None,
        memo: str | None = None,
    ) -> None:
        self.audit_recorder.output_dir = self.accident_recorder.output_dir
        async with self._audit_lock:
            try:
                record = await asyncio.to_thread(
                    self.audit_recorder.append,
                    event_type=event_type,
                    text=text,
                    accident_log_filename=accident_log_filename,
                    accident_log_time=accident_log_time,
                    decision_mode=decision_mode,
                    decision_result=decision_result,
                    memo=memo,
                )
            except ModuleNotFoundError:
                LOGGER.exception("mcap package is not installed; cannot save audit log")
                return
            except Exception:
                LOGGER.exception("failed to save audit log")
                return

        self.state.add_audit_log(audit_monitor_state_from_record(record))
        await self.publish_audit_log_entry(record)

    async def record_devkit_connection_audit(self, devkit: DevKitConnection, *, connected: bool) -> None:
        event_type = "vehicle_connect" if connected else "vehicle_disconnect"
        action = "connected to" if connected else "disconnected from"
        endpoint = self.devkit_audit_endpoint(devkit)
        endpoint_text = f" ({endpoint})" if endpoint else ""
        await self.record_audit_event(
            event_type=event_type,
            text=f"{self.vehicle_audit_label(devkit.vehicle_id)} {action} RCT{endpoint_text}.",
        )

    def devkit_audit_endpoint(self, devkit: DevKitConnection) -> str:
        if devkit.host and devkit.port is not None:
            return f"{devkit.host}:{devkit.port}"
        return devkit.url

    def vehicle_audit_label(self, vehicle_id: int) -> str:
        if vehicle_id == 1:
            return "Vehicle A"
        if vehicle_id == 2:
            return "Vehicle B"
        return f"Vehicle {vehicle_id}"

    async def record_decision_audit(
        self,
        accident_log_path: Path,
        decision_record: dict[str, Any],
        *,
        decision_mode: str,
    ) -> None:
        await self.record_audit_event(
            event_type="decision",
            text=self.decision_audit_text(decision_record, decision_mode=decision_mode),
            accident_log_filename=accident_log_path.name,
            accident_log_time=accident_log_path.stem.removeprefix("autodrive "),
            decision_mode=decision_mode,
            decision_result={
                "fault_vehicle_id": decision_record.get("fault_vehicle_id"),
                "penalty_vehicle_id": decision_record.get("penalty_vehicle_id"),
                "no_decision": bool(decision_record.get("no_decision")),
                "decision_package_ids": decision_record.get("decision_package_ids", []),
            },
            memo=decision_record.get("memo") if isinstance(decision_record.get("memo"), str) else None,
        )

    def race_end_audit_text(self, *, winner_vehicle_id: int, loser_vehicle_id: int, reason: str) -> str:
        if reason == "total_lap_count":
            reason_text = "reached total lap count"
        elif reason == "maximum_penalty_count":
            reason_text = "reached maximum penalty count"
        else:
            reason_text = reason.replace("_", " ")
        return f"Race ended: {reason_text}. Winner V{winner_vehicle_id}, loser V{loser_vehicle_id}."

    def decision_audit_text(self, decision_record: dict[str, Any], *, decision_mode: str) -> str:
        mode_label = "auto" if decision_mode == "auto" else "manual"
        if decision_record.get("no_decision"):
            result = "no decision"
        else:
            penalty_vehicle_id = decision_record.get("penalty_vehicle_id")
            fault_vehicle_id = decision_record.get("fault_vehicle_id")
            if penalty_vehicle_id is not None:
                result = f"penalty V{penalty_vehicle_id}"
            elif fault_vehicle_id is not None:
                result = f"fault V{fault_vehicle_id}"
            else:
                result = "decision recorded"
        memo = decision_record.get("memo")
        memo_text = f" Note: {memo}" if isinstance(memo, str) and memo else ""
        return f"Decision recorded ({mode_label}): {result}.{memo_text}"

    def accident_record_audit_time(self, accident_log_time: str) -> str:
        parts = accident_log_time.split(" ", 1)
        return parts[1] if len(parts) == 2 else accident_log_time

    def refresh_bridge_rates(self, now: float | None = None) -> bool:
        current_snapshot = {
            devkit_snapshot["name"]: (devkit_snapshot["bridge_hz"], devkit_snapshot["bridge_per_minute"])
            for devkit_snapshot in self.state.snapshot()["devkits"]
        }
        changed = False
        for devkit in self.devkits:
            rates = self.bridge_rates.rates(devkit.vehicle_id, now=now)
            next_values = (float(rates["bridge_hz"]), int(rates["bridge_per_minute"]))
            if current_snapshot.get(devkit.name) == next_values:
                continue
            self.state.set_devkit_bridge_rate(
                devkit.name,
                bridge_hz=next_values[0],
                bridge_per_minute=next_values[1],
            )
            changed = True
        return changed

    async def audit_bridge_rates(self, now: float | None = None) -> None:
        now = monotonic() if now is None else now
        settings = self.state.audit_rule_settings()
        for devkit in self.devkits:
            rates = self.bridge_rates.rates(devkit.vehicle_id, now=now)
            events = self.bridge_hz_audit.evaluate(
                vehicle_id=devkit.vehicle_id,
                vehicle_label=self.vehicle_audit_label(devkit.vehicle_id),
                bridge_hz=float(rates["bridge_hz"]),
                connected=devkit.connected,
                settings=settings,
                now=now,
            )
            for event in events:
                await self.record_audit_event(
                    event_type=event.event_type,
                    text=event.text,
                )

    def status_payload(self, *, full: bool = False) -> dict[str, Any]:
        self.refresh_bridge_rates()
        snapshot = self.state.snapshot()
        snapshot.pop("topic_selections", None)
        snapshot.pop("accident_logs", None)
        snapshot.pop("audit_log", None)
        snapshot.pop("race_time_seconds", None)

        if not full:
            snapshot.pop("accident_recorder", None)
            snapshot.pop("penalty_rule", None)
            snapshot.pop("racing_rule", None)
            snapshot.pop("audit_rule", None)
            snapshot["devkits"] = [
                {
                    "name": devkit["name"],
                    "vehicle_id": devkit["vehicle_id"],
                    "connected": devkit["connected"],
                    "queued_messages": devkit["queued_messages"],
                    "bridge_hz": devkit["bridge_hz"],
                    "bridge_per_minute": devkit["bridge_per_minute"],
                }
                for devkit in snapshot.get("devkits", [])
            ]

        payload = {
            "monitor_protocol": {
                "name": "autodrive-rct-monitor",
                "version": MONITOR_PROTOCOL_VERSION,
            },
            "trace_lidar_vehicle_ids": sorted(self.trace_lidar_vehicle_ids),
            **snapshot,
        }
        if full:
            payload["simulator_socketio_path"] = f"/{SOCKETIO_PATH}/"
        return payload

    def refresh_accident_logs_from_disk(self) -> None:
        accident_logs = [
            AccidentLogMonitorState(
                filename=accident_log.filename,
                path=accident_log.path,
                time=accident_log.time,
                size_bytes=accident_log.size_bytes,
                decision_record=load_decision_record(Path(accident_log.path)),
            )
            for accident_log in list_accident_logs(self.accident_recorder.output_dir)
        ]
        self.state.set_accident_logs(accident_logs)

    def refresh_audit_log_from_disk(self) -> None:
        self.audit_recorder.output_dir = self.accident_recorder.output_dir
        try:
            audit_log = [
                audit_monitor_state_from_record(audit_record)
                for audit_record in list_audit_logs(self.audit_recorder.output_dir)
            ]
        except ModuleNotFoundError:
            LOGGER.exception("mcap package is not installed; cannot read audit log")
            audit_log = []
        self.state.set_audit_log(audit_log)

    def accident_log_path_from_filename(self, filename: str) -> Path:
        if Path(filename).name != filename:
            raise ValueError("invalid accident log filename")
        path = self.accident_recorder.output_dir / filename
        if path.suffix != ".mcap":
            raise ValueError("accident log filename must point to an .mcap file")
        if not path.is_file():
            raise ValueError("accident log not found")
        return path

    def resolve_accident_log_path(self, path_param: str) -> Path:
        output_dir = self.accident_recorder.output_dir.resolve()
        path = Path(path_param)
        if not path.is_absolute():
            path = (Path.cwd() / path).resolve()
        else:
            path = path.resolve()
        if path.suffix != ".mcap":
            raise ValueError("accident log path must point to an .mcap file")
        if not path.is_relative_to(output_dir):
            raise ValueError("accident log path must be inside accident log directory")
        return path

    def accident_log_summary_from_mcap(self, path: Path, *, include_lidar_scan: bool = True) -> dict[str, Any]:
        return accident_log_summary_from_mcap(path, self.settings.devkit_vehicle_ids, include_lidar_scan=include_lidar_scan)

    def topic_options_payload(self) -> list[dict[str, Any]]:
        selections = self.resolved_topic_selections()
        return [
            {
                **option,
                "checked": selections.get(option["topic"], default_topic_selections()[option["topic"]]),
                "mutable": option["access"] == "restricted" or option["topic"] in RECOMMENDED_OFF_TOPICS,
                "recommended_off": option["topic"] in RECOMMENDED_OFF_TOPICS,
                "bridge_filterable": option["topic"] in TOPIC_TO_BRIDGE_FIELD_SUFFIXES or option["topic"] == "/autodrive/roboracer_1/front_camera",
                "bridge_ignored": option["topic"] in TOPICS_IGNORED_FOR_DEVKIT_BRIDGE,
            }
            for option in TOPIC_OPTIONS
        ]

    def validate_topic_selections(self, topic_selections: dict[str, Any]) -> dict[str, bool]:
        valid_topics = {option["topic"] for option in TOPIC_OPTIONS}
        validated_topic_selections: dict[str, bool] = {}
        for topic, enabled in topic_selections.items():
            if topic not in valid_topics:
                raise ValueError(f"unsupported topic {topic!r}")
            if not isinstance(enabled, bool):
                raise ValueError(f"topic {topic!r} enabled flag must be a boolean")
            validated_topic_selections[topic] = enabled
        return validated_topic_selections

    def validate_accident_recorder_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        value = settings.get("pre_accident_seconds")
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise ValueError("pre_accident_seconds must be a number")
        pre_accident_seconds = float(value)
        if pre_accident_seconds < 0:
            raise ValueError("pre_accident_seconds must be greater than or equal to 0")
        if pre_accident_seconds > 60:
            raise ValueError("pre_accident_seconds must be less than or equal to 60")
        include_camera = settings.get("include_camera", False)
        if not isinstance(include_camera, bool):
            raise ValueError("include_camera must be a boolean")
        return {
            "pre_accident_seconds": pre_accident_seconds,
            "include_camera": include_camera,
        }

    def validate_penalty_rule_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        restart_delay_seconds = settings.get("restart_delay_seconds", PENALTY_RELEASE_DELAY_SECONDS)
        if isinstance(restart_delay_seconds, bool) or not isinstance(restart_delay_seconds, int | float):
            raise ValueError("restart_delay_seconds must be a number")
        restart_delay_seconds = float(restart_delay_seconds)
        if restart_delay_seconds < 0 or restart_delay_seconds > 60:
            raise ValueError("restart_delay_seconds must be between 0 and 60")
        decision_pack_version = settings.get("decision_pack_version", "v2")
        if decision_pack_version not in {"v1", "v2"}:
            raise ValueError("decision_pack_version must be v1 or v2")
        sw_analysis = settings.get("sw_analysis", DEFAULT_PENALTY_SW_ANALYSIS_SETTINGS)
        if not isinstance(sw_analysis, dict):
            raise ValueError("sw_analysis must be an object")
        validated_sw_analysis = dict(DEFAULT_PENALTY_SW_ANALYSIS_SETTINGS)
        for key, value in sw_analysis.items():
            if key not in validated_sw_analysis:
                raise ValueError(f"unknown sw_analysis option: {key}")
            if not isinstance(value, bool):
                raise ValueError(f"sw_analysis.{key} must be a boolean")
            validated_sw_analysis[key] = value
        decision_pack_v2 = settings.get("decision_pack_v2", {})
        if not isinstance(decision_pack_v2, dict):
            raise ValueError("decision_pack_v2 must be an object")
        automatic_decision = decision_pack_v2.get("automatic_decision", False)
        if not isinstance(automatic_decision, bool):
            raise ValueError("decision_pack_v2.automatic_decision must be a boolean")
        graph_settings = decision_pack_v2.get("graphs", DEFAULT_DECISION_PACK_V2_GRAPH_SETTINGS)
        if not isinstance(graph_settings, dict):
            raise ValueError("decision_pack_v2.graphs must be an object")
        validated_graphs = dict(DEFAULT_DECISION_PACK_V2_GRAPH_SETTINGS)
        for key, value in graph_settings.items():
            if key not in validated_graphs:
                raise ValueError(f"unknown decision_pack_v2 graph option: {key}")
            if not isinstance(value, bool):
                raise ValueError(f"decision_pack_v2.graphs.{key} must be a boolean")
            validated_graphs[key] = value
        collision_type_settings = decision_pack_v2.get("collision_types", DEFAULT_DECISION_PACK_V2_COLLISION_TYPE_SETTINGS)
        if not isinstance(collision_type_settings, dict):
            raise ValueError("decision_pack_v2.collision_types must be an object")
        validated_collision_types = dict(DEFAULT_DECISION_PACK_V2_COLLISION_TYPE_SETTINGS)
        for key, value in collision_type_settings.items():
            if key not in validated_collision_types:
                raise ValueError(f"unknown decision_pack_v2 collision type option: {key}")
            if not isinstance(value, bool):
                raise ValueError(f"decision_pack_v2.collision_types.{key} must be a boolean")
            validated_collision_types[key] = value
        return {
            "restart_delay_seconds": restart_delay_seconds,
            "decision_pack_version": decision_pack_version,
            "sw_analysis": validated_sw_analysis,
            "decision_pack_v2": {
                "automatic_decision": automatic_decision,
                "graphs": validated_graphs,
                "collision_types": validated_collision_types,
            },
        }

    def validate_racing_rule_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        total_lap_count = settings.get("total_lap_count", 10)
        if isinstance(total_lap_count, bool) or not isinstance(total_lap_count, int | float):
            raise ValueError("total_lap_count must be a number")
        total_lap_count = int(total_lap_count)
        if total_lap_count < 1 or total_lap_count > 1000:
            raise ValueError("total_lap_count must be between 1 and 1000")

        maximum_penalty_count = settings.get("maximum_penalty_count", 0)
        if isinstance(maximum_penalty_count, bool) or not isinstance(maximum_penalty_count, int | float):
            raise ValueError("maximum_penalty_count must be a number")
        maximum_penalty_count = int(maximum_penalty_count)
        if maximum_penalty_count < 0 or maximum_penalty_count > 1000:
            raise ValueError("maximum_penalty_count must be between 0 and 1000")

        celebration_with_confetti = settings.get("celebration_with_confetti", False)
        if not isinstance(celebration_with_confetti, bool):
            raise ValueError("celebration_with_confetti must be a boolean")

        return {
            "total_lap_count": total_lap_count,
            "maximum_penalty_count": maximum_penalty_count,
            "celebration_with_confetti": celebration_with_confetti,
        }

    def validate_audit_rule_settings(self, settings: dict[str, Any]) -> dict[str, Any]:
        bridge_hz_maximum = settings.get("bridge_hz_maximum", 120.0)
        if isinstance(bridge_hz_maximum, bool) or not isinstance(bridge_hz_maximum, int | float):
            raise ValueError("bridge_hz_maximum must be a number")
        bridge_hz_maximum = float(bridge_hz_maximum)
        if bridge_hz_maximum <= 0 or bridge_hz_maximum > 1000:
            raise ValueError("bridge_hz_maximum must be greater than 0 and less than or equal to 1000")

        bridge_hz_minimum = settings.get("bridge_hz_minimum", 20.0)
        if isinstance(bridge_hz_minimum, bool) or not isinstance(bridge_hz_minimum, int | float):
            raise ValueError("bridge_hz_minimum must be a number")
        bridge_hz_minimum = float(bridge_hz_minimum)
        if bridge_hz_minimum < 0 or bridge_hz_minimum > 1000:
            raise ValueError("bridge_hz_minimum must be between 0 and 1000")
        if bridge_hz_minimum >= bridge_hz_maximum:
            raise ValueError("bridge_hz_minimum must be less than bridge_hz_maximum")

        bridge_hz_spike_percent = settings.get("bridge_hz_spike_percent", DEFAULT_BRIDGE_HZ_SPIKE_PERCENT)
        if isinstance(bridge_hz_spike_percent, bool) or not isinstance(bridge_hz_spike_percent, int | float):
            raise ValueError("bridge_hz_spike_percent must be a number")
        bridge_hz_spike_percent = float(bridge_hz_spike_percent)
        if bridge_hz_spike_percent < 5 or bridge_hz_spike_percent > 50:
            raise ValueError("bridge_hz_spike_percent must be between 5 and 50")

        return {
            "bridge_hz_maximum": bridge_hz_maximum,
            "bridge_hz_minimum": bridge_hz_minimum,
            "bridge_hz_spike_percent": bridge_hz_spike_percent,
        }

    def resolved_topic_selections(self) -> dict[str, bool]:
        selections = default_topic_selections()
        selections.update(self.state.topic_selections())
        return selections

    def set_devkit_connected(self, devkit: DevKitConnection, connected: bool) -> bool:
        if devkit.connected == connected:
            self.update_devkit_queue(devkit)
            return False
        devkit.connected = connected
        self.state.set_devkit_connected(devkit.name, connected)
        self.update_devkit_queue(devkit)
        return True

    def update_devkit_queue(self, devkit: DevKitConnection) -> None:
        self.state.set_devkit_queue_size(devkit.name, devkit.queue.qsize())


async def async_main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = load_settings()
    configure_socketio_logging(settings)
    tower = RaceControlTower(settings)
    await tower.start()


def main() -> None:
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        LOGGER.info("RCT stopped")
