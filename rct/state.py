# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from threading import RLock
from typing import Any, Iterable, Mapping

DEFAULT_PENALTY_SW_ANALYSIS_SETTINGS: dict[str, bool] = {
    "rear_end_collision": True,
    "single_vehicle_collision": True,
    "unsafe_lateral_movement": True,
    "late_braking_divebomb": True,
    "squeeze_at_corner_exit": True,
    "unsafe_rejoin": True,
    "shared_racing_incident": True,
}

DEFAULT_DECISION_PACK_V2_GRAPH_SETTINGS: dict[str, bool] = {
    "G01": True,
    "G02": True,
    "G03": True,
    "G04": True,
    "G05": True,
    "G06": True,
    "G07": True,
    "G08": True,
    "G09": True,
    "G10": True,
    "G11": True,
    "G12": True,
    "G13": True,
    "G14": True,
    "G15": True,
}

DEFAULT_DECISION_PACK_V2_COLLISION_TYPE_SETTINGS: dict[str, bool] = {
    "CT1": True,
    "CT2": True,
    "CT3": True,
    "CT4": True,
    "CT5": True,
    "CT6": True,
    "CT7": True,
}


@dataclass
class DevKitMonitorState:
    name: str
    vehicle_id: int
    url: str
    host: str = ""
    port: int | None = None
    configured: bool = False
    enabled: bool = True
    connected: bool = False
    queued_messages: int = 0
    bridge_hz: float = 0.0
    bridge_per_minute: int = 0


@dataclass
class AccidentLogMonitorState:
    filename: str
    path: str
    time: str
    size_bytes: int
    decision_record: dict[str, Any] | None = None


@dataclass
class AuditLogMonitorState:
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


@dataclass
class PenaltyDecisionMonitorState:
    active: bool = False
    collision_vehicle_ids: list[int] | None = None
    filtered_vehicle_ids: list[int] | None = None
    penalty_vehicle_id: int | None = None
    victim_vehicle_id: int | None = None
    release_delay_seconds: float = 2.0


