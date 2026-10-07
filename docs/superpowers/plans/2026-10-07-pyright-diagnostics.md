# pyright diagnostics for pylsp — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A pylsp plugin, `python-lsp-pyright`, that runs `pyright --outputjson <file>` when a document is opened or saved and publishes the results as LSP diagnostics.

**Architecture:** One module, `src/python_lsp_pyright/plugin.py`, registered through the `pylsp` entry point as `pyright`. Pure helpers (`build_command`, `run_pyright`, `parse_output`, `error_diagnostic`) are called by two pluggy hooks (`pylsp_settings`, `pylsp_lint`). A module-level cache keyed by document path returns the last result on unsaved lints, following pylsp-mypy.

**Tech Stack:** Python ≥3.9, python-lsp-server (pluggy hooks), pyright CLI, uv (`uv_build` backend), pytest.

**Spec:** `docs/superpowers/specs/2026-10-07-pyright-diagnostics-design.md`

## Global Constraints

- `requires-python = ">=3.9"`; every module starts with `from __future__ import annotations`. No `match` statements and no `X | Y` outside annotations.
- Runtime dependencies: only `python-lsp-server`. Optional extra `pyright = ["pyright"]`. Dev group: `pytest`, `pyright`.
- Entry point: `[project.entry-points.pylsp] pyright = "python_lsp_pyright.plugin"`. Settings live under `pylsp.plugins.pyright` with defaults `{"enabled": True, "executable": "pyright"}`.
- Every diagnostic has `source = "pyright"`. Severity: `error` → 1, `warning` → 2, `information` → 3, anything else → 1 plus a logged warning.
- The error diagnostic range is always `{"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 1000}}` with severity 1.
- Use `logging.getLogger(__name__)`. No timeout on the subprocess.
- VCS: use **git** (the repo is also colocated with jj, so leave `.jj/` alone). Work on branch `pyright-diagnostics`. End every commit message with the line `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`. git has no user identity configured in this environment: unless the user has configured one by then, run commits as `git -c user.name="Felix Kloss" -c user.email="felix.kloss@uni-tuebingen.de" commit ...` and don't change any git config.
- Run everything through uv: `uv sync`, `uv run pytest`.

## Review Focus

- **A document that isn't on disk** (an untitled buffer, or a file deleted while open). Expect no pyright diagnostics and no error diagnostic, and don't cache the result. Pinned in Task 2 (`test_document_not_on_disk_is_skipped`).
- **pylsp started without a workspace root** (`root_path == ""`). `subprocess.run(cwd="")` would raise `FileNotFoundError` and get misreported as "executable not found". Expect pyright to run with `cwd=None`. Pinned in Task 2 (`test_empty_root_path_runs_without_cwd`).
- **Text on stdout before the JSON**, e.g. first-run messages from the PyPI wrapper. Expect the JSON to be parsed anyway. Pinned in Task 1 (`test_ignores_text_before_json`).
- **pyright killed by a signal (negative exit code), or the executable not runnable (`PermissionError`).** Expect the single error diagnostic, not a crash and not an empty result. Pinned in Task 2 (`test_killed_by_signal`, `test_executable_not_runnable`).
- **A workspace path containing spaces.** Expect the real pyright run to work. Pinned in Task 3: the project directory is `"my project"`.

---

## Setup (before Task 1)

- [ ] Create the branch from the current HEAD (which holds the spec and plan commits):

```bash
git checkout -b pyright-diagnostics
```

---

### Task 1: Packaging and `parse_output`

**Files:**
- Modify: `pyproject.toml` (whole file)
- Modify: `src/python_lsp_pyright/__init__.py` (whole file)
- Create: `src/python_lsp_pyright/plugin.py`
- Create: `tests/test_parse.py`

**Interfaces:**
- Consumes: nothing.
- Produces (in `python_lsp_pyright.plugin`):
  - `SOURCE: str = "pyright"`
  - `error_diagnostic(message: str) -> dict[str, Any]`
  - `parse_output(stdout: str, document_path: str) -> list[dict[str, Any]]` (raises `ValueError` if there is no decodable JSON object)
  - `log: logging.Logger`

- [ ] **Step 1: Replace `pyproject.toml`**

