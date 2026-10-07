"""python-lsp-server plugin that reports pyright diagnostics."""

from __future__ import annotations

import json
import logging
import os
import subprocess
from typing import Any

from pylsp import hookimpl

log = logging.getLogger(__name__)

SOURCE = "pyright"

SEVERITIES = {"error": 1, "warning": 2, "information": 3}

# Used for errors that do not belong to a specific position.  Clients clip the
# end column to the line length.
FIRST_LINE = {
    "start": {"line": 0, "character": 0},
    "end": {"line": 0, "character": 1000},
}

# pylsp lints on every change and replaces all diagnostics of the document with
# the result.  pyright only checks the saved file, so unsaved lints return the
# (possibly stale) diagnostics of the last run instead of clearing them.
last_diagnostics: dict[str, list[dict[str, Any]]] = {}


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


def build_command(executable: str, path: str) -> list[str]:
    """Return the command line that checks ``path`` with pyright."""
    return [executable, "--outputjson", path]


def run_pyright(command: list[str], cwd: str | None) -> tuple[int, str, str]:
    """Run pyright and return its exit code, stdout and stderr."""
    process = subprocess.run(
        command, cwd=cwd, capture_output=True, text=True, check=False
    )
    return process.returncode, process.stdout, process.stderr


def _failure(message: str) -> list[dict[str, Any]]:
    log.error("%s", message)
    return [error_diagnostic(message)]


def _check(executable: str, path: str, cwd: str | None) -> list[dict[str, Any]]:
    command = build_command(executable, path)
    log.debug("running %s in %s", command, cwd)
    try:
        code, stdout, stderr = run_pyright(command, cwd)
    except FileNotFoundError:
        return _failure(
            f"pyright executable '{executable}' not found; install pyright or set "
            "pylsp.plugins.pyright.executable"
        )
    except OSError as e:
        return _failure(f"could not run pyright executable '{executable}': {e}")

    # Exit code 1 only means that errors were reported.
    if code not in (0, 1):
        return _failure(
            stderr.strip() or stdout.strip() or f"pyright exited with code {code}"
        )

    try:
        return parse_output(stdout, path)
    except ValueError:
        return _failure(f"could not parse pyright output: {stdout[:500]}")


@hookimpl
def pylsp_settings(config) -> dict[str, Any]:
    return {"plugins": {"pyright": {"enabled": True, "executable": "pyright"}}}


@hookimpl
def pylsp_lint(config, workspace, document, is_saved) -> list[dict[str, Any]]:
    path = document.path
    if not is_saved and path in last_diagnostics:
        return last_diagnostics[path]

    # pyright only checks files on disk, so e.g. untitled buffers are skipped.
    if not os.path.isfile(path):
        return []

    settings = config.plugin_settings("pyright")
    diagnostics = _check(
        settings.get("executable") or "pyright", path, workspace.root_path or None
    )
    log.info("pyright reported %d diagnostics for %s", len(diagnostics), path)
    last_diagnostics[path] = diagnostics
    return diagnostics