class RaceControlState:
    def __init__(self) -> None:
        self._lock = RLock()
        self._revision = 0
        self._simulator_clients = 0
        self._monitor_clients = 0
        self._devkits: dict[str, DevKitMonitorState] = {}
        self._topic_selections: dict[str, bool] = {}
        self._accident_recorder_settings: dict[str, float | bool] = {
            "pre_accident_seconds": 5.0,
            "include_camera": False,
        }
        self._penalty_rule_settings: dict[str, Any] = {
            "restart_delay_seconds": 2.0,
            "decision_pack_version": "v2",
            "sw_analysis": dict(DEFAULT_PENALTY_SW_ANALYSIS_SETTINGS),
            "decision_pack_v2": {
                "automatic_decision": False,
                "enable_evaluation": False,
                "graphs": dict(DEFAULT_DECISION_PACK_V2_GRAPH_SETTINGS),
                "collision_types": dict(DEFAULT_DECISION_PACK_V2_COLLISION_TYPE_SETTINGS),
            },
        }
        self._racing_rule_settings: dict[str, float | bool] = {
            "total_lap_count": 10,
            "maximum_penalty_count": 0,
            "celebration_with_confetti": True,
        }
        self._audit_rule_settings: dict[str, float | bool] = {
            "bridge_hz_maximum": 120.0,
            "bridge_hz_minimum": 20.0,
            "bridge_hz_drop_percent": 25.0,
        }
        self._accident_logs: list[AccidentLogMonitorState] = []
        self._audit_log: list[AuditLogMonitorState] = []
        self._penalty_decision = PenaltyDecisionMonitorState(
            collision_vehicle_ids=[],
            filtered_vehicle_ids=[],
        )
        self._vehicle_penalties: dict[int, int] = {}
        self._race_result: dict[str, Any] = {
            "active": False,
            "winner_vehicle_id": None,
            "loser_vehicle_id": None,
            "reason": None,
        }
        self._race_time_started_at: float | None = None
        self._race_time_elapsed_seconds = 0.0
        self._review_time_started_at: float | None = None
        self._review_time_elapsed_seconds = 0.0

    def configure_devkits(self, devkits: Iterable[DevKitMonitorState]) -> None:
        with self._lock:
            self._devkits = {devkit.name: devkit for devkit in devkits}
            self._revision += 1

    def set_simulator_clients(self, count: int) -> None:
        with self._lock:
            if self._simulator_clients == count:
                return
            self._simulator_clients = count
            self._revision += 1

    def start_race_time(self, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        with self._lock:
            self._race_time_elapsed_seconds = 0.0
            self._race_time_started_at = now
            self._review_time_elapsed_seconds = 0.0
            self._review_time_started_at = None
            self._revision += 1

    def stop_race_time(self, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        with self._lock:
            if self._race_time_started_at is None:
                return
            self._race_time_elapsed_seconds += max(0.0, now - self._race_time_started_at)
            self._race_time_started_at = None
            self._revision += 1

    def race_time_seconds(self, now: float | None = None) -> float:
        now = time.monotonic() if now is None else now
        with self._lock:
            if self._race_time_started_at is None:
                return self._race_time_elapsed_seconds
            return self._race_time_elapsed_seconds + max(0.0, now - self._race_time_started_at)

    def start_review_time(self, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        with self._lock:
            if self._review_time_started_at is not None:
                return
            self._review_time_started_at = now
            self._revision += 1

    def stop_review_time(self, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        with self._lock:
            if self._review_time_started_at is None:
                return
            self._review_time_elapsed_seconds += max(0.0, now - self._review_time_started_at)
            self._review_time_started_at = None
            self._revision += 1

    def review_time_seconds(self, now: float | None = None) -> float:
        now = time.monotonic() if now is None else now
        with self._lock:
            if self._review_time_started_at is None:
                return self._review_time_elapsed_seconds
            return self._review_time_elapsed_seconds + max(0.0, now - self._review_time_started_at)

    def set_monitor_clients(self, count: int) -> None:
        with self._lock:
            if self._monitor_clients == count:
                return
            self._monitor_clients = count
            self._revision += 1

    def set_devkit_connected(self, name: str, connected: bool) -> None:
        with self._lock:
            if self._devkits[name].connected == connected:
                return
            self._devkits[name].connected = connected
            self._revision += 1

    def set_devkit_endpoint(
        self,
        name: str,
        url: str,
        host: str,
        port: int,
        configured: bool,
    ) -> None:
        with self._lock:
            devkit = self._devkits[name]
            if (
                devkit.url == url
                and devkit.host == host
                and devkit.port == port
                and devkit.configured == configured
            ):
                return
            devkit.url = url
            devkit.host = host
            devkit.port = port
            devkit.configured = configured
            self._revision += 1

    def set_devkit_enabled(self, name: str, enabled: bool) -> None:
        with self._lock:
            if self._devkits[name].enabled == enabled:
                return
            self._devkits[name].enabled = enabled
            self._revision += 1

    def set_devkit_queue_size(self, name: str, queued_messages: int) -> None:
        with self._lock:
            if self._devkits[name].queued_messages == queued_messages:
                return
            self._devkits[name].queued_messages = queued_messages
            self._revision += 1

    def set_devkit_bridge_rate(
        self,
        name: str,
        bridge_hz: float,
        bridge_per_minute: int,
    ) -> None:
        with self._lock:
            devkit = self._devkits[name]
            if (
                devkit.bridge_hz == bridge_hz
                and devkit.bridge_per_minute == bridge_per_minute
            ):
                return
            devkit.bridge_hz = bridge_hz
            devkit.bridge_per_minute = bridge_per_minute
            self._revision += 1

    def set_topic_selections(self, topic_selections: Mapping[str, bool]) -> None:
        normalized_topic_selections = {
            str(topic): bool(enabled) for topic, enabled in topic_selections.items()
        }
        with self._lock:
            if self._topic_selections == normalized_topic_selections:
                return
            self._topic_selections = normalized_topic_selections
            self._revision += 1

    def update_topic_selections(self, topic_selections: Mapping[str, bool]) -> None:
        normalized_updates = {
            str(topic): bool(enabled) for topic, enabled in topic_selections.items()
        }
        with self._lock:
            next_topic_selections = dict(self._topic_selections)
            next_topic_selections.update(normalized_updates)
            if self._topic_selections == next_topic_selections:
                return
            self._topic_selections = next_topic_selections
            self._revision += 1

    def topic_selections(self) -> dict[str, bool]:
        with self._lock:
            return dict(self._topic_selections)

    def set_accident_recorder_settings(
        self,
        *,
        pre_accident_seconds: float,
        include_camera: bool,
    ) -> None:
        next_settings = {
            "pre_accident_seconds": float(pre_accident_seconds),
            "include_camera": bool(include_camera),
        }
        with self._lock:
            if self._accident_recorder_settings == next_settings:
                return
            self._accident_recorder_settings = next_settings
            self._revision += 1

    def accident_recorder_settings(self) -> dict[str, float | bool]:
        with self._lock:
            return dict(self._accident_recorder_settings)

    def set_penalty_rule_settings(
        self,
        *,
        restart_delay_seconds: float,
        decision_pack_version: str = "v2",
        sw_analysis: Mapping[str, bool] | None = None,
        decision_pack_v2: Mapping[str, Any] | None = None,
    ) -> None:
        next_sw_analysis = dict(DEFAULT_PENALTY_SW_ANALYSIS_SETTINGS)
        if sw_analysis is not None:
            next_sw_analysis.update(sw_analysis)
        next_graphs = dict(DEFAULT_DECISION_PACK_V2_GRAPH_SETTINGS)
        next_collision_types = dict(DEFAULT_DECISION_PACK_V2_COLLISION_TYPE_SETTINGS)
        next_automatic_decision = False
        next_enable_evaluation = False
        if decision_pack_v2 is not None:
            next_automatic_decision = bool(decision_pack_v2.get("automatic_decision", False))
            next_enable_evaluation = bool(decision_pack_v2.get("enable_evaluation", False))
            graph_settings = decision_pack_v2.get("graphs", {})
            if isinstance(graph_settings, Mapping):
                next_graphs.update(graph_settings)
            collision_type_settings = decision_pack_v2.get("collision_types", {})
            if isinstance(collision_type_settings, Mapping):
                next_collision_types.update(collision_type_settings)
        next_settings = {
            "restart_delay_seconds": float(restart_delay_seconds),
            "decision_pack_version": str(decision_pack_version),
            "sw_analysis": next_sw_analysis,
            "decision_pack_v2": {
                "automatic_decision": next_automatic_decision,
                "enable_evaluation": next_enable_evaluation,
                "graphs": next_graphs,
                "collision_types": next_collision_types,
            },
        }
        with self._lock:
            if self._penalty_rule_settings == next_settings:
                return
            self._penalty_rule_settings = next_settings
            self._revision += 1

    def penalty_rule_settings(self) -> dict[str, Any]:
        with self._lock:
            settings = dict(self._penalty_rule_settings)
            settings["sw_analysis"] = dict(settings.get("sw_analysis", {}))
            v2_settings = settings.get("decision_pack_v2", {})
            if not isinstance(v2_settings, dict):
                v2_settings = {}
            settings["decision_pack_v2"] = {
                "automatic_decision": bool(v2_settings.get("automatic_decision", False)),
                "enable_evaluation": bool(v2_settings.get("enable_evaluation", False)),
                "graphs": dict(v2_settings.get("graphs", {})),
                "collision_types": dict(v2_settings.get("collision_types", {})),
            }
            return settings

    def set_racing_rule_settings(
        self,
        *,
        total_lap_count: int,
        maximum_penalty_count: int,
        celebration_with_confetti: bool,
    ) -> None:
        next_settings = {
            "total_lap_count": int(total_lap_count),
            "maximum_penalty_count": int(maximum_penalty_count),
            "celebration_with_confetti": bool(celebration_with_confetti),
        }
        with self._lock:
            if self._racing_rule_settings == next_settings:
                return
            self._racing_rule_settings = next_settings
            self._revision += 1

    def racing_rule_settings(self) -> dict[str, float | bool]:
        with self._lock:
            return dict(self._racing_rule_settings)

    def set_audit_rule_settings(
        self,
        *,
        bridge_hz_maximum: float,
        bridge_hz_minimum: float,
        bridge_hz_drop_percent: float,
    ) -> None:
        next_settings = {
            "bridge_hz_maximum": float(bridge_hz_maximum),
            "bridge_hz_minimum": float(bridge_hz_minimum),
            "bridge_hz_drop_percent": float(bridge_hz_drop_percent),
        }
        with self._lock:
            if self._audit_rule_settings == next_settings:
                return
            self._audit_rule_settings = next_settings
            self._revision += 1

    def audit_rule_settings(self) -> dict[str, float | bool]:
        with self._lock:
            return dict(self._audit_rule_settings)

    def set_accident_logs(self, accident_logs: Iterable[AccidentLogMonitorState]) -> None:
        next_logs = list(accident_logs)
        with self._lock:
            if self._accident_logs == next_logs:
                return
            self._accident_logs = next_logs
            self._revision += 1

    def add_accident_log(self, accident_log: AccidentLogMonitorState) -> None:
        with self._lock:
            self._accident_logs = [
                accident_log,
                *[log for log in self._accident_logs if log.filename != accident_log.filename],
            ]
            self._revision += 1

    def accident_logs(self) -> list[dict[str, Any]]:
        with self._lock:
            return [asdict(accident_log) for accident_log in self._accident_logs]

    def set_audit_log(self, audit_log: Iterable[AuditLogMonitorState]) -> None:
        next_log = list(audit_log)
        with self._lock:
            if self._audit_log == next_log:
                return
            self._audit_log = next_log
            self._revision += 1

    def add_audit_log(self, audit_log: AuditLogMonitorState) -> None:
        with self._lock:
            self._audit_log = [
                *self._audit_log,
                audit_log,
            ]
            self._revision += 1

    def audit_log(self) -> list[dict[str, Any]]:
        with self._lock:
            return [asdict(audit_log) for audit_log in self._audit_log]

    def set_penalty_decision(
        self,
        *,
        active: bool,
        collision_vehicle_ids: Iterable[int] | None = None,
        filtered_vehicle_ids: Iterable[int] | None = None,
        penalty_vehicle_id: int | None = None,
        victim_vehicle_id: int | None = None,
        release_delay_seconds: float = 2.0,
    ) -> None:
        next_decision = PenaltyDecisionMonitorState(
            active=bool(active),
            collision_vehicle_ids=sorted(int(vehicle_id) for vehicle_id in (collision_vehicle_ids or [])),
            filtered_vehicle_ids=sorted(int(vehicle_id) for vehicle_id in (filtered_vehicle_ids or [])),
            penalty_vehicle_id=penalty_vehicle_id,
            victim_vehicle_id=victim_vehicle_id,
            release_delay_seconds=float(release_delay_seconds),
        )
        with self._lock:
            if self._penalty_decision == next_decision:
                return
            self._penalty_decision = next_decision
            self._revision += 1

    def penalty_decision(self) -> dict[str, Any]:
        with self._lock:
            return asdict(self._penalty_decision)

    def increment_vehicle_penalty(self, vehicle_id: int) -> int:
        with self._lock:
            count = self._vehicle_penalties.get(vehicle_id, 0) + 1
            self._vehicle_penalties[vehicle_id] = count
            self._revision += 1
            return count

    def vehicle_penalties(self) -> dict[str, int]:
        with self._lock:
            return {str(vehicle_id): count for vehicle_id, count in sorted(self._vehicle_penalties.items())}

    def reset_vehicle_penalties(self) -> None:
        with self._lock:
            if not self._vehicle_penalties:
                return
            self._vehicle_penalties.clear()
            self._revision += 1

    def set_race_result(
        self,
        *,
        active: bool,
        winner_vehicle_id: int | None = None,
        loser_vehicle_id: int | None = None,
        reason: str | None = None,
    ) -> None:
        next_result = {
            "active": bool(active),
            "winner_vehicle_id": winner_vehicle_id,
            "loser_vehicle_id": loser_vehicle_id,
            "reason": reason,
        }
        with self._lock:
            if self._race_result == next_result:
                return
            self._race_result = next_result
            self._revision += 1

    def race_result(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._race_result)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "revision": self._revision,
                "simulator_clients": self._simulator_clients,
                "monitor_clients": self._monitor_clients,
                "devkits": [asdict(devkit) for devkit in self._devkits.values()],
                "topic_selections": dict(self._topic_selections),
                "accident_recorder": dict(self._accident_recorder_settings),
                "penalty_rule": self.penalty_rule_settings(),
                "racing_rule": dict(self._racing_rule_settings),
                "audit_rule": dict(self._audit_rule_settings),
                "accident_logs": [asdict(accident_log) for accident_log in self._accident_logs],
                "audit_log": [asdict(audit_log) for audit_log in self._audit_log],
                "penalty_decision": asdict(self._penalty_decision),
                "vehicle_penalties": {str(vehicle_id): count for vehicle_id, count in sorted(self._vehicle_penalties.items())},
                "race_result": dict(self._race_result),
                "race_time_seconds": self.race_time_seconds(),
                "review_time_seconds": self.review_time_seconds(),
            }