```toml
[project]
name = "python-lsp-pyright"
version = "0.1.0"
description = "pyright diagnostics for python-lsp-server"
readme = "README.md"
authors = [
    { name = "Felix Kloss", email = "felix.kloss@uni-tuebingen.de" }
]
requires-python = ">=3.9"
dependencies = ["python-lsp-server"]

[project.optional-dependencies]
pyright = ["pyright"]

[project.entry-points.pylsp]
pyright = "python_lsp_pyright.plugin"

[dependency-groups]
dev = ["pytest", "pyright"]

[build-system]
requires = ["uv_build>=0.11.28,<0.12.0"]
build-backend = "uv_build"
```

(This removes the `[project.scripts]` entry from `uv init`.)

- [ ] **Step 2: Replace `src/python_lsp_pyright/__init__.py`**

```python
"""pyright diagnostics for python-lsp-server."""
```

- [ ] **Step 3: Create a stub `src/python_lsp_pyright/plugin.py`** so the entry point imports

```python
"""python-lsp-server plugin that reports pyright diagnostics."""

from __future__ import annotations
```

- [ ] **Step 4: Install the environment**

Run: `uv sync`
Expected: creates `.venv` and installs python-lsp-server, pytest, pyright, and the project in editable mode, without errors.

- [ ] **Step 5: Write the failing tests in `tests/test_parse.py`**

```python
from __future__ import annotations

import json
import os

import pytest

from python_lsp_pyright.plugin import error_diagnostic, parse_output

DOC = os.path.abspath("example.py")

RANGE = {"start": {"line": 1, "character": 2}, "end": {"line": 1, "character": 5}}


def entry(file=DOC, severity="error", message="msg", rule="reportFoo", rng=RANGE):
    result = {"file": file, "severity": severity, "message": message}
    if rng is not None:
        result["range"] = rng
    if rule is not None:
        result["rule"] = rule
    return result


def report(*entries):
    return json.dumps(
        {"version": "1.1.414", "generalDiagnostics": list(entries), "summary": {}}
    )


def test_converts_entry():
    assert parse_output(report(entry()), DOC) == [
        {
            "source": "pyright",
            "range": RANGE,
            "message": "msg",
            "severity": 1,
            "code": "reportFoo",
        }
    ]


@pytest.mark.parametrize(
    ("severity", "expected"),
    [("error", 1), ("warning", 2), ("information", 3), ("bogus", 1)],
)
def test_severity_mapping(severity, expected):
    [diagnostic] = parse_output(report(entry(severity=severity)), DOC)
    assert diagnostic["severity"] == expected


def test_omits_code_without_rule():
    [diagnostic] = parse_output(report(entry(rule=None)), DOC)
    assert "code" not in diagnostic


def test_missing_range_uses_first_line():
    [diagnostic] = parse_output(report(entry(rng=None)), DOC)
    assert diagnostic["range"] == {
        "start": {"line": 0, "character": 0},
        "end": {"line": 0, "character": 1000},
    }


def test_filters_other_files():
    other = os.path.abspath("other.py")
    output = report(entry(file=other), entry(message="mine"))
    assert [d["message"] for d in parse_output(output, DOC)] == ["mine"]


def test_matches_symlinked_path(tmp_path):
    real = tmp_path / "real.py"
    real.write_text("")
    link = tmp_path / "link.py"
    link.symlink_to(real)
    [diagnostic] = parse_output(report(entry(file=str(real))), str(link))
    assert diagnostic["message"] == "msg"


def test_no_diagnostics():
    assert parse_output(report(), DOC) == []


def test_ignores_text_before_json():
    output = "Installing pyright...\n" + report(entry())
    assert len(parse_output(output, DOC)) == 1


@pytest.mark.parametrize("output", ["", "not json", "{broken"])
def test_invalid_output_raises(output):
    with pytest.raises(ValueError):
        parse_output(output, DOC)


def test_error_diagnostic():
    assert error_diagnostic("it broke") == {
        "source": "pyright",
        "range": {
            "start": {"line": 0, "character": 0},
            "end": {"line": 0, "character": 1000},
        },
        "message": "it broke",
        "severity": 1,
    }
```

- [ ] **Step 6: Run the tests to verify they fail**

