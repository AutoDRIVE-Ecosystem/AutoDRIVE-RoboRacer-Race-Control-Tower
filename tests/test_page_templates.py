# SPDX-License-Identifier: BSD-3-Clause

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

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


if __name__ == "__main__":
    unittest.main()
