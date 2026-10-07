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