Run: `uv run pytest tests/test_parse.py -v`
Expected: collection error `ImportError: cannot import name 'error_diagnostic' from 'python_lsp_pyright.plugin'`.

- [ ] **Step 7: Implement in `src/python_lsp_pyright/plugin.py`** (replace the stub)

```python
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
```

- [ ] **Step 8: Run the tests to verify they pass**

Run: `uv run pytest tests/test_parse.py -v`
Expected: all tests PASS.

- [ ] **Step 9: Commit**

```bash
git add pyproject.toml uv.lock src/python_lsp_pyright/__init__.py src/python_lsp_pyright/plugin.py tests/test_parse.py
git commit -m "Add packaging and pyright JSON output parsing

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Running pyright and the pylsp hooks

**Files:**
- Modify: `src/python_lsp_pyright/plugin.py` (add imports and append new functions)
- Create: `tests/conftest.py`
- Create: `tests/test_lint.py`

**Interfaces:**
- Consumes (from Task 1): `SOURCE`, `error_diagnostic(message) -> dict`, `parse_output(stdout, document_path) -> list[dict]`, `log`.
- Produces (in `python_lsp_pyright.plugin`):
  - `last_diagnostics: dict[str, list[dict[str, Any]]]`, keyed by `document.path`
  - `build_command(executable: str, path: str) -> list[str]`
  - `run_pyright(command: list[str], cwd: str | None) -> tuple[int, str, str]`
  - `pylsp_settings(config) -> dict` (hook)
  - `pylsp_lint(config, workspace, document, is_saved) -> list[dict[str, Any]]` (hook)
- Test fixtures (in `tests/conftest.py`), used by Task 3 as well: `config`, `workspace`, `make_document(name="example.py", source="x = 1\n") -> Document`. There is also an autouse fixture that clears `plugin.last_diagnostics`.

- [ ] **Step 1: Write `tests/conftest.py`**

```python
from __future__ import annotations

from unittest.mock import Mock

import pytest
from pylsp import uris
from pylsp.config.config import Config
from pylsp.workspace import Document, Workspace

from python_lsp_pyright import plugin


@pytest.fixture(autouse=True)
def clear_cache():
    plugin.last_diagnostics.clear()
    yield
    plugin.last_diagnostics.clear()


@pytest.fixture
def root(tmp_path):
    return tmp_path


@pytest.fixture
def config(root):
    return Config(uris.from_fs_path(str(root)), {}, 0, {})


@pytest.fixture
def workspace(root, config):
    return Workspace(uris.from_fs_path(str(root)), Mock(), config)


@pytest.fixture
def make_document(root, workspace):
    def make(name="example.py", source="x = 1\n"):
        path = root / name
        path.write_text(source)
        return Document(uris.from_fs_path(str(path)), workspace)

    return make
```

- [ ] **Step 2: Write the failing tests in `tests/test_lint.py`**

```python
from __future__ import annotations

import json
import sys
from types import SimpleNamespace

import pytest
from pylsp import uris
from pylsp.workspace import Document

from python_lsp_pyright import plugin

RANGE = {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 1}}


def output_for(path, message="boom"):
    return json.dumps(
        {
            "generalDiagnostics": [
                {
                    "file": path,
                    "severity": "error",
                    "message": message,
                    "range": RANGE,
                    "rule": "reportFoo",
                }
            ]
        }
    )


@pytest.fixture
def fake_run(monkeypatch):
    """Replace run_pyright; set .result (tuple) or .error (exception)."""

    class FakeRun:
        def __init__(self):
            self.calls = []
            self.result = (0, '{"generalDiagnostics": []}', "")
            self.error = None

        def __call__(self, command, cwd):
            self.calls.append((command, cwd))
            if self.error is not None:
                raise self.error
            return self.result

    fake = FakeRun()
    monkeypatch.setattr(plugin, "run_pyright", fake)
    return fake


def lint(config, workspace, document, is_saved=True):
    return plugin.pylsp_lint(
        config=config, workspace=workspace, document=document, is_saved=is_saved
    )


def messages(diagnostics):
    return [d["message"] for d in diagnostics]


def test_plugin_is_registered(config):
    assert config.plugin_manager.get_plugin("pyright") is plugin
    assert config.plugin_settings("pyright") == {
        "enabled": True,
        "executable": "pyright",
    }


