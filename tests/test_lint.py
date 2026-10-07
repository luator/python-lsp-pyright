from __future__ import annotations

import json
import os
import subprocess
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


def test_non_string_executable(config, workspace, make_document, fake_run):
    config.update({"plugins": {"pyright": {"executable": ["npx", "pyright"]}}})

    assert messages(lint(config, workspace, make_document())) == [
        "pylsp.plugins.pyright.executable must be a string, got ['npx', 'pyright']"
    ]
    assert fake_run.calls == []


def test_unexpected_error_is_reported(config, workspace, make_document, fake_run):
    # An exception escaping the hook would drop the diagnostics of all plugins.
    fake_run.result = (0, '{"generalDiagnostics": null}', "")

    [diagnostic] = lint(config, workspace, make_document())

    assert diagnostic["message"].startswith("pyright plugin failed: TypeError")
    assert diagnostic["severity"] == 1


def test_unparsable_output_reports_stderr(config, workspace, make_document, fake_run):
    fake_run.result = (1, "", "Traceback ...\nURLError: no network\n")

    assert messages(lint(config, workspace, make_document())) == [
        "could not parse pyright output: Traceback ...\nURLError: no network"
    ]


def test_deleted_document_drops_cache(config, workspace, make_document, fake_run):
    document = make_document()
    fake_run.result = (1, output_for(document.path), "")
    lint(config, workspace, document)
    os.remove(document.path)

    assert lint(config, workspace, document, is_saved=False) == []
    assert document.path not in plugin.last_diagnostics


def test_unsaved_reruns_when_file_changed_on_disk(
    config, workspace, make_document, fake_run
):
    # E.g. a save whose lint was debounced away, or a git checkout.
    document = make_document(source="x = 1\n")
    fake_run.result = (1, output_for(document.path, "first"), "")
    lint(config, workspace, document)
    with open(document.path, "w") as f:
        f.write("x = 'changed'\n")
    fake_run.result = (1, output_for(document.path, "second"), "")

    diagnostics = lint(config, workspace, document, is_saved=False)

    assert len(fake_run.calls) == 2
    assert messages(diagnostics) == ["second"]


def test_run_pyright_decodes_utf8_regardless_of_locale(tmp_path):
    # pyright writes UTF-8; run the plugin in an interpreter with ASCII locale.
    # Keep the command line ASCII; the bytes are "Tübingen Ё" in UTF-8.
    child = r"import sys; sys.stdout.buffer.write(b'T\xc3\xbcbingen \xd0\x81')"
    parent = (
        "import sys\n"
        "from python_lsp_pyright import plugin\n"
        f"_, out, _ = plugin.run_pyright([sys.executable, '-c', {child!r}], None)\n"
        "sys.stdout.buffer.write(out.encode('utf-8'))\n"
    )
    env = dict(os.environ, LC_ALL="C", PYTHONCOERCECLOCALE="0", PYTHONUTF8="0")
    result = subprocess.run(
        [sys.executable, "-c", parent], env=env, capture_output=True, check=False
    )
    assert result.returncode == 0, result.stderr.decode(errors="replace")
    assert result.stdout.decode("utf-8") == "Tübingen Ё"
