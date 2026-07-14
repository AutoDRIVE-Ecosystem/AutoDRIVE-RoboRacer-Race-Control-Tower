# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .develop_reference import SUPPORTED_DEVELOP_VERSIONS, build_develop_reference


@dataclass(frozen=True)
class ProtocolNavItem:
    title: str
    anchor: str


@dataclass(frozen=True)
class ProtocolDocs:
    version: str
    overview_html: str
    rest_html: str
    ws_html: str
    overview_nav: tuple[ProtocolNavItem, ...]
    rest_nav: tuple[ProtocolNavItem, ...]
    ws_nav: tuple[ProtocolNavItem, ...]


def render_monitor_protocol_docs(
    repo_root: Path,
    version: str = "latest",
    *,
    use_registered_routes: bool = False,
) -> ProtocolDocs:
    del repo_root, use_registered_routes
    reference = build_develop_reference(version)
    return ProtocolDocs(
        version=reference["version"],
        overview_html="",
        rest_html="",
        ws_html="",
        overview_nav=(),
        rest_nav=tuple(
            ProtocolNavItem(route["path"], route["anchor"])
            for route in reference["rest_routes"]
        ),
        ws_nav=tuple(
            ProtocolNavItem(route["path"], route["anchor"])
            for route in reference["ws_routes"]
        )
        + tuple(
            ProtocolNavItem(
                f"{message['kind']}: {message['name']}",
                message["anchor"],
            )
            for message in reference["ws_messages"]
        ),
    )