def test_build_command():
    assert plugin.build_command("pyright", "/a/b.py") == [
        "pyright",
        "--outputjson",
        "/a/b.py",
    ]


def test_run_pyright(tmp_path):
    script = (
        "import os, sys; print(os.getcwd()); "
        "sys.stderr.write('err'); sys.exit(3)"
    )
    code, stdout, stderr = plugin.run_pyright(
        [sys.executable, "-c", script], cwd=str(tmp_path)
    )
    assert code == 3
    assert stdout.strip() == str(tmp_path)
    assert stderr == "err"


def test_runs_pyright_on_saved_document(config, workspace, make_document, fake_run):
    document = make_document()
    fake_run.result = (1, output_for(document.path), "")

    diagnostics = lint(config, workspace, document)

    assert fake_run.calls == [
        (["pyright", "--outputjson", document.path], workspace.root_path)
    ]
    assert diagnostics == [
        {
            "source": "pyright",
            "range": RANGE,
            "message": "boom",
            "severity": 1,
            "code": "reportFoo",
        }
    ]


def test_custom_executable(config, workspace, make_document, fake_run):
    config.update({"plugins": {"pyright": {"executable": "/opt/bin/pyright"}}})
    document = make_document()

    lint(config, workspace, document)

    assert fake_run.calls[0][0][0] == "/opt/bin/pyright"


def test_unsaved_returns_cache_without_running(
    config, workspace, make_document, fake_run
):
    document = make_document()
    fake_run.result = (1, output_for(document.path), "")
    lint(config, workspace, document)

    diagnostics = lint(config, workspace, document, is_saved=False)

    assert len(fake_run.calls) == 1
    assert messages(diagnostics) == ["boom"]


def test_unsaved_without_cache_runs(config, workspace, make_document, fake_run):
    document = make_document()
    fake_run.result = (1, output_for(document.path), "")

    diagnostics = lint(config, workspace, document, is_saved=False)

    assert len(fake_run.calls) == 1
    assert messages(diagnostics) == ["boom"]


def test_saved_refreshes_cache(config, workspace, make_document, fake_run):
    document = make_document()
    fake_run.result = (1, output_for(document.path, "first"), "")
    lint(config, workspace, document)
    fake_run.result = (1, output_for(document.path, "second"), "")

    assert messages(lint(config, workspace, document)) == ["second"]
    assert messages(lint(config, workspace, document, is_saved=False)) == ["second"]


def test_document_not_on_disk_is_skipped(config, workspace, root, fake_run):
    document = Document(uris.from_fs_path(str(root / "missing.py")), workspace)

    assert lint(config, workspace, document) == []
    assert fake_run.calls == []
    assert document.path not in plugin.last_diagnostics


def test_empty_root_path_runs_without_cwd(config, make_document, fake_run):
    document = make_document()

    lint(config, SimpleNamespace(root_path=""), document)

    assert fake_run.calls[0][1] is None


def test_exit_code_0_without_diagnostics(config, workspace, make_document, fake_run):
    assert lint(config, workspace, make_document()) == []


def test_executable_not_found(config, workspace, make_document, fake_run):
    fake_run.error = FileNotFoundError(2, "No such file or directory")

    assert messages(lint(config, workspace, make_document())) == [
        "pyright executable 'pyright' not found; install pyright or set "
        "pylsp.plugins.pyright.executable"
    ]


def test_executable_not_runnable(config, workspace, make_document, fake_run):
    fake_run.error = PermissionError(13, "Permission denied")

    [diagnostic] = lint(config, workspace, make_document())

    assert diagnostic["message"] == (
        "could not run pyright executable 'pyright': [Errno 13] Permission denied"
    )
    assert diagnostic["severity"] == 1


def test_fatal_exit_reports_stderr(config, workspace, make_document, fake_run):
    fake_run.result = (3, "out", "config error\n")

    assert messages(lint(config, workspace, make_document())) == ["config error"]


def test_fatal_exit_falls_back_to_stdout(config, workspace, make_document, fake_run):
    fake_run.result = (2, "fatal\n", "")

    assert messages(lint(config, workspace, make_document())) == ["fatal"]


