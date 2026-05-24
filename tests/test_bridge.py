# SPDX-License-Identifier: BSD-3-Clause

import asyncio
import unittest
import base64
import gzip
from io import BytesIO
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from rct.accident_recorder import AccidentBridgeRecord, AccidentRecorder, accident_log_filename, list_accident_logs
from rct.accident_summary import accident_log_compact_summary_from_mcap
from rct.bridge import (
    BridgeHistory,
    BridgeRateTracker,
    ControlCache,
    OUTGOING_BRIDGE_DEFAULTS,
    extract_collision_counts,
    extract_lidar_range_arrays,
    extract_lidar_scans,
    extract_monitor_telemetry,
)
from rct.config import load_settings
from rct.decision import save_decision_record
from rct.ros2_mcap import bridge_payload_to_ros2_messages, convert_accident_mcap_to_ros2_mcap, vehicle_tf_transforms
from rct.server import RaceControlTower, ros2_mcap_download_filename


class BridgeHistoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_latest_returns_newest_retained_payload(self):
        history = BridgeHistory(retention_seconds=5.0)

        await history.append({"V1 Position": "1 0 0"}, now=10.0)
        await history.append({"V1 Position": "2 0 0"}, now=12.0)

        latest = await history.latest(now=12.0)

        self.assertIsNotNone(latest)
        self.assertEqual(latest.timestamp, 12.0)
        self.assertEqual(latest.payload, {"V1 Position": "2 0 0"})

    async def test_retention_prunes_payloads_older_than_last_five_seconds(self):
        history = BridgeHistory(retention_seconds=5.0)

        await history.append({"old": 1}, now=10.0)
        await history.append({"new": 2}, now=16.0)

        record = await history.oldest_after(0.0, now=16.0)

        self.assertIsNotNone(record)
        self.assertEqual(record.payload, {"new": 2})

    async def test_wait_for_oldest_after_blocks_until_newer_payload_exists(self):
        history = BridgeHistory(retention_seconds=5.0)
        latest = await history.append({"V1 Position": "10 0 0"})
        waiter = asyncio.create_task(history.wait_for_oldest_after(latest.timestamp))

        await asyncio.sleep(0)
        self.assertFalse(waiter.done())

        record = await history.append({"V1 Position": "11 0 0"})

        waited_record = await asyncio.wait_for(waiter, timeout=1.0)
        self.assertEqual(waited_record.timestamp, record.timestamp)
        self.assertEqual(waited_record.payload, {"V1 Position": "11 0 0"})


class ControlCacheTests(unittest.IsolatedAsyncioTestCase):
    async def test_control_cache_starts_with_outgoing_defaults(self):
        cache = ControlCache()

        _timestamp, snapshot = await cache.snapshot()

        expected = dict(OUTGOING_BRIDGE_DEFAULTS)
        expected.pop("origin")
        self.assertEqual(snapshot, expected)

    async def test_merge_updates_control_fields_only(self):
        cache = ControlCache()

        _timestamp, snapshot = await cache.merge(
            {
                "V1 Throttle": "0.5",
                "V1 Steering": "-0.1",
                "V1 Position": "ignored",
            },
            100.0,
        )

        self.assertEqual(snapshot["V1 Throttle"], "0.5")
        self.assertEqual(snapshot["V1 Steering"], "-0.1")
        self.assertNotIn("V1 Position", snapshot)
        self.assertEqual(snapshot["V2 Throttle"], "0.0")

    async def test_merge_can_include_origin(self):
        cache = ControlCache()

        _timestamp, snapshot = await cache.merge(
            {"V2 Throttle": "0.5"},
            100.0,
            origin_vehicle_id=2,
            include_origin=True,
        )

        self.assertEqual(snapshot["origin"], 2)


