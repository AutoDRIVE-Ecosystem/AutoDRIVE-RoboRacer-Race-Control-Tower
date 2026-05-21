# SPDX-License-Identifier: BSD-3-Clause

import unittest

from rct.state import AccidentLogMonitorState, DevKitMonitorState, RaceControlState


class RaceControlStateTests(unittest.TestCase):
    def test_snapshot_contains_shared_monitor_state(self):
        state = RaceControlState()
        state.configure_devkits(
            [
                DevKitMonitorState("devkit:1", 1, "ws://127.0.0.1:4568"),
                DevKitMonitorState("devkit:2", 2, "ws://127.0.0.1:4569"),
            ]
        )

        state.set_simulator_clients(1)
        state.set_monitor_clients(2)
        state.set_devkit_connected("devkit:1", True)
        state.set_devkit_queue_size("devkit:1", 3)

        snapshot = state.snapshot()

        self.assertEqual(snapshot["simulator_clients"], 1)
        self.assertEqual(snapshot["monitor_clients"], 2)
        self.assertEqual(
            snapshot["devkits"][0],
            {
                "name": "devkit:1",
                "vehicle_id": 1,
                "url": "ws://127.0.0.1:4568",
                "host": "",
                "port": None,
                "configured": False,
                "enabled": True,
                "connected": True,
                "queued_messages": 3,
                "bridge_hz": 0.0,
                "bridge_per_minute": 0,
            },
        )

    def test_snapshot_tracks_devkit_endpoint_and_enabled_state(self):
        state = RaceControlState()
        state.configure_devkits([DevKitMonitorState("devkit:1", 1, "")])

        state.set_devkit_endpoint("devkit:1", "ws://10.0.2.2:4568", "10.0.2.2", 4568, True)
        state.set_devkit_enabled("devkit:1", False)

        snapshot = state.snapshot()

        self.assertEqual(snapshot["devkits"][0]["url"], "ws://10.0.2.2:4568")
        self.assertEqual(snapshot["devkits"][0]["host"], "10.0.2.2")
        self.assertEqual(snapshot["devkits"][0]["port"], 4568)
        self.assertTrue(snapshot["devkits"][0]["configured"])
        self.assertFalse(snapshot["devkits"][0]["enabled"])

    def test_snapshot_tracks_devkit_bridge_rate(self):
        state = RaceControlState()
        state.configure_devkits([DevKitMonitorState("devkit:1", 1, "")])

        state.set_devkit_bridge_rate("devkit:1", 0.5, 30)

        snapshot = state.snapshot()

        self.assertEqual(snapshot["devkits"][0]["bridge_hz"], 0.5)
        self.assertEqual(snapshot["devkits"][0]["bridge_per_minute"], 30)

    def test_snapshot_tracks_topic_selections(self):
        state = RaceControlState()
        state.set_topic_selections(
            {
                "/autodrive/roboracer_1/front_camera": False,
                "/autodrive/roboracer_1/imu": True,
            }
        )

        snapshot = state.snapshot()

        self.assertEqual(
            snapshot["topic_selections"],
            {
                "/autodrive/roboracer_1/front_camera": False,
                "/autodrive/roboracer_1/imu": True,
            },
        )

    def test_snapshot_tracks_accident_recorder_settings(self):
        state = RaceControlState()

        self.assertEqual(state.snapshot()["accident_recorder"]["pre_accident_seconds"], 5.0)
        self.assertFalse(state.snapshot()["accident_recorder"]["include_camera"])

        state.set_accident_recorder_settings(pre_accident_seconds=3.5, include_camera=True)

        self.assertEqual(state.snapshot()["accident_recorder"]["pre_accident_seconds"], 3.5)
        self.assertTrue(state.snapshot()["accident_recorder"]["include_camera"])

    def test_snapshot_tracks_penalty_rule_settings(self):
        state = RaceControlState()

        self.assertEqual(state.snapshot()["penalty_rule"]["restart_delay_seconds"], 2.0)
        self.assertTrue(state.snapshot()["penalty_rule"]["sw_analysis"]["rear_end_collision"])

        state.set_penalty_rule_settings(
            restart_delay_seconds=1.5,
            sw_analysis={
                "rear_end_collision": False,
                "unsafe_lateral_movement": True,
                "late_braking_divebomb": True,
                "squeeze_at_corner_exit": True,
                "unsafe_rejoin": True,
                "shared_racing_incident": True,
            },
        )

        self.assertEqual(state.snapshot()["penalty_rule"]["restart_delay_seconds"], 1.5)
        self.assertFalse(state.snapshot()["penalty_rule"]["sw_analysis"]["rear_end_collision"])

    def test_snapshot_tracks_racing_rule_settings(self):
        state = RaceControlState()

        self.assertEqual(state.snapshot()["racing_rule"]["total_lap_count"], 10)
        self.assertEqual(state.snapshot()["racing_rule"]["maximum_penalty_count"], 0)
        self.assertTrue(state.snapshot()["racing_rule"]["celebration_with_confetti"])

        state.set_racing_rule_settings(
            total_lap_count=5,
            maximum_penalty_count=2,
            celebration_with_confetti=False,
        )

        self.assertEqual(state.snapshot()["racing_rule"]["total_lap_count"], 5)
        self.assertEqual(state.snapshot()["racing_rule"]["maximum_penalty_count"], 2)
        self.assertFalse(state.snapshot()["racing_rule"]["celebration_with_confetti"])

    def test_snapshot_tracks_accident_logs(self):
        state = RaceControlState()
        state.add_accident_log(
            AccidentLogMonitorState(
                filename="autodrive 2026-05-19 12:00:00:001.mcap",
                path="accident_logs/autodrive 2026-05-19 12:00:00:001.mcap",
                time="2026-05-19 12:00:00:001",
                size_bytes=123,
            )
        )

        self.assertEqual(
            state.snapshot()["accident_logs"],
            [
                {
                    "filename": "autodrive 2026-05-19 12:00:00:001.mcap",
                    "path": "accident_logs/autodrive 2026-05-19 12:00:00:001.mcap",
                    "time": "2026-05-19 12:00:00:001",
                    "size_bytes": 123,
                }
            ],
        )

    def test_snapshot_tracks_penalty_decision(self):
        state = RaceControlState()

        state.set_penalty_decision(
            active=True,
            collision_vehicle_ids=[2, 1],
            filtered_vehicle_ids=[1, 2],
            penalty_vehicle_id=2,
            victim_vehicle_id=1,
            release_delay_seconds=2.0,
        )

        self.assertEqual(
            state.snapshot()["penalty_decision"],
            {
                "active": True,
                "collision_vehicle_ids": [1, 2],
                "filtered_vehicle_ids": [1, 2],
                "penalty_vehicle_id": 2,
                "victim_vehicle_id": 1,
                "release_delay_seconds": 2.0,
            },
        )

    def test_snapshot_tracks_vehicle_penalties(self):
        state = RaceControlState()

        self.assertEqual(state.snapshot()["vehicle_penalties"], {})

        self.assertEqual(state.increment_vehicle_penalty(2), 1)
        self.assertEqual(state.increment_vehicle_penalty(2), 2)

        self.assertEqual(state.snapshot()["vehicle_penalties"], {"2": 2})

        state.reset_vehicle_penalties()

        self.assertEqual(state.snapshot()["vehicle_penalties"], {})

    def test_revision_changes_only_when_values_change(self):
        state = RaceControlState()
        state.configure_devkits([DevKitMonitorState("devkit:1", 1, "ws://127.0.0.1:4568")])
        first_revision = state.snapshot()["revision"]

        state.set_monitor_clients(0)
        self.assertEqual(state.snapshot()["revision"], first_revision)

        state.set_monitor_clients(1)
        self.assertGreater(state.snapshot()["revision"], first_revision)


if __name__ == "__main__":
    unittest.main()
