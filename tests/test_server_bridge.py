# SPDX-License-Identifier: BSD-3-Clause

import importlib.util
import asyncio
import json
import unittest
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic
from urllib.parse import quote

from rct.accident_recorder import AccidentBridgeRecord
from rct.audit_recorder import AuditLogRecord
from rct.config import Settings
from rct.decision import save_decision_record

AIOHTTP_AVAILABLE = importlib.util.find_spec("aiohttp") is not None
MCAP_AVAILABLE = importlib.util.find_spec("mcap") is not None
SOCKETIO_AVAILABLE = importlib.util.find_spec("socketio") is not None and AIOHTTP_AVAILABLE
RaceControlTower = None

if SOCKETIO_AVAILABLE:
    import socketio
if AIOHTTP_AVAILABLE:
    from aiohttp import web
    import aiohttp

    from rct.server import SOCKETIO_PATH, RaceControlTower


BRIDGE_SAMPLE_PATH = Path(__file__).with_name("bridge_sample.json")


def test_settings() -> Settings:
    return Settings(
        host="127.0.0.1",
        port=0,
        devkit_urls=("ws://127.0.0.1:4568", "ws://127.0.0.1:4569"),
        devkit_vehicle_ids=(1, 2),
        bridge_history_seconds=5.0,
        enable_presplit_bridge_cache=True,
        log_bridge_field_sizes=False,
        empty_front_camera_in_bridge_history=False,
        replace_front_camera_with_white_jpeg=False,
        reconnect_delay_seconds=0.1,
        max_message_size=16 * 1024 * 1024,
        client_queue_size=8,
        ping_interval_seconds=20,
        ping_timeout_seconds=20,
        monitor_ws_hz=0.0,
        monitor_frame_events=False,
        debug_engineio_messages=False,
        debug_engineio_max_chars=2000,
        debug_socketio_client=False,
        debug_engineio_client=False,
        debug_socketio_server=False,
        debug_engineio_server=False,
        debug_bridge_flow=False,
        log_bridge_messages=False,
        log_bridge_max_chars=20000,
        enable_origin=False,
    )