class BridgeRateTrackerTests(unittest.TestCase):
    def test_tracks_rates_over_window(self):
        tracker = BridgeRateTracker(window_seconds=60.0)

        tracker.record(1, now=100.0)
        rates = tracker.record(1, now=101.0)

        self.assertAlmostEqual(rates["bridge_hz"], 2 / 60.0)
        self.assertEqual(rates["bridge_per_minute"], 2)

    def test_prunes_old_rates(self):
        tracker = BridgeRateTracker(window_seconds=60.0)

        tracker.record(1, now=0.0)
        rates = tracker.rates(1, now=61.0)

        self.assertEqual(rates["bridge_per_minute"], 0)

    def test_default_window_is_one_second(self):
        tracker = BridgeRateTracker()

        tracker.record(1, now=100.0)
        rates = tracker.record(1, now=100.5)

        self.assertAlmostEqual(rates["bridge_hz"], 2.0)
        self.assertEqual(rates["bridge_per_minute"], 120)

    def test_rates_drop_to_zero_after_window_expires(self):
        tracker = BridgeRateTracker()

        tracker.record(1, now=100.0)
        rates = tracker.rates(1, now=101.1)

        self.assertEqual(rates["bridge_hz"], 0.0)
        self.assertEqual(rates["bridge_per_minute"], 0)


class CollisionCountTests(unittest.TestCase):
    def test_extracts_vehicle_collision_counts(self):
        counts = extract_collision_counts(
            {
                "V1 Collision Count": "1",
                "V2 collision_count": 2.0,
                "V1 Position": "ignored",
            }
        )

        self.assertEqual(counts, {1: 1, 2: 2})

    def test_ignores_non_numeric_collision_values(self):
        counts = extract_collision_counts({"V1 Collision Count": "n/a"})

        self.assertEqual(counts, {})


