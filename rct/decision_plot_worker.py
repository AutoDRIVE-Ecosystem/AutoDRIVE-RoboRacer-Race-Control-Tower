# SPDX-License-Identifier: BSD-3-Clause

from __future__ import annotations

import json
import sys

from .decision import render_decision_plot_svg


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python -m rct.decision_plot_worker <decision_id>", file=sys.stderr)
        return 2

    decision_id = sys.argv[1]
    try:
        summary = json.loads(sys.stdin.buffer.read().decode("utf-8"))
        sys.stdout.buffer.write(render_decision_plot_svg(decision_id, summary))
        sys.stdout.buffer.flush()
    except Exception as exc:
        print(f"failed to render decision plot: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
