# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


DocSectionName = Literal["overview", "rest", "ws"]
SUPPORTED_DEVELOP_VERSIONS = frozenset({"0.1", "latest"})


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


def render_monitor_protocol_docs(repo_root: Path, version: str = "latest") -> ProtocolDocs:
    if version not in SUPPORTED_DEVELOP_VERSIONS:
        raise ValueError(f"unsupported monitor protocol docs version: {version}")

    source_path = repo_root / "docs" / "monitor-protocol.md"
    if not source_path.is_file():
        unavailable = '<p class="text-body-secondary">Monitor protocol reference is not available.</p>'
        return ProtocolDocs(version, unavailable, "", "", (), (), ())

    lines = source_path.read_text(encoding="utf-8").splitlines()
    rest_index = _heading_index(lines, "## REST API")
    ws_index = _heading_index(lines, "## WebSocket API")
    overview_lines = lines[:rest_index]
    rest_lines = lines[rest_index:ws_index]
    ws_lines = lines[ws_index:]

    return ProtocolDocs(
        version=version,
        overview_html=_render_markdown_subset(overview_lines, skip_h1=True),
        rest_html=_render_markdown_subset(_group_rest_endpoint_sections(rest_lines, version)),
        ws_html=_render_markdown_subset(_replace_version_placeholders(ws_lines, version)),
        overview_nav=_build_nav(overview_lines, "overview"),
        rest_nav=_build_rest_nav(rest_lines, version),
        ws_nav=_build_nav(ws_lines, "ws"),
    )


def _heading_index(lines: list[str], heading: str) -> int:
    try:
        return lines.index(heading)
    except ValueError:
        return len(lines)


def _build_nav(lines: list[str], section: DocSectionName) -> tuple[ProtocolNavItem, ...]:
    nav_items: list[ProtocolNavItem] = []
    for line in lines:
        match = re.match(r"^(#{1,3})\s+(.+)$", line)
        if match is None:
            continue
        level = len(match.group(1))
        title = _plain_text(match.group(2))
        if section == "overview" and level == 1:
            continue
        if section == "rest" and level != 3:
            continue
        if section == "ws" and level == 1:
            continue
        nav_items.append(ProtocolNavItem(title=title, anchor=_heading_id(match.group(2))))
    return tuple(nav_items)


def _build_rest_nav(lines: list[str], version: str) -> tuple[ProtocolNavItem, ...]:
    nav_items: list[ProtocolNavItem] = []
    seen_paths: set[str] = set()
    for line in lines:
        parsed = _parse_rest_heading(line)
        if parsed is None:
            continue
        _method, path = parsed
        display_path = path.replace("{version}", version)
        if display_path in seen_paths:
            continue
        seen_paths.add(display_path)
        nav_items.append(ProtocolNavItem(title=display_path, anchor=_heading_id(f"`{display_path}`")))
    return tuple(nav_items)


def _group_rest_endpoint_sections(lines: list[str], version: str) -> list[str]:
    grouped: list[str] = []
    emitted_paths: set[str] = set()
    for line in lines:
        parsed = _parse_rest_heading(line)
        if parsed is None:
            grouped.append(_replace_version_placeholder(line, version))
            continue

        method, path = parsed
        display_path = path.replace("{version}", version)
        if display_path not in emitted_paths:
            grouped.append(f"### `{display_path}`")
            emitted_paths.add(display_path)
        grouped.append(f"#### {method}")
    return grouped


def _parse_rest_heading(line: str) -> tuple[str, str] | None:
    match = re.match(r"^###\s+([A-Z]+)\s+`([^`]+)`$", line)
    if match is None:
        return None
    return match.group(1), match.group(2)


def _replace_version_placeholders(lines: list[str], version: str) -> list[str]:
    return [_replace_version_placeholder(line, version) for line in lines]


def _replace_version_placeholder(line: str, version: str) -> str:
    return line.replace("{version}", version)


def _render_markdown_subset(lines: list[str], *, skip_h1: bool = False) -> str:
    output: list[str] = []
    paragraph: list[str] = []
    in_list = False
    in_code = False
    code_language = ""
    code_lines: list[str] = []
    heading_ids: dict[str, int] = {}

    def flush_paragraph() -> None:
        if not paragraph:
            return
        output.append(f"<p>{_inline_format(' '.join(paragraph))}</p>")
        paragraph.clear()

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            output.append("</ul>")
            in_list = False

    def close_code() -> None:
        class_attr = f' class="language-{html.escape(code_language, quote=True)}"' if code_language else ""
        output.append(f"<pre><code{class_attr}>{html.escape(chr(10).join(code_lines))}</code></pre>")
        code_lines.clear()

    for line in lines:
        if in_code:
            if line.startswith("```"):
                close_code()
                in_code = False
                code_language = ""
            else:
                code_lines.append(line)
            continue

        if line.startswith("```"):
            flush_paragraph()
            close_list()
            in_code = True
            code_language = line[3:].strip()
            continue

        heading = re.match(r"^(#{1,4})\s+(.+)$", line)
        if heading is not None:
            flush_paragraph()
            close_list()
            level = len(heading.group(1))
            text = heading.group(2)
            if skip_h1 and level == 1:
                continue
            output.append(
                f'<h{level} id="{_unique_heading_id(text, heading_ids)}">{_inline_format(text)}</h{level}>'
            )
            continue

        if not line.strip():
            flush_paragraph()
            close_list()
            continue

        list_item = re.match(r"^-\s+(.+)$", line)
        if list_item is not None:
            flush_paragraph()
            if not in_list:
                output.append("<ul>")
                in_list = True
            output.append(f"<li>{_inline_format(list_item.group(1))}</li>")
            continue

        paragraph.append(line.strip())

    flush_paragraph()
    close_list()
    if in_code:
        close_code()
    return "\n".join(output)


def _heading_id(text: str) -> str:
    slug = _plain_text(text).lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-") or "section"


def _unique_heading_id(text: str, heading_ids: dict[str, int]) -> str:
    base_id = _heading_id(text)
    count = heading_ids.get(base_id, 0)
    heading_ids[base_id] = count + 1
    if count == 0:
        return base_id
    return f"{base_id}-{count + 1}"


def _plain_text(text: str) -> str:
    return re.sub(r"`([^`]+)`", r"\1", text).strip()


def _inline_format(text: str) -> str:
    escaped = html.escape(text)
    return re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