class AccidentRecorderTests(unittest.TestCase):
    def test_ring_buffer_keeps_pre_accident_window(self):
        recorder = AccidentRecorder()

        recorder.record_bridge_payload({"old": 1}, pre_accident_seconds=5.0, include_camera=False, now=10.0, wall_time=10)
        recorder.record_bridge_payload({"new": 2}, pre_accident_seconds=5.0, include_camera=False, now=16.0, wall_time=16)

        snapshot = recorder.snapshot(now=16.0, pre_accident_seconds=5.0)

        self.assertEqual([record.payload for record in snapshot], [{"new": 2}])

    def test_ring_buffer_omits_front_camera_when_disabled(self):
        recorder = AccidentRecorder()

        recorder.record_bridge_payload(
            {"V1 Front Camera Image": "large", "V1 Position": "1 2 3"},
            pre_accident_seconds=5.0,
            include_camera=False,
            now=10.0,
            wall_time=10,
        )

        snapshot = recorder.snapshot(now=10.0, pre_accident_seconds=5.0)

        self.assertEqual(snapshot[0].payload, {"V1 Position": "1 2 3"})

    def test_ring_buffer_keeps_front_camera_when_enabled(self):
        recorder = AccidentRecorder()

        recorder.record_bridge_payload(
            {"V1 Front Camera Image": "large", "V1 Position": "1 2 3"},
            pre_accident_seconds=5.0,
            include_camera=True,
            now=10.0,
            wall_time=10,
        )

        snapshot = recorder.snapshot(now=10.0, pre_accident_seconds=5.0)

        self.assertEqual(snapshot[0].payload, {"V1 Front Camera Image": "large", "V1 Position": "1 2 3"})

    def test_accident_log_filename_uses_requested_format(self):
        filename = accident_log_filename(datetime(2026, 5, 19, 1, 2, 3, 456789))

        self.assertEqual(filename, "autodrive 2026-05-19 01:02:03:456.mcap")

    def test_write_mcap_publishes_final_file_without_temporary_file(self):
        recorder = AccidentRecorder()
        with TemporaryDirectory() as temporary_directory:
            recorder.output_dir = Path(temporary_directory)

            log = recorder.write_mcap(
                [
                    AccidentBridgeRecord(
                        monotonic_timestamp=1.0,
                        wall_time_ns=1_000_000_000,
                        event="simulator/Bridge",
                        payload={"V1 Position": "1 2 0"},
                    )
                ],
                trigger_vehicle_id=1,
                collision_count=1,
                created_at=datetime(2026, 5, 19, 1, 2, 3, 456000),
            )

            self.assertTrue(Path(log.path).exists())
            self.assertEqual(list(Path(temporary_directory).glob("*.tmp")), [])

    def test_compact_summary_omits_frames_and_keeps_decision_metadata(self):
        recorder = AccidentRecorder()
        with TemporaryDirectory() as temporary_directory:
            recorder.output_dir = Path(temporary_directory)
            log = recorder.write_mcap(
                [
                    AccidentBridgeRecord(
                        monotonic_timestamp=1.0,
                        wall_time_ns=1_000_000_000,
                        event="simulator/Bridge",
                        payload={"V1 Position": "1 2 0"},
                    )
                ],
                trigger_vehicle_id=1,
                collision_count=1,
                created_at=datetime(2026, 5, 19, 1, 2, 3, 456000),
            )
            save_decision_record(Path(log.path), fault_vehicle_id=1)

            summary = accident_log_compact_summary_from_mcap(Path(log.path))

        self.assertEqual(summary["frames"], [])
        self.assertEqual(summary["metadata"]["trigger_vehicle_id"], 1)
        self.assertEqual(summary["decision_record"]["fault_vehicle_id"], 1)

    def test_lists_accident_logs_newest_first(self):
        with TemporaryDirectory() as temporary_directory:
            old_path = f"{temporary_directory}/autodrive 2026-05-19 01:02:03:456.mcap"
            new_path = f"{temporary_directory}/autodrive 2026-05-19 01:02:04:000.mcap"
            with open(old_path, "wb") as output:
                output.write(b"old")
            with open(new_path, "wb") as output:
                output.write(b"new")

            logs = list_accident_logs(temporary_directory)

        self.assertEqual([log.filename for log in logs], [
            "autodrive 2026-05-19 01:02:04:000.mcap",
            "autodrive 2026-05-19 01:02:03:456.mcap",
        ])

    def test_converts_accident_bridge_mcap_to_ros2_topics_for_both_vehicles(self):
        from mcap.reader import NonSeekingReader

        recorder = AccidentRecorder()
        with TemporaryDirectory() as temporary_directory:
            recorder.output_dir = Path(temporary_directory)
            log = recorder.write_mcap(
                [
                    AccidentBridgeRecord(
                        monotonic_timestamp=1.0,
                        wall_time_ns=1_000_000_000,
                        event="simulator/Bridge",
                        payload={
                            "V1 Throttle": "0.1",
                            "V1 Position": "1 2 0",
                            "V1 Orientation Quaternion": "0 0 0 1",
                            "V2 Throttle": "0.2",
                            "V2 Position": "3 4 0",
                            "V2 Orientation Quaternion": "0 0 0 1",
                        },
                    )
                ],
                trigger_vehicle_id=1,
                collision_count=1,
                created_at=datetime(2026, 5, 19, 1, 2, 3, 456000),
            )

            converted = convert_accident_mcap_to_ros2_mcap(Path(log.path))
            reader = NonSeekingReader(BytesIO(converted))
            messages = list(reader.iter_messages(log_time_order=False))

        channels = {channel.topic: channel for _schema, channel, _message in messages}
        self.assertIn("/autodrive/roboracer_1/throttle", channels)
        self.assertIn("/autodrive/roboracer_1/ips", channels)
        self.assertIn("/autodrive/roboracer_2/throttle", channels)
        self.assertIn("/autodrive/roboracer_2/ips", channels)
        self.assertIn("/tf", channels)
        self.assertNotIn("/autodrive/roboracer_1/tf", channels)
        self.assertNotIn("/autodrive/roboracer_2/tf", channels)
        self.assertEqual(channels["/tf"].message_encoding, "cdr")
        self.assertEqual(channels["/autodrive/roboracer_2/ips"].message_encoding, "cdr")

    def test_vehicle_tf_transforms_use_unique_child_frame_names_under_each_vehicle(self):
        transforms = vehicle_tf_transforms(2, [1.0, 2.0, 0.0], [0.0, 0.0, 0.0, 1.0], [0.0, 0.0], 0.0)

        self.assertIn(
            ("world", "roboracer_2"),
            [(parent, child) for parent, child, _translation, _rotation in transforms],
        )
        self.assertIn(
            ("roboracer_2", "lidar_2"),
            [(parent, child) for parent, child, _translation, _rotation in transforms],
        )

    def test_tf_cdr_deserializes_with_world_parent_frame(self):
        try:
            from rosbags.typesys import Stores, get_typestore
        except ImportError:
            self.skipTest("rosbags is not installed")

        payload = {
            "V1 Position": "1 2 0",
            "V1 Orientation Quaternion": "0 0 0 1",
        }
        tf_message = [
            message
            for message in bridge_payload_to_ros2_messages(payload, 1_000_000_000)
            if message.topic == "/tf"
        ][0]

        typestore = get_typestore(Stores.ROS2_HUMBLE)
        decoded = typestore.deserialize_cdr(tf_message.data, "tf2_msgs/msg/TFMessage")

        self.assertEqual(decoded.transforms[0].header.frame_id, "world")
        self.assertEqual(decoded.transforms[0].child_frame_id, "roboracer_1")

    def test_ros2_download_filename_uses_ros2_suffix(self):
        self.assertEqual(
            ros2_mcap_download_filename("autodrive 2026-05-19 01:02:03:456.mcap"),
            "autodrive 2026-05-19 01:02:03:456_ros2.mcap",
        )

    def test_resolve_accident_log_path_rejects_paths_outside_accident_log_directory(self):
        with TemporaryDirectory() as temporary_directory:
            tower = RaceControlTower(load_settings())
            tower.accident_recorder.output_dir = Path(temporary_directory)

            with self.assertRaises(ValueError):
                tower.resolve_accident_log_path("../outside.mcap")

    def test_decision_record_uses_schema_and_decision_io_versions(self):
        with TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "autodrive 2026-05-19 01:02:03:456.mcap"
            path.write_bytes(b"")

            record = save_decision_record(
                path,
                fault_vehicle_id=1,
                penalty=None,
                penalty_vehicle_id=None,
                no_decision=False,
                decision_package_ids=["rear_end_collision"],
                decision_results={
                    "rear_end_collision": {
                        "id": "rear_end_collision",
                        "input_version": "0.1",
                        "output_version": "0.1",
                        "opinion": "Opinion",
                        "confidence": 0.5,
                        "penalty_vehicle_id": 1,
                        "metrics": {},
                    }
                },
                memo="memo",
            )

            self.assertEqual(record["schema_version"], "0.1")
            self.assertEqual(record["decision_io_version"], "0.1")
            self.assertIn("decision_results", record)
            self.assertNotIn("rct_git_revision", record)


