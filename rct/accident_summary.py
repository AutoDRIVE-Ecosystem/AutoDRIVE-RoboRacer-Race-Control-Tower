# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

from .bridge import extract_lidar_range_arrays, extract_lidar_scans, extract_monitor_telemetry
from .decision import load_decision_record

LOGGER = logging.getLogger("rct")
LIDAR_REPLAY_ANGLE_MIN = -2.35619
LIDAR_REPLAY_ANGLE_INCREMENT = 0.004363323
LIDAR_REPLAY_MAX_RANGES = 270


def replay_lidar_ranges_payload(ranges: list[float]) -> dict[str, Any]:
    if len(ranges) <= LIDAR_REPLAY_MAX_RANGES:
        return {
            "ranges": ranges,
            "angle_min": LIDAR_REPLAY_ANGLE_MIN,
            "angle_increment": LIDAR_REPLAY_ANGLE_INCREMENT,
        }
    step = max(1, round(len(ranges) / LIDAR_REPLAY_MAX_RANGES))
    return {
        "ranges": ranges[::step],
        "angle_min": LIDAR_REPLAY_ANGLE_MIN,
        "angle_increment": LIDAR_REPLAY_ANGLE_INCREMENT * step,
        "sample_step": step,
    }


def accident_log_summary_from_mcap(
    path: Path,
    devkit_vehicle_ids: tuple[int, ...] = (),
    *,
    include_lidar_scan: bool = True,
) -> dict[str, Any]:
    from mcap.exceptions import EndOfFile
    from mcap.reader import NonSeekingReader

    frames: list[dict[str, Any]] = []
    metadata: dict[str, Any] = {}
    complete = True
    with path.open("rb") as mcap_file:
        reader = NonSeekingReader(mcap_file)
        try:
            for _schema, channel, message in reader.iter_messages(
                topics=("/rct/accident/metadata", "/rct/accident/bridge"),
                log_time_order=False,
            ):
                try:
                    payload = json.loads(message.data.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue

                if channel.topic == "/rct/accident/metadata":
                    metadata = payload
                    continue

                bridge_payload = payload.get("payload") if isinstance(payload, dict) else None
                vehicles = extract_monitor_telemetry(bridge_payload)
                if not vehicles:
                    continue
                if include_lidar_scan:
                    lidar_vehicle_ids = set(vehicles) | set(devkit_vehicle_ids) | {1, 2}
                    lidar_positions = {
                        vehicle_id: {"ips": values["ips"]}
                        for vehicle_id, values in vehicles.items()
                        if isinstance(values.get("ips"), dict)
                    }
                    lidar_scans: dict[int, Any] = {
                        vehicle_id: replay_lidar_ranges_payload(ranges)
                        for vehicle_id, ranges in extract_lidar_range_arrays(bridge_payload, lidar_vehicle_ids).items()
                    }
                    for vehicle_id, points in extract_lidar_scans(bridge_payload, lidar_vehicle_ids, lidar_positions).items():
                        lidar_scans.setdefault(vehicle_id, points)
                    for vehicle_id, points in lidar_scans.items():
                        vehicles.setdefault(vehicle_id, {})["lidar_scan"] = points

                frames.append(
                    {
                        "index": payload.get("index", len(frames)) if isinstance(payload, dict) else len(frames),
                        "log_time_ns": message.log_time,
                        "wall_time_ns": payload.get("wall_time_ns", message.log_time) if isinstance(payload, dict) else message.log_time,
                        "vehicles": {str(vehicle_id): telemetry for vehicle_id, telemetry in sorted(vehicles.items())},
                    }
                )
        except EndOfFile:
            complete = False
            LOGGER.debug("read partial accident log summary from %s before MCAP footer was available", path)

    frames.sort(key=lambda frame: frame["log_time_ns"])
    if frames:
        start_time_ns = int(frames[0]["log_time_ns"])
        end_time_ns = int(frames[-1]["log_time_ns"])
    else:
        start_time_ns = 0
        end_time_ns = 0

    duration_seconds = max(0.0, (end_time_ns - start_time_ns) / 1_000_000_000)
    for frame in frames:
        frame["time_offset_seconds"] = max(0.0, (int(frame["log_time_ns"]) - start_time_ns) / 1_000_000_000)
        frame["time_to_accident_seconds"] = frame["time_offset_seconds"] - duration_seconds

    return {
        "filename": path.name,
        "time": path.stem.removeprefix("autodrive "),
        "size_bytes": path.stat().st_size,
        "duration_seconds": duration_seconds,
        "complete": complete,
        "metadata": metadata,
        "decision_record": load_decision_record(path),
        "frames": frames,
    }


def accident_log_compact_summary_from_mcap(path: Path) -> dict[str, Any]:
    from mcap.exceptions import EndOfFile
    from mcap.reader import NonSeekingReader

    metadata: dict[str, Any] = {}
    complete = True
    with path.open("rb") as mcap_file:
        reader = NonSeekingReader(mcap_file)
        try:
            for _schema, channel, message in reader.iter_messages(
                topics=("/rct/accident/metadata",),
                log_time_order=False,
            ):
                try:
                    payload = json.loads(message.data.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
                if channel.topic == "/rct/accident/metadata":
                    metadata = payload
                    break
        except EndOfFile:
            complete = False
            LOGGER.debug("read partial compact accident log summary from %s before MCAP footer was available", path)

    return {
        "filename": path.name,
        "time": path.stem.removeprefix("autodrive "),
        "size_bytes": path.stat().st_size,
        "complete": complete,
        "metadata": metadata,
        "decision_record": load_decision_record(path),
        "frames": [],
    }


def parse_vehicle_ids(value: str) -> tuple[int, ...]:
    if not value:
        return ()
    vehicle_ids: list[int] = []
    for item in value.split(","):
        item = item.strip()
        if item:
            vehicle_ids.append(int(item))
    return tuple(vehicle_ids)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate an RCT accident MCAP replay summary.")
    parser.add_argument("path", type=Path)
    parser.add_argument("--devkit-vehicle-ids", default="")
    parser.add_argument("--no-lidar-scan", action="store_true")
    args = parser.parse_args()

    summary = accident_log_summary_from_mcap(
        args.path,
        parse_vehicle_ids(args.devkit_vehicle_ids),
        include_lidar_scan=not args.no_lidar_scan,
    )
    print(json.dumps(summary, separators=(",", ":")))


if __name__ == "__main__":
    main()
