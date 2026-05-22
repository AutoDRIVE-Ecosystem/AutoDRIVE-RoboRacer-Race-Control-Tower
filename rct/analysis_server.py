# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any
from urllib.parse import quote

from aiohttp import web

from .accident_recorder import AccidentRecorder, list_accident_logs
from .bridge import extract_monitor_telemetry
from .decision import (
    current_git_revision,
    get_decision_package,
    load_decision_record,
    render_decision_html,
    render_decision_plot_svg,
    save_decision_record,
)
from .monitor_protocol import MONITOR_PROTOCOL_VERSION, is_monitor_rest_path
from .ros2_mcap import convert_accident_mcap_to_ros2_mcap

LOGGER = logging.getLogger("rct.analysis")


def ros2_mcap_download_filename(filename: str) -> str:
    if filename.endswith(".mcap"):
        return f"{filename[:-5]}_ros2.mcap"
    return f"{filename}_ros2.mcap"


def cors_headers() -> dict[str, str]:
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET,POST,DELETE,OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Max-Age": "3600",
    }


@web.middleware
async def cors_middleware(request: web.Request, handler: web.RequestHandler) -> web.StreamResponse:
    if request.method == "OPTIONS":
        return web.Response(status=204, headers=cors_headers())
    response = await handler(request)
    response.headers.update(cors_headers())
    return response


