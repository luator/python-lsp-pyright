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
