# SPDX-License-Identifier: BSD-3-Clause

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from aiohttp import web

from rct.develop_reference import (
    DEVELOP_REFERENCE,
    OK_RESPONSE_SCHEMA,
    build_develop_reference,
    install_develop_reference_route_collector,
    monitor_input_schema,
    route_doc,
)
from rct.page_templates import build_page_template_response


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
        self.assertIn('href="/vendor/highlightjs/github-11.11.1.min.css"', html)
        self.assertIn('src="/assets/autodrive-extended-logo-3.png"', html)
        self.assertIn('src="/vendor/bootstrap/bootstrap-5.3.8.bundle.min.js"', html)
        self.assertIn('src="/vendor/highlightjs/highlight-11.11.1.min.js"', html)
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

    def test_route_collector_uses_third_argument_as_reference_description(self):
        DEVELOP_REFERENCE.clear()
        try:
            app = web.Application()
            install_develop_reference_route_collector(app.router)

            async def handler(_request):
                return web.json_response({"ok": True})

            app.router.add_get(
                "/monitor/REST/{version}/topics",
                handler,
                route_doc(
                    "Returns topic selections.",
                    input_schema=monitor_input_schema(),
                    output_schema=OK_RESPONSE_SCHEMA,
                ),
            )
            app.router.add_post("/monitor/REST/{version}/topics", handler, "Updates topic selections.")
            app.router.add_delete(
                "/monitor/REST/{version}/accident-logs",
                handler,
                "Deletes accident logs.",
            )
            app.router.add_get("/monitor/WS/{version}", handler, "Accepts monitor WebSocket clients.")
            app.router.add_get("/assets/{tail:.*}", handler)

            reference = build_develop_reference("latest")

            self.assertEqual(
                [route["path"] for route in reference["rest_routes"]],
                [
                    "/monitor/REST/latest/topics",
                    "/monitor/REST/latest/accident-logs",
                ],
            )
            self.assertEqual(
                [method["method"] for method in reference["rest_routes"][0]["methods"]],
                ["GET", "POST"],
            )
            self.assertEqual(reference["rest_routes"][0]["methods"][0]["description"], "Returns topic selections.")
            self.assertEqual(reference["rest_routes"][0]["methods"][0]["input_schema"]["properties"]["body"], {"type": "null"})
            self.assertEqual(reference["rest_routes"][0]["methods"][0]["output_schema"], OK_RESPONSE_SCHEMA)
            self.assertEqual(reference["rest_routes"][1]["methods"][0]["description"], "Deletes accident logs.")
            self.assertEqual(reference["ws_routes"][0]["path"], "/monitor/WS/latest")
            self.assertEqual(reference["ws_routes"][0]["methods"][0]["description"], "Accepts monitor WebSocket clients.")
        finally:
            DEVELOP_REFERENCE.clear()

    def test_route_collector_ignores_routes_without_reference_description(self):
        DEVELOP_REFERENCE.clear()
        try:
            app = web.Application()
            install_develop_reference_route_collector(app.router)

            async def handler(_request):
                return web.json_response({"ok": True})

            app.router.add_get("/monitor/REST/{version}/accident-logs/ros2-mcap", handler)
            app.router.add_get("/monitor/REST/{version}/topics", handler, "Returns topics.")

            reference = build_develop_reference("0.1")

            self.assertEqual(
                [route["path"] for route in reference["rest_routes"]],
                ["/monitor/REST/0.1/topics"],
            )
        finally:
            DEVELOP_REFERENCE.clear()

    def test_develop_template_renders_reference_dict(self):
        DEVELOP_REFERENCE.clear()
        try:
            app = web.Application()
            install_develop_reference_route_collector(app.router)

            async def handler(_request):
                return web.json_response({"ok": True})

            app.router.add_get(
                "/monitor/REST/{version}/topics",
                handler,
                route_doc(
                    "Returns topic selections.",
                    input_schema=monitor_input_schema(),
                    output_schema=OK_RESPONSE_SCHEMA,
                ),
            )
            app.router.add_post(
                "/monitor/REST/{version}/topics",
                handler,
                route_doc(
                    "Updates topic selections.",
                    input_schema=monitor_input_schema(),
                    output_schema=OK_RESPONSE_SCHEMA,
                ),
            )
            app.router.add_get("/monitor/WS/{version}", handler, "Accepts monitor WebSocket clients.")

            response = build_page_template_response("/develop/latest", Path("frontend"))

            self.assertIsNotNone(response)
            html = response.body.decode("utf-8")
            self.assertIn("Monitor Protocol Reference", html)
            self.assertIn("/monitor/REST/latest/topics", html)
            self.assertIn("Returns topic selections.", html)
            self.assertIn("Updates topic selections.", html)
            self.assertNotIn("handle_monitor_topics_get", html)
            self.assertIn("Input JSON Schema", html)
            self.assertIn("Output JSON Schema", html)
            self.assertIn('class="language-json"', html)
            self.assertIn("hljs.highlightAll();", html)
            self.assertIn("js-rct-run-get", html)
            self.assertIn("bi-play-fill", html)
            self.assertIn('data-route-path="/monitor/REST/latest/topics"', html)
            self.assertNotIn("GET Result", html)
            self.assertIn("rct-protocol-result-close", html)
            self.assertIn("bi-x-lg", html)
            self.assertIn("background-color: #0f172a", html)
            self.assertIn("font-size: 0.75rem", html)
            self.assertIn("font-size: 1.2rem", html)
            self.assertIn("font-size: 1rem", html)
            self.assertIn("font-size: 0.8rem", html)
            self.assertIn("text-transform: uppercase", html)
            self.assertIn("max-height: 400px", html)
            self.assertIn("overflow: auto", html)
            self.assertIn("data-spy-target", html)
            self.assertIn("data-spy-section", html)
            self.assertIn("is-active", html)
            self.assertIn("updateActiveSpyLink", html)
            self.assertIn("slideDown", html)
            self.assertNotIn('data-route-path="/monitor/WS/latest"', html)
            self.assertIn('"body"', html)
            output_title_index = html.index("Output JSON Schema")
            result_index = html.index('id="monitor-rest-latest-topics-get-result"', output_title_index)
            output_schema_index = html.index('<pre><code class="language-json">', output_title_index)
            self.assertLess(result_index, output_schema_index)
            get_section = html[
                html.index("Returns topic selections."):html.index("Updates topic selections.")
            ]
            self.assertNotIn("Input JSON Schema", get_section)
            self.assertIn("/monitor/WS/latest", html)
            self.assertIn("Accepts monitor WebSocket clients.", html)
            self.assertIn("Server Event:", html)
        finally:
            DEVELOP_REFERENCE.clear()


if __name__ == "__main__":
    unittest.main()