def test_fatal_exit_without_output(config, workspace, make_document, fake_run):
    fake_run.result = (4, "", "")

    assert messages(lint(config, workspace, make_document())) == [
        "pyright exited with code 4"
    ]


def test_killed_by_signal(config, workspace, make_document, fake_run):
    fake_run.result = (-9, "", "")

    assert messages(lint(config, workspace, make_document())) == [
        "pyright exited with code -9"
    ]


def test_unparsable_output(config, workspace, make_document, fake_run):
    fake_run.result = (0, "x" * 600, "")

    assert messages(lint(config, workspace, make_document())) == [
        "could not parse pyright output: " + "x" * 500
    ]


def test_error_is_cached(config, workspace, make_document, fake_run):
    document = make_document()
    fake_run.error = FileNotFoundError(2, "No such file or directory")
    lint(config, workspace, document)

    diagnostics = lint(config, workspace, document, is_saved=False)

    assert len(fake_run.calls) == 1
    assert "not found" in diagnostics[0]["message"]
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/test_lint.py -v`
Expected: FAIL. `test_plugin_is_registered` fails because the settings are `{}`, and the other tests fail with `AttributeError: ... has no attribute 'run_pyright'` (raised by `monkeypatch.setattr`) or no attribute `build_command` / `pylsp_lint`.

- [ ] **Step 4: Implement.** In `src/python_lsp_pyright/plugin.py`, change the imports at the top to:

```python
from __future__ import annotations

import json
import logging
import os
import subprocess
from typing import Any

from pylsp import hookimpl
```

Then add the cache directly after the `FIRST_LINE` definition:

```python
# pylsp lints on every change and replaces all diagnostics of the document with
# the result.  pyright only checks the saved file, so unsaved lints return the
# (possibly stale) diagnostics of the last run instead of clearing them.
last_diagnostics: dict[str, list[dict[str, Any]]] = {}
```

Then append at the end of the file:

```python
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
```

- [ ] **Step 5: Run all tests to verify they pass**

Run: `uv run pytest -v`
Expected: all tests in `tests/test_parse.py` and `tests/test_lint.py` PASS.

- [ ] **Step 6: Commit**

```bash
git add src/python_lsp_pyright/plugin.py tests/conftest.py tests/test_lint.py
git commit -m "Add pylsp lint and settings hooks running pyright

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: End-to-end test with real pyright, and README

**Files:**
- Create: `tests/test_end_to_end.py`
- Modify: `README.md` (currently empty)

**Interfaces:**
- Consumes: `plugin.pylsp_lint` (Task 2); the fixtures `root`, `config`, `workspace`, `make_document` from `tests/conftest.py` (Task 2). This test overrides `root` so the project path contains a space.
- Produces: nothing new.

- [ ] **Step 1: Write `tests/test_end_to_end.py`**

```python
from __future__ import annotations

import shutil

import pytest

from python_lsp_pyright import plugin

pytestmark = pytest.mark.skipif(
    shutil.which("pyright") is None, reason="pyright is not installed"
)


@pytest.fixture
def root(tmp_path):
    # A space in the path makes sure arguments are passed without a shell.
    path = tmp_path / "my project"
    path.mkdir()
    return path


def lint(config, workspace, document):
    return plugin.pylsp_lint(
        config=config, workspace=workspace, document=document, is_saved=True
    )


def test_reports_type_error(config, workspace, make_document):
    document = make_document(source='x: int = "a"\n')

    [diagnostic] = lint(config, workspace, document)

    assert diagnostic["source"] == "pyright"
    assert diagnostic["code"] == "reportAssignmentType"
    assert diagnostic["severity"] == 1
    assert diagnostic["range"] == {
        "start": {"line": 0, "character": 9},
        "end": {"line": 0, "character": 12},
    }


def test_clean_file(config, workspace, make_document):
    assert lint(config, workspace, make_document(source="x: int = 1\n")) == []


def test_uses_project_config(root, config, workspace, make_document):
    (root / "pyrightconfig.json").write_text('{"reportAssignmentType": "warning"}')
    document = make_document(source='x: int = "a"\n')

    [diagnostic] = lint(config, workspace, document)

    assert diagnostic["severity"] == 2
```

- [ ] **Step 2: Run the end-to-end tests**