class AnalysisServer:
    def __init__(self, accident_log_dir: Path | str = "accident_logs") -> None:
        self.accident_recorder = AccidentRecorder(accident_log_dir)

    def create_app(self) -> web.Application:
        app = web.Application(middlewares=[cors_middleware])
        app.router.add_get("/monitor/REST/{version}/accident-logs", self.handle_accident_logs_get)
        app.router.add_get("/monitor/REST/{version}/accident-logs/ros2-mcap", self.handle_accident_log_ros2_mcap_get)
        app.router.add_get("/monitor/REST/{version}/accident-logs/{filename}/summary", self.handle_accident_log_summary_get)
        app.router.add_get(
            "/monitor/REST/{version}/accident-logs/{filename}/decision-analyses/{decision_id}/html",
            self.handle_accident_log_decision_html_get,
        )
        app.router.add_get(
            "/monitor/REST/{version}/accident-logs/{filename}/decision-analyses/{decision_id}/plot.svg",
            self.handle_accident_log_decision_plot_get,
        )
        app.router.add_post(
            "/monitor/REST/{version}/accident-logs/{filename}/decision-record",
            self.handle_accident_log_decision_record_post,
        )
        app.router.add_delete("/monitor/REST/{version}/accident-logs", self.handle_accident_logs_delete)
        app.router.add_route("OPTIONS", "/{tail:.*}", self.handle_options)
        return app

    async def handle_options(self, request: web.Request) -> web.Response:
        return web.Response(status=204, headers=cors_headers())

    def validate_version(self, request: web.Request) -> web.Response | None:
        version_path = f"/monitor/REST/{request.match_info['version']}"
        if not is_monitor_rest_path(version_path):
            return web.json_response({"error": "unsupported monitor protocol version"}, status=404)
        return None

    async def handle_accident_logs_get(self, request: web.Request) -> web.Response:
        error_response = self.validate_version(request)
        if error_response is not None:
            return error_response
        return web.json_response(
            {
                "protocol": "autodrive-rct-monitor",
                "version": MONITOR_PROTOCOL_VERSION,
                "accident_logs": [record.__dict__ for record in list_accident_logs(self.accident_recorder.output_dir)],
            }
        )

    async def handle_accident_log_ros2_mcap_get(self, request: web.Request) -> web.Response:
        error_response = self.validate_version(request)
        if error_response is not None:
            return error_response

        path_param = request.query.get("path")
        if not path_param:
            return web.json_response({"error": "path is required"}, status=400)

        try:
            path = self.resolve_accident_log_path(path_param)
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400)

        if not path.is_file():
            return web.json_response({"error": "accident log not found"}, status=404)

        try:
            body = await asyncio.to_thread(convert_accident_mcap_to_ros2_mcap, path)
        except Exception:
            LOGGER.exception("failed to convert accident log to ROS2 MCAP from %s", path)
            return web.json_response({"error": "failed to convert accident log to ROS2 MCAP"}, status=500)

        filename = ros2_mcap_download_filename(path.name)
        quoted_filename = quote(filename)
        return web.Response(
            body=body,
            headers={
                "Content-Type": "application/octet-stream",
                "Content-Disposition": f"attachment; filename=\"{filename}\"; filename*=UTF-8''{quoted_filename}",
            },
        )

    async def handle_accident_log_summary_get(self, request: web.Request) -> web.Response:
        error_response = self.validate_version(request)
        if error_response is not None:
            return error_response
        try:
            path = self.accident_log_path_from_filename(request.match_info["filename"])
        except ValueError as exc:
            status = 404 if str(exc) == "accident log not found" else 400
            return web.json_response({"error": str(exc)}, status=status)

        try:
            summary = await asyncio.to_thread(self.accident_log_summary_from_mcap, path)
        except Exception:
            LOGGER.exception("failed to read accident log summary from %s", path)
            return web.json_response({"error": "failed to read accident log summary"}, status=500)

        return web.json_response(
            {
                "protocol": "autodrive-rct-monitor",
                "version": MONITOR_PROTOCOL_VERSION,
                **summary,
            }
        )

    async def handle_accident_log_decision_html_get(self, request: web.Request) -> web.Response:
        path, error_response = self.decision_request_path_and_package_response(request)
        if error_response is not None:
            return error_response
        assert path is not None
        decision_id = request.match_info["decision_id"]
        image_url = self.decision_plot_url(request, path.name, decision_id)
        try:
            summary = await asyncio.to_thread(self.accident_log_summary_from_mcap, path)
            body = await asyncio.to_thread(render_decision_html, decision_id, summary, image_url)
        except Exception:
            LOGGER.exception("failed to render decision analysis %s for %s", decision_id, path)
            return web.json_response({"error": "failed to render decision analysis"}, status=500)
        return web.Response(text=body, content_type="text/html")

    async def handle_accident_log_decision_plot_get(self, request: web.Request) -> web.Response:
        path, error_response = self.decision_request_path_and_package_response(request)
        if error_response is not None:
            return error_response
        assert path is not None
        decision_id = request.match_info["decision_id"]
        try:
            summary = await asyncio.to_thread(self.accident_log_summary_from_mcap, path)
            body = await asyncio.to_thread(render_decision_plot_svg, decision_id, summary)
        except Exception:
            LOGGER.exception("failed to render decision plot %s for %s", decision_id, path)
            return web.json_response({"error": "failed to render decision plot"}, status=500)
        return web.Response(body=body, content_type="image/svg+xml")

    async def handle_accident_log_decision_record_post(self, request: web.Request) -> web.Response:
        error_response = self.validate_version(request)
        if error_response is not None:
            return error_response
        try:
            path = self.accident_log_path_from_filename(request.match_info["filename"])
        except ValueError as exc:
            return web.json_response({"error": str(exc)}, status=400)

        try:
            body = await request.json()
        except (json.JSONDecodeError, ValueError):
            return web.json_response({"error": "request body must be JSON"}, status=400)

        package_ids = body.get("decision_package_ids", [])
        if not isinstance(package_ids, list) or not all(isinstance(item, str) and get_decision_package(item) for item in package_ids):
            return web.json_response({"error": "decision_package_ids must be known decision rule ids"}, status=400)
        memo = body.get("memo", "")
        if not isinstance(memo, str):
            return web.json_response({"error": "memo must be a string"}, status=400)
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
            try:
                delay_seconds = float(body.get("penalty_delay_seconds", 0.0))
            except (TypeError, ValueError):
                return web.json_response({"error": "penalty_delay_seconds must be a number"}, status=400)
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
                memo=memo,
                git_revision=current_git_revision(Path(__file__).resolve().parent.parent),
            )
        except Exception:
            LOGGER.exception("failed to save decision record for %s", path)
            return web.json_response({"error": "failed to save decision record"}, status=500)

        return web.json_response({"ok": True, "decision_record": record})

    async def handle_accident_logs_delete(self, request: web.Request) -> web.Response:
        error_response = self.validate_version(request)
        if error_response is not None:
            return error_response

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
        return web.json_response(
            {
                "ok": True,
                "deleted": deleted,
                "accident_logs": [record.__dict__ for record in list_accident_logs(output_dir)],
            }
        )

    def decision_plot_url(self, request: web.Request, filename: str, decision_id: str) -> str:
        base = f"{request.scheme}://{request.host}"
        return (
            f"{base}/monitor/REST/{request.match_info['version']}/accident-logs/"
            f"{quote(filename)}/decision-analyses/{quote(decision_id)}/plot.svg"
        )

    def accident_log_path_from_filename(self, filename: str) -> Path:
        if Path(filename).name != filename:
            raise ValueError("invalid accident log filename")
        path = self.accident_recorder.output_dir / filename
        if path.suffix != ".mcap":
            raise ValueError("accident log filename must point to an .mcap file")
        if not path.is_file():
            raise ValueError("accident log not found")
        return path

    def decision_request_path_and_package_response(self, request: web.Request) -> tuple[Path | None, web.Response | None]:
        error_response = self.validate_version(request)
        if error_response is not None:
            return None, error_response
        decision_id = request.match_info["decision_id"]
        if get_decision_package(decision_id) is None:
            return None, web.json_response({"error": "unknown decision rule id"}, status=404)
        try:
            path = self.accident_log_path_from_filename(request.match_info["filename"])
        except ValueError as exc:
            status = 404 if str(exc) == "accident log not found" else 400
            return None, web.json_response({"error": str(exc)}, status=status)
        return path, None

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

    def accident_log_summary_from_mcap(self, path: Path) -> dict[str, Any]:
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
            "current_rct_git_revision": current_git_revision(Path(__file__).resolve().parent.parent),
            "frames": frames,
        }


async def async_main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    host = os.getenv("RCT_ANALYSIS_HOST", os.getenv("RCT_HOST", "0.0.0.0"))
    port = int(os.getenv("RCT_ANALYSIS_PORT", "4568"))
    accident_log_dir = os.getenv("RCT_ACCIDENT_LOG_DIR", "accident_logs")
    server = AnalysisServer(accident_log_dir)
    runner = web.AppRunner(server.create_app())
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    LOGGER.info("RCT analysis server listening on %s:%s", host, port)
    try:
        await asyncio.Future()
    finally:
        await runner.cleanup()


def main() -> None:
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        LOGGER.info("RCT analysis server stopped")


if __name__ == "__main__":
    main()
