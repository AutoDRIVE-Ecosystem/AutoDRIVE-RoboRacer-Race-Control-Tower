# SPDX-License-Identifier: BSD-3-Clause

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from aiohttp import web

from rct.develop_reference import MONITOR_REST_REFERENCE, install_monitor_rest_route_collector
from rct.page_templates import build_page_template_response
from rct.monitor_protocol_docs import render_monitor_protocol_docs


class PageTemplateResponseTests(unittest.TestCase):
    def test_renders_root_page_template(self):
        with TemporaryDirectory() as temp_dir:
            frontend_root = Path(temp_dir)
            templates = frontend_root / "templates"
            templates.mkdir()
            (templates / "base.html").write_text(
                "<title>[[ page_title ]]</title>{% block content %}{% endblock %}",
                encoding="utf-8",
            )
            (templates / "index.html").write_text(
                '{% extends "base.html" %}{% block content %}'
                '<main data-page="[[ active_page ]]"></main>'
                "{% endblock %}",
                encoding="utf-8",
            )

            response = build_page_template_response("/", frontend_root)

            self.assertIsNotNone(response)
            self.assertEqual(response.status_code, 200)
            self.assertIn(("Content-Type", "text/html; charset=utf-8"), response.headers)
            self.assertIn(b"<title>AutoDRIVE Race Control Tower</title>", response.body)
            self.assertIn(b'<main data-page="race-control"></main>', response.body)

    def test_renders_develop_page_template(self):
        with TemporaryDirectory() as temp_dir:
            frontend_root = Path(temp_dir)
            templates = frontend_root / "templates"
            templates.mkdir()
            (templates / "base.html").write_text(
                "<title>[[ page_title ]]</title>{% block content %}{% endblock %}",
                encoding="utf-8",
            )
            (templates / "develop.html").write_text(
                '{% extends "base.html" %}{% block content %}'
                '<main data-page="[[ active_page ]]"></main>'
                "{% endblock %}",
                encoding="utf-8",
            )

            response = build_page_template_response("/develop", frontend_root)

            self.assertIsNotNone(response)
            self.assertEqual(response.status_code, 200)
            self.assertIn(b"<title>Develop - AutoDRIVE Race Control Tower</title>", response.body)
            self.assertIn(b'<main data-page="develop"></main>', response.body)

    def test_renders_versioned_develop_page_template(self):
        with TemporaryDirectory() as temp_dir:
            frontend_root = Path(temp_dir)
            templates = frontend_root / "templates"
            templates.mkdir()
            (templates / "base.html").write_text(
                "<title>[[ page_title ]]</title>{% block content %}{% endblock %}",
                encoding="utf-8",
            )
            (templates / "develop.html").write_text(
                '{% extends "base.html" %}{% block content %}'
                '<main data-version="[[ monitor_protocol_docs.version ]]"></main>'
                "{% endblock %}",
                encoding="utf-8",
            )

            latest_response = build_page_template_response("/develop/latest", frontend_root)
            versioned_response = build_page_template_response("/develop/0.1", frontend_root)

            self.assertIsNotNone(latest_response)
            self.assertIsNotNone(versioned_response)
            self.assertIn(b"<title>Develop latest - AutoDRIVE Race Control Tower</title>", latest_response.body)
            self.assertIn(b'<main data-version="latest"></main>', latest_response.body)
            self.assertIn(b"<title>Develop 0.1 - AutoDRIVE Race Control Tower</title>", versioned_response.body)
            self.assertIn(b'<main data-version="0.1"></main>', versioned_response.body)

    def test_develop_template_uses_root_relative_static_asset_paths(self):
        response = build_page_template_response("/develop/latest", Path("frontend"))

        self.assertIsNotNone(response)
        html = response.body.decode("utf-8")
        self.assertIn('href="/vendor/bootstrap/bootstrap-5.3.8.min.css"', html)
        self.assertIn('src="/vendor/jquery/jquery-4.0.0.min.js"', html)
        self.assertIn('href="/vendor/bootstrap-icons/bootstrap-icons-1.13.1.min.css"', html)
        self.assertIn('src="/assets/autodrive-extended-logo-3.png"', html)
        self.assertIn('src="/vendor/bootstrap/bootstrap-5.3.8.bundle.min.js"', html)
        self.assertNotIn("/develop/vendor/", html)
        self.assertNotIn("/develop/assets/", html)

    def test_ignores_static_asset_paths(self):
        with TemporaryDirectory() as temp_dir:
            response = build_page_template_response("/assets/favicon.png", Path(temp_dir))

            self.assertIsNone(response)

    def test_preserves_existing_javascript_template_literals(self):
        with TemporaryDirectory() as temp_dir:
            frontend_root = Path(temp_dir)
            templates = frontend_root / "templates"
            templates.mkdir()
            (templates / "base.html").write_text(
                "{% block scripts %}{% endblock %}",
                encoding="utf-8",
            )
            (templates / "index.html").write_text(
                '{% extends "base.html" %}{% block scripts %}'
                '<script>const label = `${number}${{ 1: "st" }[number] || "th"}`;</script>'
                "{% endblock %}",
                encoding="utf-8",
            )

            response = build_page_template_response("/", frontend_root)

            self.assertIsNotNone(response)
            self.assertIn(b'${{ 1: "st" }[number] || "th"}', response.body)

    def test_monitor_protocol_docs_are_split_into_reference_sections(self):
        with TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            docs = repo_root / "docs"
            docs.mkdir()
            (docs / "monitor-protocol.md").write_text(
                "# AutoDRIVE RCT Monitor Protocol\n\n"
                "Intro text.\n\n"
                "## Path Layout\n\n"
                "Overview body.\n\n"
                "## REST API\n\n"
                "### GET `/monitor/REST/{version}`\n\n"
                "REST body.\n\n"
                "### GET `/monitor/REST/{version}/topics`\n\n"
                "Topics GET body.\n\n"
                "### POST `/monitor/REST/{version}/topics`\n\n"
                "Topics POST body.\n\n"
                "## WebSocket API\n\n"
                "### Server Event: `status`\n\n"
                "WS body.\n\n"
                "## WebSocket Client Commands\n\n"
                "### Command: `configure-devkits`\n\n"
                "Command body.\n",
                encoding="utf-8",
            )

            rendered = render_monitor_protocol_docs(repo_root, version="0.1")

            self.assertIn("Intro text.", rendered.overview_html)
            self.assertIn('id="path-layout"', rendered.overview_html)
            self.assertIn("REST body.", rendered.rest_html)
            self.assertIn('id="monitor-rest-0-1"', rendered.rest_html)
            self.assertIn('id="monitor-rest-0-1-topics"', rendered.rest_html)
            self.assertIn("<h4", rendered.rest_html)
            self.assertIn(">GET</h4>", rendered.rest_html)
            self.assertIn("WS body.", rendered.ws_html)
            self.assertEqual(
                [item.title for item in rendered.overview_nav],
                ["Path Layout"],
            )
            self.assertEqual(
                [item.title for item in rendered.rest_nav],
                ["/monitor/REST/0.1", "/monitor/REST/0.1/topics"],
            )
            self.assertIn(
                "Server Event: status",
                [item.title for item in rendered.ws_nav],
            )
            self.assertIn(
                "Command: configure-devkits",
                [item.title for item in rendered.ws_nav],
            )

    def test_rest_reference_nav_groups_methods_by_concrete_path(self):
        with TemporaryDirectory() as temp_dir:
            repo_root = Path(temp_dir)
            docs = repo_root / "docs"
            docs.mkdir()
            (docs / "monitor-protocol.md").write_text(
                "# AutoDRIVE RCT Monitor Protocol\n\n"
                "## REST API\n\n"
                "### GET `/monitor/REST/{version}/topics`\n\n"
                "GET body.\n\n"
                "### POST `/monitor/REST/{version}/topics`\n\n"
                "POST body.\n\n"
                "## WebSocket API\n",
                encoding="utf-8",
            )

            rendered = render_monitor_protocol_docs(repo_root, version="latest")

            self.assertEqual(
                [item.title for item in rendered.rest_nav],
                ["/monitor/REST/latest/topics"],
            )
            self.assertEqual(
                [item.anchor for item in rendered.rest_nav],
                ["monitor-rest-latest-topics"],
            )
            self.assertEqual(rendered.rest_html.count('id="monitor-rest-latest-topics"'), 1)
            self.assertIn(">GET</h4>", rendered.rest_html)
            self.assertIn(">POST</h4>", rendered.rest_html)

    def test_registered_monitor_rest_routes_populate_develop_reference(self):
        MONITOR_REST_REFERENCE.clear()
        try:
            app = web.Application()
            install_monitor_rest_route_collector(app.router)

            async def handler(_request):
                return web.json_response({"ok": True})

            app.router.add_get("/monitor/REST/{version}/topics", handler)
            app.router.add_post("/monitor/REST/{version}/topics", handler)
            app.router.add_delete("/monitor/REST/{version}/accident-logs", handler)
            app.router.add_get("/assets/{tail:.*}", handler)

            with TemporaryDirectory() as temp_dir:
                repo_root = Path(temp_dir)
                docs = repo_root / "docs"
                docs.mkdir()
                (docs / "monitor-protocol.md").write_text(
                    "# AutoDRIVE RCT Monitor Protocol\n\n"
                    "## REST API\n\n"
                    "Registered REST routes.\n\n"
                    "## WebSocket API\n",
                    encoding="utf-8",
                )

                rendered = render_monitor_protocol_docs(repo_root, version="latest", use_registered_routes=True)

            self.assertEqual(
                [item.title for item in rendered.rest_nav],
                [
                    "/monitor/REST/latest/topics",
                    "/monitor/REST/latest/accident-logs",
                ],
            )
            self.assertIn('id="monitor-rest-latest-topics"', rendered.rest_html)
            self.assertIn('id="monitor-rest-latest-accident-logs"', rendered.rest_html)
            self.assertIn(">GET</h4>", rendered.rest_html)
            self.assertIn(">POST</h4>", rendered.rest_html)
            self.assertIn(">DELETE</h4>", rendered.rest_html)
            self.assertNotIn("/assets", rendered.rest_html)
        finally:
            MONITOR_REST_REFERENCE.clear()

    def test_registered_routes_reuse_markdown_body_when_docs_heading_has_query(self):
        MONITOR_REST_REFERENCE.clear()
        try:
            app = web.Application()
            install_monitor_rest_route_collector(app.router)

            async def handler(_request):
                return web.json_response({"ok": True})

            app.router.add_get("/monitor/REST/{version}/accident-logs/ros2-mcap", handler)

            with TemporaryDirectory() as temp_dir:
                repo_root = Path(temp_dir)
                docs = repo_root / "docs"
                docs.mkdir()
                (docs / "monitor-protocol.md").write_text(
                    "# AutoDRIVE RCT Monitor Protocol\n\n"
                    "## REST API\n\n"
                    "### GET `/monitor/REST/{version}/accident-logs/ros2-mcap?path={path}`\n\n"
                    "Converts an accident MCAP selected by path.\n\n"
                    "## WebSocket API\n",
                    encoding="utf-8",
                )

                rendered = render_monitor_protocol_docs(repo_root, version="0.1", use_registered_routes=True)

            self.assertEqual(
                [item.title for item in rendered.rest_nav],
                ["/monitor/REST/0.1/accident-logs/ros2-mcap"],
            )
            self.assertIn("Converts an accident MCAP selected by path.", rendered.rest_html)
            self.assertNotIn("?path={path}", rendered.rest_html)
        finally:
            MONITOR_REST_REFERENCE.clear()


if __name__ == "__main__":
    unittest.main()
