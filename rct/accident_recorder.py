# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

import base64
import json
from collections import deque
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from time import monotonic, time_ns
from typing import Any

FRONT_CAMERA_IMAGE_KEYS = ("V1 Front Camera Image", "V2 Front Camera Image")


@dataclass(frozen=True)
class AccidentBridgeRecord:
    monotonic_timestamp: float
    wall_time_ns: int
    event: str
    payload: Any


@dataclass(frozen=True)
class AccidentLogRecord:
    filename: str
    path: str
    time: str
    size_bytes: int


class AccidentRecorder:
    def __init__(self, output_dir: Path | str = "accident_logs") -> None:
        self.output_dir = Path(output_dir)
        self._records: deque[AccidentBridgeRecord] = deque()

    def record_bridge_payload(
        self,
        payload: Any,
        *,
        pre_accident_seconds: float,
        include_camera: bool,
        event: str = "Bridge",
        now: float | None = None,
        wall_time: int | None = None,
    ) -> None:
        timestamp = monotonic() if now is None else now
        record = AccidentBridgeRecord(
            monotonic_timestamp=timestamp,
            wall_time_ns=time_ns() if wall_time is None else wall_time,
            event=event,
            payload=deepcopy(payload if include_camera else without_front_camera(payload)),
        )
        self._records.append(record)
        self._prune(timestamp, pre_accident_seconds)

    def snapshot(self, now: float | None = None, pre_accident_seconds: float | None = None) -> list[AccidentBridgeRecord]:
        timestamp = monotonic() if now is None else now
        if pre_accident_seconds is not None:
            self._prune(timestamp, pre_accident_seconds)
        return [
            AccidentBridgeRecord(
                record.monotonic_timestamp,
                record.wall_time_ns,
                record.event,
                deepcopy(record.payload),
            )
            for record in self._records
        ]

    def write_mcap(
        self,
        records: list[AccidentBridgeRecord],
        *,
        trigger_vehicle_id: int,
        collision_count: int,
        created_at: datetime | None = None,
    ) -> AccidentLogRecord:
        created = created_at or datetime.now()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        output_path = self.output_dir / accident_log_filename(created)

        from mcap.writer import Writer

        with output_path.open("wb") as output:
            writer = Writer(output)
            writer.start(profile="rct-accident-bridge")
            schema_id = writer.register_schema(
                name="autodrive.rct.AccidentBridgeEvent",
                encoding="jsonschema",
                data=json.dumps(BRIDGE_EVENT_SCHEMA, separators=(",", ":")).encode("utf-8"),
            )
            channel_id = writer.register_channel(
                topic="/rct/accident/bridge",
                message_encoding="json",
                schema_id=schema_id,
            )
            metadata_channel_id = writer.register_channel(
                topic="/rct/accident/metadata",
                message_encoding="json",
                schema_id=schema_id,
            )
            created_at_ns = int(created.timestamp() * 1_000_000_000)
            metadata = {
                "type": "metadata",
                "created_at": created.isoformat(),
                "trigger_vehicle_id": trigger_vehicle_id,
                "collision_count": collision_count,
                "record_count": len(records),
            }
            writer.add_message(
                channel_id=metadata_channel_id,
                log_time=created_at_ns,
                publish_time=created_at_ns,
                data=json.dumps(metadata, separators=(",", ":"), ensure_ascii=False).encode("utf-8"),
            )
            for index, record in enumerate(records):
                message = {
                    "type": "bridge",
                    "index": index,
                    "event": record.event,
                    "monotonic_timestamp": record.monotonic_timestamp,
                    "wall_time_ns": record.wall_time_ns,
                    "payload": json_safe(record.payload),
                }
                data = json.dumps(message, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
                writer.add_message(
                    channel_id=channel_id,
                    log_time=record.wall_time_ns,
                    publish_time=record.wall_time_ns,
                    data=data,
                )
            writer.finish()

        return accident_log_record_from_path(output_path)

    def _prune(self, now: float, pre_accident_seconds: float) -> None:
        cutoff = now - max(0.0, float(pre_accident_seconds))
        while self._records and self._records[0].monotonic_timestamp < cutoff:
            self._records.popleft()


BRIDGE_EVENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": True,
    "properties": {
        "type": {"type": "string"},
        "index": {"type": "integer"},
        "event": {"type": "string"},
        "monotonic_timestamp": {"type": "number"},
        "wall_time_ns": {"type": "integer"},
        "payload": {},
    },
}


def without_front_camera(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload
    filtered = dict(payload)
    for key in FRONT_CAMERA_IMAGE_KEYS:
        filtered.pop(key, None)
    return filtered


def json_safe(value: Any) -> Any:
    if isinstance(value, bytes):
        return {
            "encoding": "base64",
            "payload": base64.b64encode(value).decode("ascii"),
        }
    if isinstance(value, tuple):
        return [json_safe(item) for item in value]
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    return value


def accident_log_filename(created_at: datetime) -> str:
    timestamp = created_at.strftime("%Y-%m-%d %H:%M:%S")
    milliseconds = created_at.microsecond // 1000
    return f"autodrive {timestamp}:{milliseconds:03d}.mcap"


def accident_log_record_from_path(path: Path) -> AccidentLogRecord:
    stat = path.stat()
    return AccidentLogRecord(
        filename=path.name,
        path=str(path),
        time=accident_log_time_from_filename(path.name),
        size_bytes=stat.st_size,
    )


def accident_log_time_from_filename(filename: str) -> str:
    prefix = "autodrive "
    suffix = ".mcap"
    if filename.startswith(prefix) and filename.endswith(suffix):
        return filename[len(prefix) : -len(suffix)]
    return filename


def list_accident_logs(output_dir: Path | str = "accident_logs") -> list[AccidentLogRecord]:
    directory = Path(output_dir)
    if not directory.exists():
        return []
    return [
        accident_log_record_from_path(path)
        for path in sorted(directory.glob("autodrive *.mcap"), reverse=True)
        if path.is_file()
    ]
