# python-lsp-pyright

A [python-lsp-server](https://github.com/python-lsp/python-lsp-server) (pylsp)
plugin that adds [pyright](https://github.com/microsoft/pyright) type-checking
diagnostics. pylsp stays your language server; pyright is only run as a
checker.


## Warning

This is a quick and dirty implementation for personal use, completely done with Claude.
I only did a very brief review and do not claim any authorship of the code (hence the
Unlicense).  It is published on GitHub mostly to make installing it in my workspaces
easier.

Feel free to use it if you find it useful, but don't expect any support or maintenance
beyond fixing obvious bugs.


## Why?

pyright can be used as a language server itself, so why integrate it in
python-lsp-server?  Because personally, I use the latter and normally do not use pyright
at all.  However, for a specific project I need to use pyright for type checking.  I
still want to have all the rest done by python-lsp-server and running pyright as an
additional language server causes problems, as there are now two servers reacting to
things like "go to definition" or "rename" requests.

So to get type checking from pyright but keeping python-lsp-server for the rest, I
simply integrate the former into the latter with this plugin.


## Installation

Install the plugin into the same environment as pylsp:

```sh
# uses existing pyright installation
pip install "python-lsp-pyright @ git+https://github.com/luator/python-lsp-pyright.git"
# also installs pyright from PyPI
pip install "python-lsp-pyright[pyright] @ git+https://github.com/luator/python-lsp-pyright.git"
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
