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
