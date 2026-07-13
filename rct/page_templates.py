# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

from http import HTTPStatus
from pathlib import Path
from urllib.parse import unquote, urlparse

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .monitor_protocol_docs import SUPPORTED_DEVELOP_VERSIONS, render_monitor_protocol_docs
from .static_files import StaticFileResponse


def build_page_template_response(request_path: str, frontend_root: Path) -> StaticFileResponse | None:
    page = _page_from_request_path(request_path)
    if page is None:
        return None

    template_name, active_page, page_title, develop_version = page
    environment = Environment(
        loader=FileSystemLoader(frontend_root / "templates"),
        autoescape=select_autoescape(("html",)),
        variable_start_string="[[",
        variable_end_string="]]",
    )
    context = {
        "active_page": active_page,
        "page_title": page_title,
    }
    if template_name == "develop.html":
        context["monitor_protocol_docs"] = render_monitor_protocol_docs(
            frontend_root.parent,
            version=develop_version or "latest",
            use_registered_routes=True,
        )
    body = environment.get_template(template_name).render(**context).encode("utf-8")
    return StaticFileResponse(
        status_code=HTTPStatus.OK.value,
        reason_phrase=HTTPStatus.OK.phrase,
        headers=(
            ("Content-Type", "text/html; charset=utf-8"),
            ("Content-Length", str(len(body))),
            ("X-Content-Type-Options", "nosniff"),
        ),
        body=body,
    )


def _page_from_request_path(request_path: str) -> tuple[str, str, str, str | None] | None:
    parsed = urlparse(request_path)
    normalized_path = unquote(parsed.path).rstrip("/") or "/"
    if normalized_path in {"/", "/index.html"}:
        return (
            "index.html",
            "race-control",
            "AutoDRIVE Race Control Tower",
            None,
        )
    if normalized_path == "/develop":
        return (
            "develop.html",
            "develop",
            "Develop - AutoDRIVE Race Control Tower",
            "latest",
        )
    develop_prefix = "/develop/"
    if normalized_path.startswith(develop_prefix):
        version = normalized_path.removeprefix(develop_prefix)
        if version in SUPPORTED_DEVELOP_VERSIONS:
            return (
                "develop.html",
                "develop",
                f"Develop {version} - AutoDRIVE Race Control Tower",
                version,
            )
        return None
    return None