Run: `uv run pytest tests/test_end_to_end.py -v`
Expected: 3 PASS, not skipped. The dev group installs `pyright` into `.venv/bin`, and the first run may take a few seconds while the wrapper fetches pyright. If they are SKIPPED, `uv run` is not putting `.venv/bin` on PATH. Find out why rather than accepting the skip. If `test_uses_project_config` fails, pyright is not picking up config from the working directory; report it, because the spec's config claim depends on it.

- [ ] **Step 3: Write `README.md`**

````markdown
# python-lsp-pyright

A [python-lsp-server](https://github.com/python-lsp/python-lsp-server) (pylsp)
plugin that adds [pyright](https://github.com/microsoft/pyright) type-checking
diagnostics. pylsp stays your language server; pyright is only run as a
checker.

## Installation

Install the plugin into the same environment as pylsp:

```sh
pip install python-lsp-pyright            # uses `pyright` from PATH
pip install "python-lsp-pyright[pyright]" # also installs pyright from PyPI
```

The PyPI `pyright` package downloads Node.js and pyright on its first run.
You can also install pyright any other way (e.g. `npm install -g pyright`)
and either put it on PATH or point the `executable` setting at it.

## Behaviour

- pyright runs on a file when it is opened and every time it is saved.
  While you edit, the diagnostics from the last run stay visible, so their
  positions may be outdated until you save.
- pyright runs in the workspace root, so `pyrightconfig.json` and
  `[tool.pyright]` in `pyproject.toml` apply just as when you run `pyright`
  in a terminal. Without configuration, pyright uses the `python` on PATH to
  resolve imports.
- If pyright cannot be run or fails, the error is shown as a diagnostic on
  the first line of the file.

## Settings

| Setting | Default | Description |
|---|---|---|
| `pylsp.plugins.pyright.enabled` | `true` | Enable or disable the plugin. |
| `pylsp.plugins.pyright.executable` | `"pyright"` | pyright command to run. |
````

- [ ] **Step 4: Run the full test suite**

Run: `uv run pytest -v`
Expected: all tests PASS, none skipped.

- [ ] **Step 5: Smoke test through pylsp itself**

Run this from the repo root. It sends initialize, didOpen and exit to a real `pylsp` process over stdio and prints the pyright diagnostics it publishes:

(`timeout` guards against a blocking `readline` if pylsp never answers.)

```bash
timeout 120 uv run python - <<'EOF'
import json, pathlib, subprocess, tempfile, time
d = pathlib.Path(tempfile.mkdtemp())
f = d / "t.py"; f.write_text('x: int = "a"\n')
def msg(o):
    b = json.dumps(o).encode()
    return b"Content-Length: %d\r\n\r\n" % len(b) + b
p = subprocess.Popen(["pylsp"], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
p.stdin.write(msg({"jsonrpc": "2.0", "id": 1, "method": "initialize",
    "params": {"processId": None, "rootUri": d.as_uri(), "capabilities": {}}}))
p.stdin.write(msg({"jsonrpc": "2.0", "method": "initialized", "params": {}}))
p.stdin.write(msg({"jsonrpc": "2.0", "method": "textDocument/didOpen", "params": {
    "textDocument": {"uri": f.as_uri(), "languageId": "python", "version": 1,
                     "text": f.read_text()}}}))
p.stdin.flush()
deadline = time.time() + 60
while time.time() < deadline:
    header = p.stdout.readline()
    if not header.startswith(b"Content-Length"):
        continue
    n = int(header.split(b":")[1]); p.stdout.readline()
    m = json.loads(p.stdout.read(n))
    if m.get("method") == "textDocument/publishDiagnostics":
        ds = [x for x in m["params"]["diagnostics"] if x.get("source") == "pyright"]
        if ds:
            print(json.dumps(ds, indent=1)); break
p.stdin.write(msg({"jsonrpc": "2.0", "method": "exit"})); p.stdin.flush()
p.kill()
EOF
```

Expected: prints a list containing one diagnostic with `"code": "reportAssignmentType"`. If it prints nothing within 60 s, the plugin is not loaded through the entry point. Investigate; don't just retry.

- [ ] **Step 6: Commit**

```bash
git add tests/test_end_to_end.py README.md
git commit -m "Add end-to-end test against real pyright and README

Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
```
