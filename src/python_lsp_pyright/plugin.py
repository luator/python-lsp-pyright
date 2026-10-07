"""python-lsp-server plugin that reports pyright diagnostics."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

log = logging.getLogger(__name__)

SOURCE = "pyright"

SEVERITIES = {"error": 1, "warning": 2, "information": 3}

# Used for errors that do not belong to a specific position.  Clients clip the
# end column to the line length.
FIRST_LINE = {
    "start": {"line": 0, "character": 0},
    "end": {"line": 0, "character": 1000},
}


def error_diagnostic(message: str) -> dict[str, Any]:
    """Return a diagnostic on the first line reporting that pyright failed."""
    return {"source": SOURCE, "range": FIRST_LINE, "message": message, "severity": 1}


def _same_file(a: str, b: str) -> bool:
    return os.path.normcase(os.path.realpath(a)) == os.path.normcase(
        os.path.realpath(b)
    )


def _to_diagnostic(entry: dict[str, Any]) -> dict[str, Any]:
    severity = entry.get("severity")
    if severity not in SEVERITIES:
        log.warning("unknown pyright severity %r", severity)

    diagnostic = {
        "source": SOURCE,
        "range": entry.get("range") or FIRST_LINE,
        "message": entry.get("message", ""),
        "severity": SEVERITIES.get(severity, 1),
    }
    if entry.get("rule"):
        diagnostic["code"] = entry["rule"]
    return diagnostic


def parse_output(stdout: str, document_path: str) -> list[dict[str, Any]]:
    """Convert the output of ``pyright --outputjson`` to LSP diagnostics.

    Only diagnostics for ``document_path`` are returned.  Text before the JSON
    object (e.g. installation messages of the pyright PyPI wrapper) is
    ignored.  Raises ``ValueError`` if no JSON object can be decoded.
    """
    start = stdout.find("{")
    if start == -1:
        raise ValueError("no JSON object in pyright output")
    # json.JSONDecodeError is a subclass of ValueError.
    report, _ = json.JSONDecoder().raw_decode(stdout, start)

    return [
        _to_diagnostic(entry)
        for entry in report.get("generalDiagnostics", [])
        if _same_file(entry.get("file", ""), document_path)
    ]