class MonitorTelemetryTests(unittest.TestCase):
    def test_extracts_only_monitor_telemetry_fields(self):
        telemetry = extract_monitor_telemetry(
            {
                "V1 Best Lap Time": "12.34",
                "V1 Collisions": "2",
                "V1 Position": "1.5 -2.0 0.3",
                "V1 Lap Count": 4,
                "V1 Lap Time": "11.11",
                "V1 Last Lap Time": "13.37",
                "V1 Speed": "5.5",
                "V1 Linear Velocity": "0.0 2.0 0.0",
                "V1 Orientation Quaternion": "0 0 0.7071068 0.7071068",
                "V1 Throttle": "ignored",
                "V2 collision_count": 1.0,
                "/autodrive/roboracer_2/ips": {"x": 7, "y": 8},
            }
        )

        self.assertEqual(telemetry[1]["best_lap_time"], "12.34")
        self.assertEqual(telemetry[1]["collision_count"], 2)
        self.assertEqual(telemetry[1]["ips"]["x"], 1.5)
        self.assertEqual(telemetry[1]["ips"]["y"], -2.0)
        self.assertEqual(telemetry[1]["lap_count"], 4)
        self.assertEqual(telemetry[1]["lap_time"], "11.11")
        self.assertEqual(telemetry[1]["last_lap_time"], "13.37")
        self.assertEqual(telemetry[1]["speed"], 5.5)
        self.assertEqual(telemetry[1]["linear_velocity"], {"x": 0.0, "y": 2.0, "z": 0.0})
        self.assertAlmostEqual(telemetry[1]["heading_yaw"], 1.5707963267948966, places=6)
        self.assertEqual(
            telemetry[1]["orientation_quaternion"],
            {"x": 0.0, "y": 0.0, "z": 0.7071068, "w": 0.7071068},
        )
        self.assertNotIn("throttle", telemetry[1])
        self.assertEqual(telemetry[2]["collision_count"], 1)
        self.assertEqual(telemetry[2]["ips"]["x"], 7.0)
        self.assertEqual(telemetry[2]["ips"]["y"], 8.0)

    def test_extracts_monitor_telemetry_from_topic_message(self):
        telemetry = extract_monitor_telemetry(
            {
                "topic": "/autodrive/roboracer_2/ips",
                "payload": [3, 4, 0],
                "ignored": "value",
            }
        )

        self.assertEqual(telemetry[2]["ips"]["x"], 3.0)
        self.assertEqual(telemetry[2]["ips"]["y"], 4.0)

    def test_extracts_lidar_scan_points_for_traced_vehicle_only(self):
        scans = extract_lidar_scans(
            {
                "V1 LIDAR Scan": [{"x": 1, "y": 2}, {"x": 3, "y": 4}],
                "V2 LIDAR Scan": [{"x": 9, "y": 9}],
            },
            {1},
        )

        self.assertEqual(scans, {1: [{"x": 1.0, "y": 2.0}, {"x": 3.0, "y": 4.0}]})

    def test_extracts_lidar_scan_from_topic_message(self):
        scans = extract_lidar_scans(
            {
                "topic": "/autodrive/roboracer_2/lidar",
                "payload": [[1, 2], [3, 4]],
            },
            {2},
        )

        self.assertEqual(scans[2][0], {"x": 1.0, "y": 2.0})
        self.assertEqual(scans[2][1], {"x": 3.0, "y": 4.0})

    def test_extracts_lidar_points_from_text_array(self):
        scans = extract_lidar_scans(
            {"V1 LIDAR Scan": "[1.0, 2.0, 3.0, 4.0]"},
            {1},
        )

        self.assertEqual(scans[1], [{"x": 1.0, "y": 2.0}, {"x": 3.0, "y": 4.0}])

    def test_extracts_lidar_range_array_from_vehicle_origin(self):
        scans = extract_lidar_scans(
            {"V1 LIDAR Range Array": [1, 1, 1]},
            {1},
            {1: {"ips": {"x": 10, "y": 20}}},
        )

        self.assertEqual(len(scans[1]), 3)
        self.assertAlmostEqual(scans[1][1]["x"], 11.0)
        self.assertAlmostEqual(scans[1][1]["y"], 20.0)

    def test_extracts_raw_lidar_range_array_for_traced_vehicle(self):
        compressed_ranges = base64.b64encode(gzip.compress(b"1\n2\n3\n")).decode("ascii")
        arrays = extract_lidar_range_arrays(
            {
                "V1 LIDAR Range Array": compressed_ranges,
                "V2 LIDAR Range Array": [[9, 9]],
            },
            {1},
        )

        self.assertEqual(arrays, {1: [1.0, 2.0, 3.0]})


if __name__ == "__main__":
    unittest.main()
