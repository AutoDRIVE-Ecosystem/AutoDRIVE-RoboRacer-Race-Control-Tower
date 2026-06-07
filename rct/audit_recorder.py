# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from time import time_ns
from typing import Any, Iterable

AUDIT_FILENAME = "audit.mcap"
AUDIT_TOPIC = "/rct/audit/log"


@dataclass(frozen=True)
class AuditLogRecord:
    index: int
    timestamp_ns: int
    time: str
    event_type: str
    text: str
    race_number: int = 1
    kind: str = "Others"
    accident_log_filename: str | None = None
    accident_log_time: str | None = None
    decision_mode: str | None = None
    decision_result: dict[str, Any] | None = None
    memo: str | None = None


class AuditRecorder:
    def __init__(self, output_dir: Path | str = "race_records") -> None:
        self.output_dir = Path(output_dir)

    @property
    def path(self) -> Path:
        return self.output_dir / AUDIT_FILENAME

    def append(
        self,
        *,
        event_type: str,
        text: str,
        accident_log_filename: str | None = None,
        accident_log_time: str | None = None,
        decision_mode: str | None = None,
        decision_result: dict[str, Any] | None = None,
        memo: str | None = None,
        timestamp_ns: int | None = None,
    ) -> AuditLogRecord:
        records = list_audit_logs(self.output_dir)
        timestamp = time_ns() if timestamp_ns is None else timestamp_ns
        race_number = next_audit_race_number(records, event_type)
        record = AuditLogRecord(
            index=len(records),
            timestamp_ns=timestamp,
            time=audit_time_from_ns(timestamp),
            event_type=event_type,
            text=text,
            race_number=race_number,
            kind=audit_kind(event_type),
            accident_log_filename=accident_log_filename,
            accident_log_time=accident_log_time,
            decision_mode=decision_mode,
            decision_result=decision_result,
            memo=memo,
        )
        self.write([*records, record])
        return record

    def write(self, records: Iterable[AuditLogRecord]) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        output_path = self.path
        temporary_path = output_path.with_name(f".{output_path.name}.tmp")

        from mcap.writer import CompressionType, Writer

        try:
            with temporary_path.open("wb") as output:
                writer = Writer(output, compression=CompressionType.NONE)
                writer.start(profile="rct-audit-log")
                schema_id = writer.register_schema(
                    name="autodrive.rct.AuditLogEvent",
                    encoding="jsonschema",
                    data=json.dumps(AUDIT_EVENT_SCHEMA, separators=(",", ":")).encode("utf-8"),
                )
                channel_id = writer.register_channel(
                    topic=AUDIT_TOPIC,
                    message_encoding="json",
                    schema_id=schema_id,
                )
                for index, record in enumerate(records):
                    payload = asdict(record)
                    payload["index"] = index
                    data = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
                    writer.add_message(
                        channel_id=channel_id,
                        log_time=record.timestamp_ns,
                        publish_time=record.timestamp_ns,
                        data=data,
                    )
                writer.finish()
            temporary_path.replace(output_path)
        finally:
            if temporary_path.exists():
                temporary_path.unlink()


AUDIT_EVENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": True,
    "properties": {
        "index": {"type": "integer"},
        "timestamp_ns": {"type": "integer"},
        "time": {"type": "string"},
        "event_type": {"type": "string"},
        "text": {"type": "string"},
        "race_number": {"type": "integer"},
        "kind": {"type": "string"},
        "accident_log_filename": {"type": ["string", "null"]},
        "accident_log_time": {"type": ["string", "null"]},
        "decision_mode": {"type": ["string", "null"]},
        "decision_result": {"type": ["object", "null"]},
        "memo": {"type": ["string", "null"]},
    },
}


def audit_time_from_ns(timestamp_ns: int) -> str:
    timestamp = datetime.fromtimestamp(timestamp_ns / 1_000_000_000)
    milliseconds = timestamp.microsecond // 1000
    return f"{timestamp:%Y-%m-%d %H:%M:%S}:{milliseconds:03d}"


def audit_kind(event_type: str) -> str:
    return {
        "race_start": "Race Start",
        "race_end": "Race End",
        "vehicle_connect": "Vehicle Connected",
        "vehicle_disconnect": "Vehicle Disconnected",
        "bridge_hz": "Bridge Hz",
        "accident_record": "Accident",
        "decision": "Decision",
    }.get(event_type, "Others")


def next_audit_race_number(records: list[AuditLogRecord], event_type: str) -> int:
    current_race_number = max((record.race_number for record in records), default=0)
    if event_type == "race_start":
        return current_race_number + 1
    return max(1, current_race_number)


def audit_record_from_payload(payload: dict[str, Any], index: int) -> AuditLogRecord:
    timestamp_ns = int(payload.get("timestamp_ns", 0))
    event_type = str(payload.get("event_type") or "unknown")
    try:
        race_number = int(payload.get("race_number", 0))
    except (TypeError, ValueError):
        race_number = 0
    return AuditLogRecord(
        index=int(payload.get("index", index)),
        timestamp_ns=timestamp_ns,
        time=str(payload.get("time") or audit_time_from_ns(timestamp_ns)),
        event_type=event_type,
        text=str(payload.get("text") or ""),
        race_number=race_number,
        kind=payload.get("kind") if isinstance(payload.get("kind"), str) else audit_kind(event_type),
        accident_log_filename=payload.get("accident_log_filename") if isinstance(payload.get("accident_log_filename"), str) else None,
        accident_log_time=payload.get("accident_log_time") if isinstance(payload.get("accident_log_time"), str) else None,
        decision_mode=payload.get("decision_mode") if isinstance(payload.get("decision_mode"), str) else None,
        decision_result=payload.get("decision_result") if isinstance(payload.get("decision_result"), dict) else None,
        memo=payload.get("memo") if isinstance(payload.get("memo"), str) else None,
    )


def list_audit_logs(output_dir: Path | str = "race_records") -> list[AuditLogRecord]:
    path = Path(output_dir) / AUDIT_FILENAME
    if not path.is_file():
        return []

    from mcap.exceptions import EndOfFile
    from mcap.reader import NonSeekingReader

    records: list[AuditLogRecord] = []
    with path.open("rb") as mcap_file:
        reader = NonSeekingReader(mcap_file)
        try:
            for _schema, channel, message in reader.iter_messages(
                topics=(AUDIT_TOPIC,),
                log_time_order=False,
            ):
                if channel.topic != AUDIT_TOPIC:
                    continue
                try:
                    payload = json.loads(message.data.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
                if isinstance(payload, dict):
                    payload.setdefault("timestamp_ns", message.log_time)
                    records.append(audit_record_from_payload(payload, len(records)))
        except EndOfFile:
            pass

    records.sort(key=lambda record: (record.timestamp_ns, record.index))
    normalized_records: list[AuditLogRecord] = []
    current_race_number = 0
    for index, record in enumerate(records):
        if record.race_number > 0:
            current_race_number = record.race_number
        elif record.event_type == "race_start":
            current_race_number += 1
        elif current_race_number <= 0:
            current_race_number = 1

        normalized_records.append(
            AuditLogRecord(
                index=index,
                timestamp_ns=record.timestamp_ns,
                time=record.time,
                event_type=record.event_type,
                text=record.text,
                race_number=current_race_number,
                kind=record.kind or audit_kind(record.event_type),
                accident_log_filename=record.accident_log_filename,
                accident_log_time=record.accident_log_time,
                decision_mode=record.decision_mode,
                decision_result=record.decision_result,
                memo=record.memo,
            )
        )
    return normalized_records
