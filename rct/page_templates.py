# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

from http import HTTPStatus
from pathlib import Path
from urllib.parse import unquote, urlparse

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .static_files import StaticFileResponse


def build_page_template_response(request_path: str, frontend_root: Path) -> StaticFileResponse | None:
    page = _page_from_request_path(request_path)
    if page is None:
        return None

    template_name, active_page, page_title = page
    environment = Environment(
        loader=FileSystemLoader(frontend_root / "templates"),
        autoescape=select_autoescape(("html",)),
        variable_start_string="[[",
        variable_end_string="]]",
    )
    body = environment.get_template(template_name).render(
        active_page=active_page,
        page_title=page_title,
    ).encode("utf-8")
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


def _page_from_request_path(request_path: str) -> tuple[str, str, str] | None:
    parsed = urlparse(request_path)
    normalized_path = unquote(parsed.path).rstrip("/") or "/"
    if normalized_path in {"/", "/index.html"}:
        return (
            "index.html",
            "race-control",
            "AutoDRIVE Race Control Tower",
        )
    if normalized_path == "/develop":
        return (
            "develop.html",
            "develop",
            "Develop - AutoDRIVE Race Control Tower",
        )
    return None