class ServerBridgeFlowTests(unittest.IsolatedAsyncioTestCase):
    def load_bridge_sample(self):
        return json.loads(BRIDGE_SAMPLE_PATH.read_text())

    @unittest.skipIf(not SOCKETIO_AVAILABLE, "python-socketio is not installed")
    def test_audit_log_ws_message_contains_only_new_entry(self):
        tower = RaceControlTower(test_settings())
        message = json.loads(
            tower.audit_log_entry_message(
                AuditLogRecord(
                    index=0,
                    timestamp_ns=1_000_000_000,
                    time="1970-01-01 09:00:01:000",
                    event_type="race_start",
                    text="Race started: simulator connected.",
                    kind="Race Start",
                )
            )
        )

        self.assertEqual(message["event"], "audit-log")
        self.assertIn("audit_entry", message)
        self.assertNotIn("audit_log", message)
        self.assertEqual(message["audit_entry"]["event_type"], "race_start")
        self.assertEqual(message["audit_entry"]["race_number"], 1)
        self.assertEqual(message["audit_entry"]["kind"], "Race Start")

    @unittest.skipIf(not SOCKETIO_AVAILABLE, "python-socketio is not installed")
    def test_accident_record_audit_time_omits_date(self):
        tower = RaceControlTower(test_settings())

        self.assertEqual(
            tower.accident_record_audit_time("2026-06-07 11:51:20:443"),
            "11:51:20:443",
        )

    @unittest.skipIf(not SOCKETIO_AVAILABLE, "python-socketio is not installed")
    async def test_emit_to_simulators_avoids_socketio_4_asyncio_wait_coroutine_bug(self):
        received = []
        received_event = asyncio.Event()
        settings = replace(test_settings(), devkit_urls=(), devkit_vehicle_ids=())
        tower = RaceControlTower(settings)
        tower_app = tower.create_app()
        tower_runner = web.AppRunner(tower_app)
        await tower_runner.setup()
        tower_site = web.TCPSite(tower_runner, "127.0.0.1", 0)
        await tower_site.start()
        tower_port = tower_runner.addresses[0][1]

        simulator = socketio.AsyncClient(reconnection=False)

        async def simulator_bridge(data):
            received.append(data)
            received_event.set()

        simulator.on("Bridge", simulator_bridge)

        try:
            await simulator.connect(
                f"http://127.0.0.1:{tower_port}",
                transports=["websocket"],
                socketio_path=SOCKETIO_PATH,
            )

            await tower.emit_to_simulators("Bridge", ({"V1 Throttle": "0.1"},))
            await asyncio.wait_for(received_event.wait(), timeout=3)
        finally:
            if getattr(simulator.eio, "state", "disconnected") == "connected":
                await simulator.disconnect()
            await tower_runner.cleanup()

        self.assertEqual(received, [{"V1 Throttle": "0.1"}])

    @unittest.skipIf(not SOCKETIO_AVAILABLE, "python-socketio is not installed")
    async def test_send_cached_incoming_bridge_replays_latest_bridge_for_devkit(self):
        tower = RaceControlTower(test_settings())
        devkit = tower.devkits[1]
        delivered = []

        async def enqueue(event, args):
            delivered.append((event, args))

        devkit.enqueue = enqueue

        await tower.bridge_history.append(
            {"V1 Position": "1 0 0", "V2 Position": "2 0 0", "V2 Throttle": "0.2"},
            now=monotonic(),
        )
        await tower.send_cached_incoming_bridge(devkit)

        self.assertEqual(
            delivered,
            [("Bridge", ({"V1 Position": "2 0 0", "V1 Throttle": "0.2"},))],
        )

    @unittest.skipIf(not SOCKETIO_AVAILABLE, "python-socketio is not installed")
    async def test_first_simulator_bridge_replays_to_devkit_that_connected_before_cache_existed(self):
        tower = RaceControlTower(test_settings())
        devkit = tower.devkits[1]
        delivered = []

        async def enqueue(event, args):
            delivered.append((event, args))

        async def publish_status():
            return None

        async def publish_simulator_telemetry(_payload, _event, source="simulator"):
            return None

        async def emit_control_cache_to_simulator():
            return None

        devkit.enqueue = enqueue
        tower.publish_status = publish_status
        tower.publish_simulator_telemetry = publish_simulator_telemetry
        tower.emit_control_cache_to_simulator = emit_control_cache_to_simulator

        devkit.connected = True
        devkit.awaiting_initial_bridge = not await tower.send_cached_incoming_bridge(devkit)
        self.assertTrue(devkit.awaiting_initial_bridge)

        await tower.handle_simulator_bridge_event(
            "simulator",
            ({"V1 Position": "1 0 0", "V2 Position": "2 0 0", "V2 Throttle": "0.2"},),
        )

        self.assertFalse(devkit.awaiting_initial_bridge)
        self.assertEqual(
            delivered,
            [("Bridge", ({"V1 Position": "2 0 0", "V1 Throttle": "0.2"},))],
        )

    @unittest.skipIf(not SOCKETIO_AVAILABLE, "python-socketio is not installed")
    async def test_socketio_4_default_namespace_connection_uses_engineio_state(self):
        tower = RaceControlTower(test_settings())
        devkit = tower.devkits[0]

        devkit.client.namespaces = []
        devkit.client.eio.state = "connected"

        self.assertTrue(devkit._client_connected())

    @unittest.skipIf(not SOCKETIO_AVAILABLE, "python-socketio is not installed")
    async def test_engineio_ping_timeout_is_used_as_server_grace_period(self):
        tower = RaceControlTower(test_settings())

        self.assertEqual(tower.sio.eio.ping_interval, 20)
        self.assertEqual(tower.sio.eio.ping_interval_grace_period, 20)
        self.assertEqual(tower.sio.eio.ping_timeout, 20)

    @unittest.skipIf(not SOCKETIO_AVAILABLE, "python-socketio is not installed")
    async def test_rejects_duplicate_active_devkit_endpoint(self):
        tower = RaceControlTower(test_settings())
        original_url = tower.devkits[1].url

        await tower.configure_devkit(tower.devkits[0], "127.0.0.1", 4568, enabled=True)

        with self.assertRaisesRegex(ValueError, "already assigned"):
            await tower.configure_devkit(tower.devkits[1], "127.0.0.1", 4568, enabled=True)

        self.assertTrue(tower.devkits[1].configured)
        self.assertEqual(tower.devkits[1].url, original_url)

    @unittest.skipIf(not SOCKETIO_AVAILABLE, "python-socketio is not installed")
    async def test_allows_duplicate_endpoint_when_previous_devkit_is_disabled(self):
        tower = RaceControlTower(test_settings())

        await tower.configure_devkit(tower.devkits[0], "127.0.0.1", 4568, enabled=False)
        await tower.configure_devkit(tower.devkits[1], "127.0.0.1", 4568, enabled=True)

        self.assertTrue(tower.devkits[1].configured)
        self.assertEqual(tower.devkits[1].url, "ws://127.0.0.1:4568")

    @unittest.skipIf(not SOCKETIO_AVAILABLE, "python-socketio is not installed")
    @unittest.skipIf(not AIOHTTP_AVAILABLE, "aiohttp is not installed")
    async def test_monitor_rest_endpoint_update_applies_new_devkit_host_and_port(self):
        new_connected = asyncio.Event()

        devkit_sio = socketio.AsyncServer(async_mode="aiohttp")
        devkit_app = web.Application()
        devkit_sio.attach(devkit_app, socketio_path=SOCKETIO_PATH)

        async def devkit_connect(sid, environ):
            new_connected.set()
            return True

        devkit_sio.on("connect", devkit_connect)

        devkit_runner = web.AppRunner(devkit_app)
        await devkit_runner.setup()
        devkit_site = web.TCPSite(devkit_runner, "127.0.0.1", 0)
        await devkit_site.start()
        devkit_port = devkit_runner.addresses[0][1]

        settings = replace(
            test_settings(),
            devkit_urls=("ws://127.0.0.1:4568",),
            devkit_vehicle_ids=(1,),
            reconnect_delay_seconds=0.01,
        )
        tower = RaceControlTower(settings)
        tower.simulator_sids.add("simulator")
        tower.state.set_simulator_clients(1)
        tower_app = tower.create_app()
        tower_runner = web.AppRunner(tower_app)
        await tower_runner.setup()
        tower_site = web.TCPSite(tower_runner, "127.0.0.1", 0)
        await tower_site.start()
        tower_port = tower_runner.addresses[0][1]

        try:
            async with aiohttp.ClientSession() as session:
                response = await session.post(
                    f"http://127.0.0.1:{tower_port}/monitor/REST/latest/devkits/1/endpoint",
                    json={
                        "host": "127.0.0.1",
                        "port": devkit_port,
                        "enabled": True,
                    },
                )
                self.assertEqual(response.status, 200)
                payload = await response.json()

            await asyncio.wait_for(new_connected.wait(), timeout=3)

            self.assertTrue(payload["ok"])
            self.assertEqual(tower.devkits[0].host, "127.0.0.1")
            self.assertEqual(tower.devkits[0].port, devkit_port)
            self.assertTrue(tower.devkits[0].configured)
            self.assertTrue(tower.devkits[0].enabled)
        finally:
            await tower.disconnect_all_devkits()
            await tower_runner.cleanup()
            await devkit_runner.cleanup()

    @unittest.skipIf(not SOCKETIO_AVAILABLE, "python-socketio is not installed")
    @unittest.skipIf(not AIOHTTP_AVAILABLE, "aiohttp is not installed")
    async def test_monitor_topics_get_returns_default_session_state(self):
        tower = RaceControlTower(test_settings())
        tower_app = tower.create_app()
        tower_runner = web.AppRunner(tower_app)
        await tower_runner.setup()
        tower_site = web.TCPSite(tower_runner, "127.0.0.1", 0)
        await tower_site.start()
        tower_port = tower_runner.addresses[0][1]

        try:
            async with aiohttp.ClientSession() as session:
                response = await session.get(
                    f"http://127.0.0.1:{tower_port}/monitor/REST/latest/topics",
                )
                self.assertEqual(response.status, 200)
                payload = await response.json()
        finally:
            await tower_runner.cleanup()

        self.assertIn("topics", payload)
        self.assertIn("topic_selections", payload)
        self.assertFalse(payload["topic_selections"]["/autodrive/roboracer_1/front_camera"])
        self.assertFalse(payload["topic_selections"]["/autodrive/roboracer_1/ips"])
        self.assertTrue(payload["topic_selections"]["/autodrive/roboracer_1/imu"])

    @unittest.skipIf(not SOCKETIO_AVAILABLE, "python-socketio is not installed")
    @unittest.skipIf(not AIOHTTP_AVAILABLE, "aiohttp is not installed")
    async def test_monitor_topics_post_updates_session_state(self):
        tower = RaceControlTower(test_settings())
        tower_app = tower.create_app()
        tower_runner = web.AppRunner(tower_app)
        await tower_runner.setup()
        tower_site = web.TCPSite(tower_runner, "127.0.0.1", 0)
        await tower_site.start()
        tower_port = tower_runner.addresses[0][1]

        try:
            async with aiohttp.ClientSession() as session:
                response = await session.post(
                    f"http://127.0.0.1:{tower_port}/monitor/REST/latest/topics",
                    json={
                        "topic_selections": {
                            "/autodrive/roboracer_1/front_camera": True,
                            "/autodrive/roboracer_1/ips": True,
                        }
                    },
                )
                self.assertEqual(response.status, 200)
                payload = await response.json()

                follow_up = await session.get(
                    f"http://127.0.0.1:{tower_port}/monitor/REST/latest/topics",
                )
                self.assertEqual(follow_up.status, 200)
                follow_up_payload = await follow_up.json()
        finally:
            await tower_runner.cleanup()

        self.assertTrue(payload["ok"])
        self.assertTrue(payload["topic_selections"]["/autodrive/roboracer_1/front_camera"])
        self.assertTrue(payload["topic_selections"]["/autodrive/roboracer_1/ips"])
        self.assertTrue(follow_up_payload["topic_selections"]["/autodrive/roboracer_1/front_camera"])
        self.assertTrue(follow_up_payload["topic_selections"]["/autodrive/roboracer_1/ips"])

    @unittest.skipIf(not SOCKETIO_AVAILABLE, "python-socketio is not installed")
    @unittest.skipIf(not AIOHTTP_AVAILABLE, "aiohttp is not installed")
    async def test_monitor_accident_recorder_post_updates_session_state(self):
        tower = RaceControlTower(test_settings())
        tower_app = tower.create_app()
        tower_runner = web.AppRunner(tower_app)
        await tower_runner.setup()
        tower_site = web.TCPSite(tower_runner, "127.0.0.1", 0)
        await tower_site.start()
        tower_port = tower_runner.addresses[0][1]

        try:
            async with aiohttp.ClientSession() as session:
                response = await session.post(
                    f"http://127.0.0.1:{tower_port}/monitor/REST/latest/accident-recorder",
                    json={"pre_accident_seconds": 3.5, "include_camera": True},
                )
                self.assertEqual(response.status, 200)
                payload = await response.json()

                follow_up = await session.get(
                    f"http://127.0.0.1:{tower_port}/monitor/REST/latest/accident-recorder",
                )
                self.assertEqual(follow_up.status, 200)
                follow_up_payload = await follow_up.json()
        finally:
            await tower_runner.cleanup()

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["accident_recorder"]["pre_accident_seconds"], 3.5)
        self.assertTrue(payload["accident_recorder"]["include_camera"])
        self.assertEqual(follow_up_payload["accident_recorder"]["pre_accident_seconds"], 3.5)
        self.assertTrue(follow_up_payload["accident_recorder"]["include_camera"])

    @unittest.skipIf(not SOCKETIO_AVAILABLE, "python-socketio is not installed")
    @unittest.skipIf(not AIOHTTP_AVAILABLE, "aiohttp is not installed")
    async def test_monitor_accident_logs_get_returns_files_from_recorder_directory(self):
        tower = RaceControlTower(test_settings())
        with TemporaryDirectory() as temporary_directory:
            tower.accident_recorder.output_dir = Path(temporary_directory)
            accident_log = tower.accident_recorder.output_dir / "autodrive 2026-05-19 01:02:03:456.mcap"
            accident_log.write_bytes(b"mcap")
            tower_app = tower.create_app()
            tower_runner = web.AppRunner(tower_app)
            await tower_runner.setup()
            tower_site = web.TCPSite(tower_runner, "127.0.0.1", 0)
            await tower_site.start()
            tower_port = tower_runner.addresses[0][1]

            try:
                async with aiohttp.ClientSession() as session:
                    response = await session.get(
                        f"http://127.0.0.1:{tower_port}/monitor/REST/latest/accident-logs?ts=123",
                    )
                    self.assertEqual(response.status, 200)
                    payload = await response.json()
            finally:
                await tower_runner.cleanup()

        self.assertEqual(len(payload["accident_logs"]), 1)
        self.assertEqual(payload["accident_logs"][0]["filename"], "autodrive 2026-05-19 01:02:03:456.mcap")
        self.assertEqual(payload["accident_logs"][0]["time"], "2026-05-19 01:02:03:456")

    @unittest.skipIf(not SOCKETIO_AVAILABLE, "python-socketio is not installed")
    @unittest.skipIf(not AIOHTTP_AVAILABLE, "aiohttp is not installed")
    async def test_monitor_accident_logs_get_returns_decision_record_from_matching_json(self):
        tower = RaceControlTower(test_settings())
        with TemporaryDirectory() as temporary_directory:
            tower.accident_recorder.output_dir = Path(temporary_directory)
            accident_log = tower.accident_recorder.output_dir / "autodrive 2026-05-19 01:02:03:456.mcap"
            accident_log.write_bytes(b"mcap")
            save_decision_record(accident_log, fault_vehicle_id=2, penalty_vehicle_id=2)
            tower_app = tower.create_app()
            tower_runner = web.AppRunner(tower_app)
            await tower_runner.setup()
            tower_site = web.TCPSite(tower_runner, "127.0.0.1", 0)
            await tower_site.start()
            tower_port = tower_runner.addresses[0][1]

            try:
                async with aiohttp.ClientSession() as session:
                    response = await session.get(
                        f"http://127.0.0.1:{tower_port}/monitor/REST/latest/accident-logs?ts=123",
                    )
                    self.assertEqual(response.status, 200)
                    payload = await response.json()
            finally:
                await tower_runner.cleanup()

        self.assertEqual(len(payload["accident_logs"]), 1)
        decision_record = payload["accident_logs"][0]["decision_record"]
        self.assertEqual(decision_record["fault_vehicle_id"], 2)
        self.assertEqual(decision_record["penalty_vehicle_id"], 2)

    @unittest.skipIf(not SOCKETIO_AVAILABLE, "python-socketio is not installed")
    @unittest.skipIf(not AIOHTTP_AVAILABLE, "aiohttp is not installed")
    @unittest.skipIf(not MCAP_AVAILABLE, "mcap is not installed")
    async def test_monitor_accident_log_summary_returns_replay_frames(self):
        tower = RaceControlTower(test_settings())
        with TemporaryDirectory() as temporary_directory:
            tower.accident_recorder.output_dir = Path(temporary_directory)
            accident_log = tower.accident_recorder.write_mcap(
                [
                    AccidentBridgeRecord(
                        monotonic_timestamp=10.0,
                        wall_time_ns=1_000_000_000,
                        event="simulator/Bridge",
                        payload={"V1 Position": "1 2 0", "V2 Position": "3 4 0"},
                    ),
                    AccidentBridgeRecord(
                        monotonic_timestamp=11.0,
                        wall_time_ns=2_000_000_000,
                        event="simulator/Bridge",
                        payload={"V1 Position": "2 3 0", "V2 Position": "4 5 0"},
                    ),
                ],
                trigger_vehicle_id=1,
                collision_count=1,
                created_at=datetime(2026, 5, 19, 1, 2, 3, 456000),
            )
            tower_app = tower.create_app()
            tower_runner = web.AppRunner(tower_app)
            await tower_runner.setup()
            tower_site = web.TCPSite(tower_runner, "127.0.0.1", 0)
            await tower_site.start()
            tower_port = tower_runner.addresses[0][1]

            try:
                async with aiohttp.ClientSession() as session:
                    quoted_filename = quote(accident_log.filename)
                    response = await session.get(
                        f"http://127.0.0.1:{tower_port}/monitor/REST/latest/accident-logs/{quoted_filename}/summary?ts=123",
                        headers={"Accept-Encoding": "gzip"},
                    )
                    self.assertEqual(response.status, 200)
                    self.assertEqual(response.headers.get("Content-Encoding"), "gzip")
                    payload = await response.json()
            finally:
                await tower_runner.cleanup()

        self.assertEqual(payload["filename"], accident_log.filename)
        self.assertEqual(payload["duration_seconds"], 1.0)
        self.assertEqual(len(payload["frames"]), 2)
        self.assertEqual(payload["frames"][0]["vehicles"]["1"]["ips"]["x"], 1.0)
        self.assertEqual(payload["frames"][1]["vehicles"]["2"]["ips"]["y"], 5.0)
        self.assertEqual(payload["frames"][1]["time_to_accident_seconds"], 0.0)

    @unittest.skipIf(not SOCKETIO_AVAILABLE, "python-socketio is not installed")
    @unittest.skipIf(not AIOHTTP_AVAILABLE, "aiohttp is not installed")
    async def test_monitor_accident_logs_delete_clears_files_from_recorder_directory(self):
        tower = RaceControlTower(test_settings())
        with TemporaryDirectory() as temporary_directory:
            tower.accident_recorder.output_dir = Path(temporary_directory)
            first_log = tower.accident_recorder.output_dir / "autodrive 2026-05-19 01:02:03:456.mcap"
            second_log = tower.accident_recorder.output_dir / "autodrive 2026-05-19 01:02:04:000.mcap"
            first_log.write_bytes(b"mcap")
            second_log.write_bytes(b"mcap")
            tower_app = tower.create_app()
            tower_runner = web.AppRunner(tower_app)
            await tower_runner.setup()
            tower_site = web.TCPSite(tower_runner, "127.0.0.1", 0)
            await tower_site.start()
            tower_port = tower_runner.addresses[0][1]

            try:
                async with aiohttp.ClientSession() as session:
                    response = await session.delete(
                        f"http://127.0.0.1:{tower_port}/monitor/REST/latest/accident-logs?ts=123",
                    )
                    self.assertEqual(response.status, 200)
                    payload = await response.json()
            finally:
                await tower_runner.cleanup()

            self.assertFalse(first_log.exists())
            self.assertFalse(second_log.exists())

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["deleted"], 2)
        self.assertEqual(payload["accident_logs"], [])

    @unittest.skipIf(not SOCKETIO_AVAILABLE, "python-socketio is not installed")
    @unittest.skipIf(not AIOHTTP_AVAILABLE, "aiohttp is not installed")
    @unittest.skipIf(not MCAP_AVAILABLE, "mcap is not installed")
    async def test_monitor_audit_log_get_returns_files_from_recorder_directory(self):
        tower = RaceControlTower(test_settings())
        with TemporaryDirectory() as temporary_directory:
            tower.accident_recorder.output_dir = Path(temporary_directory)
            tower.audit_recorder.output_dir = Path(temporary_directory)
            tower.audit_recorder.append(
                event_type="race_start",
                text="Race started: simulator connected.",
                timestamp_ns=1_000_000_000,
            )
            tower_app = tower.create_app()
            tower_runner = web.AppRunner(tower_app)
            await tower_runner.setup()
            tower_site = web.TCPSite(tower_runner, "127.0.0.1", 0)
            await tower_site.start()
            tower_port = tower_runner.addresses[0][1]

            try:
                async with aiohttp.ClientSession() as session:
                    response = await session.get(
                        f"http://127.0.0.1:{tower_port}/monitor/REST/latest/audit-log?ts=123",
                    )
                    self.assertEqual(response.status, 200)
                    payload = await response.json()
            finally:
                await tower_runner.cleanup()

        self.assertEqual(len(payload["audit_log"]), 1)
        self.assertEqual(payload["audit_log"][0]["event_type"], "race_start")
        self.assertEqual(payload["audit_log"][0]["text"], "Race started: simulator connected.")

    @unittest.skipIf(not SOCKETIO_AVAILABLE, "python-socketio is not installed")
    async def test_presplit_bridge_payload_filters_disabled_topics_and_keeps_enabled_inputs(self):
        tower = RaceControlTower(test_settings())
        payload = self.load_bridge_sample()

        rewritten_payload = tower.prebuilt_devkit_bridge_payload(payload, 2)

        self.assertEqual(rewritten_payload["V1 Throttle"], payload["V2 Throttle"])
        self.assertEqual(rewritten_payload["V1 Steering"], payload["V2 Steering"])
        self.assertEqual(rewritten_payload["V1 LIDAR Range Array"], payload["V2 LIDAR Range Array"])
        self.assertNotEqual(rewritten_payload["V1 Front Camera Image"], payload["V2 Front Camera Image"])
        self.assertEqual(rewritten_payload["V1 Position"], "0.0 0.0 0.0")
        self.assertEqual(rewritten_payload["V1 Lap Count"], "0")
        self.assertEqual(rewritten_payload["V1 Last Lap Time"], "0.0")
        self.assertEqual(rewritten_payload["V1 Best Lap Time"], "0.0")
        self.assertEqual(rewritten_payload["V1 Collisions"], "0")

    @unittest.skipIf(not SOCKETIO_AVAILABLE, "python-socketio is not installed")
    async def test_presplit_bridge_payload_uses_white_front_camera_when_topic_disabled(self):
        tower = RaceControlTower(test_settings())
        payload = self.load_bridge_sample()
        tower.latest_front_camera_fields = {"V2 Front Camera Image": payload["V2 Front Camera Image"]}

        rewritten_payload = tower.prebuilt_devkit_bridge_payload(payload, 2)

        self.assertNotEqual(rewritten_payload["V1 Front Camera Image"], payload["V2 Front Camera Image"])

    @unittest.skipIf(not SOCKETIO_AVAILABLE, "python-socketio is not installed")
    async def test_presplit_bridge_payload_restores_original_front_camera_when_topic_enabled(self):
        tower = RaceControlTower(test_settings())
        payload = self.load_bridge_sample()
        tower.state.update_topic_selections({"/autodrive/roboracer_1/front_camera": True})
        tower.latest_front_camera_fields = {"V2 Front Camera Image": payload["V2 Front Camera Image"]}

        rewritten_payload = tower.prebuilt_devkit_bridge_payload(payload, 2)

        self.assertEqual(rewritten_payload["V1 Front Camera Image"], payload["V2 Front Camera Image"])

    @unittest.skipIf(not SOCKETIO_AVAILABLE, "python-socketio is not installed")
    async def test_presplit_bridge_payload_drops_lidar_when_topic_disabled(self):
        tower = RaceControlTower(test_settings())
        payload = self.load_bridge_sample()
        tower.state.update_topic_selections({"/autodrive/roboracer_1/lidar": False})

        rewritten_payload = tower.prebuilt_devkit_bridge_payload(payload, 2)

        self.assertEqual(rewritten_payload["V1 LIDAR Scan Rate"], "40.0")
        self.assertTrue(isinstance(rewritten_payload["V1 LIDAR Range Array"], str))
        self.assertTrue(isinstance(rewritten_payload["V1 LIDAR Intensity Array"], str))

    @unittest.skipIf(not SOCKETIO_AVAILABLE, "python-socketio is not installed")
    async def test_bridge_rate_refresh_clears_stale_rates(self):
        tower = RaceControlTower(test_settings())
        devkit = tower.devkits[0]
        devkit.connected = True
        tower.state.set_devkit_connected(devkit.name, True)

        tower.bridge_rates.record(devkit.vehicle_id, now=100.0)
        tower.state.set_devkit_bridge_rate(devkit.name, 1.0, 60)
        tower.refresh_bridge_rates(now=101.1)

        snapshot = tower.state.snapshot()["devkits"][0]
        self.assertEqual(snapshot["bridge_hz"], 0.0)
        self.assertEqual(snapshot["bridge_per_minute"], 0)

    @unittest.skipIf(not SOCKETIO_AVAILABLE, "python-socketio is not installed")
    async def test_simulator_bridge_immediately_echoes_latest_control_cache(self):
        tower = RaceControlTower(test_settings())
        emitted_to_simulator = []

        async def emit_to_simulators(event, args):
            emitted_to_simulator.append((event, args))

        async def broadcast_monitor(_message):
            return None

        tower.emit_to_simulators = emit_to_simulators
        tower.broadcast_monitor = broadcast_monitor
        await tower.control_cache.merge(
            {"V1 Throttle": "0.1", "V2 Steering": "0.2"},
            10.0,
            include_origin=False,
        )

        await tower.handle_simulator_bridge_event(
            "simulator",
            ({"V1 Position": "1 0 0", "V2 Position": "2 0 0"},),
        )

        self.assertEqual(len(emitted_to_simulator), 1)
        self.assertEqual(emitted_to_simulator[0][0], "Bridge")
        self.assertEqual(emitted_to_simulator[0][1][0]["V1 Throttle"], "0.1")
        self.assertEqual(emitted_to_simulator[0][1][0]["V2 Steering"], "0.2")
        self.assertNotIn("origin", emitted_to_simulator[0][1][0])
        latest = await tower.bridge_history.latest(now=10.0)
        self.assertIsNotNone(latest)
        self.assertEqual(latest.payload["V1 Position"], "1 0 0")

    @unittest.skipIf(not SOCKETIO_AVAILABLE, "python-socketio is not installed")
    async def test_devkit_control_updates_control_cache_and_sends_next_newer_bridge(self):
        tower = RaceControlTower(test_settings())
        devkit = tower.devkits[0]
        delivered_to_devkit = []

        async def enqueue(event, args):
            delivered_to_devkit.append((event, args))

        async def broadcast_monitor(_message):
            return None

        devkit.enqueue = enqueue
        tower.broadcast_monitor = broadcast_monitor

        await tower.bridge_history.append({"V1 Position": "old"})
        received_at = monotonic()
        await tower.bridge_history.append({"V1 Position": "next"}, now=received_at + 0.001)
        await tower.process_devkit_bridge_control(devkit, received_at, ({"V1 Throttle": "0.1"},))

        _timestamp, control_payload = await tower.control_cache.snapshot()
        self.assertEqual(control_payload["V1 Throttle"], "0.1")
        self.assertEqual(delivered_to_devkit, [("Bridge", ({"V1 Position": "next"},))])

    @unittest.skipIf(not SOCKETIO_AVAILABLE, "python-socketio is not installed")
    async def test_filtered_devkit_control_sends_zero_throttle_and_steering(self):
        tower = RaceControlTower(test_settings())
        devkit = tower.devkits[0]

        async def enqueue(_event, _args):
            return None

        async def broadcast_monitor(_message):
            return None

        devkit.enqueue = enqueue
        tower.broadcast_monitor = broadcast_monitor
        tower.filtered_control_vehicle_ids = {1}

        received_at = monotonic()
        await tower.bridge_history.append({"V1 Position": "next"}, now=received_at + 0.001)
        await tower.process_devkit_bridge_control(
            devkit,
            received_at,
            ({"V1 Throttle": "0.8", "V1 Steering": "-0.2"},),
        )

        _timestamp, control_payload = await tower.control_cache.snapshot()
        self.assertEqual(control_payload["V1 Throttle"], "0.0")
        self.assertEqual(control_payload["V1 Steering"], "0.0")

    @unittest.skipIf(not SOCKETIO_AVAILABLE, "python-socketio is not installed")
    async def test_manual_penalty_decision_releases_victim_and_keeps_penalty_filtered(self):
        tower = RaceControlTower(test_settings())

        async def broadcast_monitor(_message):
            return None

        tower.broadcast_monitor = broadcast_monitor
        await tower.start_manual_penalty_decision([(1, 1), (2, 1)])

        await tower.apply_manual_penalty_decision(2)

        try:
            self.assertEqual(tower.filtered_control_vehicle_ids, {2})
            decision = tower.state.penalty_decision()
            self.assertTrue(decision["active"])
            self.assertEqual(decision["penalty_vehicle_id"], 2)
            self.assertEqual(decision["victim_vehicle_id"], 1)
            self.assertEqual(decision["filtered_vehicle_ids"], [2])
            self.assertEqual(tower.state.vehicle_penalties(), {"2": 1})
        finally:
            for task in tower._penalty_release_tasks.values():
                task.cancel()

    @unittest.skipIf(not SOCKETIO_AVAILABLE, "python-socketio is not installed")
    async def test_manual_no_decision_releases_both_vehicles_without_penalty(self):
        tower = RaceControlTower(test_settings())

        async def broadcast_monitor(_message):
            return None

        tower.broadcast_monitor = broadcast_monitor
        await tower.start_manual_penalty_decision([(1, 1), (2, 1)])

        await tower.apply_manual_no_decision()

        self.assertEqual(tower.filtered_control_vehicle_ids, set())
        self.assertEqual(tower.state.vehicle_penalties(), {})
        decision = tower.state.penalty_decision()
        self.assertFalse(decision["active"])
        self.assertEqual(decision["filtered_vehicle_ids"], [])
        self.assertEqual(decision["collision_vehicle_ids"], [1, 2])

    @unittest.skipIf(not SOCKETIO_AVAILABLE, "python-socketio is not installed")
    async def test_manual_penalty_decision_with_zero_restart_delay_releases_immediately(self):
        tower = RaceControlTower(test_settings())
        monitor_events = []

        async def broadcast_monitor(message):
            monitor_events.append(message)

        tower.broadcast_monitor = broadcast_monitor
        tower.state.set_penalty_rule_settings(restart_delay_seconds=0.0)
        await tower.start_manual_penalty_decision([(1, 1), (2, 1)])

        await tower.apply_manual_penalty_decision(2)

        self.assertEqual(tower.filtered_control_vehicle_ids, set())
        self.assertEqual(tower.state.vehicle_penalties(), {"2": 1})
        self.assertEqual(tower._penalty_release_tasks, {})
        decision = tower.state.penalty_decision()
        self.assertFalse(decision["active"])
        self.assertEqual(decision["filtered_vehicle_ids"], [])
        penalty_decision_event = json.loads(monitor_events[-1])
        self.assertFalse(penalty_decision_event["active"])
        self.assertEqual(penalty_decision_event["filtered_vehicle_ids"], [])

    @unittest.skipIf(not SOCKETIO_AVAILABLE, "python-socketio is not installed")
    async def test_new_simulator_session_resets_pending_penalty_decision(self):
        tower = RaceControlTower(test_settings())
        await tower.start_manual_penalty_decision([(1, 1), (2, 1)])
        tower.collision_counts = {1: 3, 2: 2}
        tower.state.increment_vehicle_penalty(2)

        reset = tower.reset_penalty_decision_for_simulator_session()

        self.assertTrue(reset)
        self.assertEqual(tower.collision_counts, {})
        self.assertEqual(tower.state.vehicle_penalties(), {})
        self.assertEqual(tower.filtered_control_vehicle_ids, set())
        self.assertEqual(tower._penalty_release_tasks, {})
        decision = tower.state.penalty_decision()
        self.assertFalse(decision["active"])
        self.assertEqual(decision["collision_vehicle_ids"], [])
        self.assertEqual(decision["filtered_vehicle_ids"], [])

    @unittest.skipIf(not SOCKETIO_AVAILABLE, "python-socketio is not installed")
    async def test_total_lap_count_finishes_race_and_filters_both_vehicles(self):
        tower = RaceControlTower(test_settings())

        async def broadcast_monitor(_message):
            return None

        emitted_to_simulator = []

        async def emit_to_simulators(event, args):
            emitted_to_simulator.append((event, args))

        tower.broadcast_monitor = broadcast_monitor
        tower.emit_to_simulators = emit_to_simulators
        tower.state.set_racing_rule_settings(
            total_lap_count=2,
            maximum_penalty_count=0,
            celebration_with_confetti=False,
        )
        await tower.control_cache.merge(
            {"V1 Throttle": "0.7", "V1 Steering": "0.2", "V2 Throttle": "0.6"},
            monotonic(),
        )

        await tower.publish_simulator_telemetry({"V1 Lap Count": "2"}, "Bridge")

        race_result = tower.state.race_result()
        self.assertTrue(race_result["active"])
        self.assertEqual(race_result["winner_vehicle_id"], 1)
        self.assertEqual(race_result["loser_vehicle_id"], 2)
        self.assertEqual(race_result["reason"], "total_lap_count")
        _event, args = emitted_to_simulator[-1]
        self.assertEqual(args[0]["V1 Throttle"], "0.0")
        self.assertEqual(args[0]["V1 Steering"], "0.0")
        self.assertEqual(args[0]["V2 Throttle"], "0.0")
        self.assertEqual(args[0]["V2 Steering"], "0.0")

    @unittest.skipIf(not SOCKETIO_AVAILABLE, "python-socketio is not installed")
    async def test_maximum_penalty_count_finishes_race(self):
        tower = RaceControlTower(test_settings())

        async def broadcast_monitor(_message):
            return None

        async def emit_to_simulators(_event, _args):
            return None

        tower.broadcast_monitor = broadcast_monitor
        tower.emit_to_simulators = emit_to_simulators
        tower.state.set_racing_rule_settings(
            total_lap_count=10,
            maximum_penalty_count=1,
            celebration_with_confetti=False,
        )
        await tower.start_manual_penalty_decision([(1, 1), (2, 1)])

        await tower.apply_manual_penalty_decision(2)

        race_result = tower.state.race_result()
        self.assertTrue(race_result["active"])
        self.assertEqual(race_result["winner_vehicle_id"], 1)
        self.assertEqual(race_result["loser_vehicle_id"], 2)
        self.assertEqual(race_result["reason"], "maximum_penalty_count")

    @unittest.skipIf(not SOCKETIO_AVAILABLE, "python-socketio is not installed")
    async def test_devkit_bridge_outgoing_origin_is_opt_in(self):
        tower = RaceControlTower(replace(test_settings(), enable_origin=True))
        delivered_to_devkit = []

        async def enqueue(_event, _args):
            delivered_to_devkit.append(True)

        async def broadcast_monitor(_message):
            return None

        tower.broadcast_monitor = broadcast_monitor

        devkit = tower.devkits[0]
        devkit.enqueue = enqueue
        received_at = monotonic()
        await tower.bridge_history.append({"V1 Position": "next"}, now=received_at + 0.001)
        await tower.process_devkit_bridge_control(devkit, received_at, ({"V1 Throttle": "0.1"},))

        _timestamp, control_payload = await tower.control_cache.snapshot(include_origin=True)
        self.assertEqual(control_payload["origin"], 1)
        self.assertEqual(delivered_to_devkit, [True])

    @unittest.skipIf(not SOCKETIO_AVAILABLE, "python-socketio is not installed")
    async def test_cached_telemetry_message_contains_latest_vehicle_values(self):
        tower = RaceControlTower(test_settings())

        await tower.publish_simulator_telemetry(
            {"V1 Position": "1 2 0", "V2 Position": "3 4 0"},
            "Bridge",
        )
        await tower.publish_simulator_telemetry(
            {"V1 Speed": "5.5"},
            "Bridge",
        )

        message = tower.cached_telemetry_message()
        self.assertIsNotNone(message)
        self.assertIn('"1"', message)
        self.assertIn('"ips"', message)
        self.assertIn('"speed":5.5', message)
        self.assertIn('"2"', message)

    @unittest.skipIf(not SOCKETIO_AVAILABLE, "python-socketio is not installed")
    async def test_monitor_frame_events_are_disabled_by_default(self):
        tower = RaceControlTower(test_settings())
        monitor_events = []

        async def broadcast_monitor(message):
            monitor_events.append(json.loads(message))

        tower.broadcast_monitor = broadcast_monitor
        await tower.publish_monitor_frame(
            source="devkit:1",
            vehicle_id=1,
            target="simulator",
            socketio_event="Bridge",
            args=({"V1 Throttle": "0.1"},),
        )

        self.assertEqual(monitor_events, [])

    @unittest.skipIf(not SOCKETIO_AVAILABLE, "python-socketio is not installed")
    async def test_monitor_frame_events_can_be_enabled(self):
        tower = RaceControlTower(replace(test_settings(), monitor_frame_events=True))
        monitor_events = []

        async def broadcast_monitor(message):
            monitor_events.append(json.loads(message))

        tower.broadcast_monitor = broadcast_monitor
        await tower.publish_monitor_frame(
            source="devkit:1",
            vehicle_id=1,
            target="simulator",
            socketio_event="Bridge",
            args=({"V1 Throttle": "0.1"},),
        )

        self.assertEqual(monitor_events[0]["event"], "frame")
        self.assertEqual(monitor_events[0]["vehicle_id"], 1)

    @unittest.skipIf(not SOCKETIO_AVAILABLE, "python-socketio is not installed")
    async def test_lightweight_status_omits_static_settings_and_race_time(self):
        tower = RaceControlTower(test_settings())

        lightweight = tower.status_payload()
        full = tower.status_payload(full=True)

        self.assertNotIn("penalty_rule", lightweight)
        self.assertNotIn("racing_rule", lightweight)
        self.assertNotIn("accident_recorder", lightweight)
        self.assertNotIn("race_time_seconds", lightweight)
        self.assertNotIn("race_time_seconds", full)
        self.assertIn("penalty_rule", full)
        self.assertIn("racing_rule", full)
        self.assertIn("accident_recorder", full)

    @unittest.skipIf(not SOCKETIO_AVAILABLE, "python-socketio is not installed")
    async def test_event_before_connect_implicitly_connects_socketio_4_namespace(self):
        tower = RaceControlTower(test_settings())
        eio_sid = "simulator-eio-sid"

        async def send_packet(_sid, _packet):
            return None

        async def broadcast_monitor(_message):
            return None

        tower.sio._send_packet = send_packet
        tower.broadcast_monitor = broadcast_monitor
        tower.connect_all_devkits = lambda: None
        tower.sio.environ[eio_sid] = {}

        await tower._ensure_socketio_namespace_for_event(
            eio_sid,
            '2["Bridge",{"V1 Throttle":"0.1"}]',
        )

        self.assertTrue(tower.sio.manager.is_connected(eio_sid, "/"))
        self.assertIn(eio_sid, tower.simulator_sids)


if __name__ == "__main__":
    unittest.main()
