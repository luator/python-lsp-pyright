# python-lsp-pyright: pyright diagnostics for pylsp — Design

Date: 2026-10-07

## Goal

A [python-lsp-server](https://github.com/python-lsp/python-lsp-server) (pylsp)
plugin that adds pyright's type-checking diagnostics to the diagnostics pylsp
already publishes. pylsp remains the language server; pyright is used only as a
command-line checker. No completion, hover, or other pyright language features.

Where a design question is open, follow the approach of
[pylsp-mypy](https://github.com/python-lsp/pylsp-mypy), which does the same
job for mypy.

### Success criteria

- With the plugin installed in the same environment as pylsp, opening or saving
  a Python file shows pyright's errors, warnings, and information messages in
  the editor, with correct ranges and severities, alongside other pylsp
  diagnostics.
- Pyright's diagnostics do not disappear while the user types between saves.
- If pyright is missing or fails, the user sees why, in the editor.
- Unit and integration tests cover the behaviour below.

### Non-goals

- Live (as-you-type) checking of unsaved buffer contents.
- Running `pyright-langserver` or any long-lived pyright process.
- Choosing or detecting a Python interpreter/virtualenv (pyright's own config
  and the `python` on PATH decide; the user installs pylsp into the project
  venv).
- Progress reporting, exclude patterns, hover, `# pyright: ignore[...]` code
  actions, and per-project plugin config in `pyproject.toml`. These are
  possible later additions.

## Observed facts this design relies on

Verified against pylsp 1.15.0 and pyright 1.1.414:

- pylsp calls `pylsp_lint(..., is_saved=True)` on `didOpen` and `didSave`, and
  `is_saved=False` on every `didChange`. Each lint replaces the document's whole
  diagnostic set with the union of all plugins' results, so returning `[]` on
  change would clear pyright diagnostics.
- `pyright --outputjson <file>` prints a JSON object whose `generalDiagnostics`
  entries have `file` (absolute path), `severity` (`"error"`, `"warning"`,
  `"information"`), `message`, `range` (already LSP-shaped, 0-based
  `line`/`character`), and an optional `rule`.
- pyright exit codes: 0 = no errors, 1 = errors reported, ≥2 = fatal error,
  config error, or invalid arguments.

## Architecture

Package layout (src layout, `uv_build` backend):

```
src/python_lsp_pyright/
    __init__.py
    plugin.py        # hook implementations and helpers
tests/
    test_plugin.py
```

The `uv init` placeholder `main()` and its `[project.scripts]` entry are
removed.

### Registration

```toml
[project.entry-points.pylsp]
pyright = "python_lsp_pyright.plugin"
```

The plugin name is `pyright`, so its settings live under
`pylsp.plugins.pyright.*`, and `pylsp.plugins.pyright.enabled = false`
disables it through pylsp's standard mechanism.

### Settings

Provided by `pylsp_settings()` as defaults:

| Setting | Default | Meaning |
|---|---|---|
| `pylsp.plugins.pyright.enabled` | `true` | Standard pylsp plugin switch. |
| `pylsp.plugins.pyright.executable` | `"pyright"` | Command used to run pyright; resolved via PATH if not absolute. |

### Components (in `plugin.py`)

Small functions with one job each, so the parsing logic is testable without
running pyright:

- `build_command(executable, path) -> list[str]`
  Returns `[executable, "--outputjson", path]`.
- `run_pyright(command, cwd) -> tuple[int, str, str]`
  Runs the command with `subprocess.run(..., capture_output=True, text=True)`
  and returns `(returncode, stdout, stderr)`. Lets `FileNotFoundError`
  propagate to the caller.
- `parse_output(stdout, document_path) -> list[dict]`
  Parses the JSON and converts each `generalDiagnostics` entry whose `file`
  refers to `document_path` into an LSP diagnostic. Two paths match when
  `os.path.normcase(os.path.realpath(p))` is equal for both, which handles
  symlinks and case-insensitive filesystems. Raises `ValueError` if `stdout` is not valid JSON.
- `error_diagnostic(message) -> dict`
  Builds the single "something went wrong" diagnostic described under error
  handling.
- `pylsp_settings(config)` hook — returns the defaults above.
- `pylsp_lint(config, workspace, document, is_saved)` hook — orchestrates
  caching, running, and error handling.

Module-level state: `last_diagnostics: dict[str, list[dict]]`, keyed by
`document.path`, as in pylsp-mypy. Logging uses
`logging.getLogger(__name__)`.

### Diagnostic conversion

| pyright field | LSP diagnostic field |
|---|---|
| `range` | `range`, copied unchanged |
| `message` | `message` |
| `severity`: `error` / `warning` / `information` | `severity`: 1 / 2 / 3 (an unknown value logs a warning and maps to 1) |
| `rule` (when present) | `code` (left out when absent) |
| — | `source = "pyright"` |

## Data flow

```
pylsp_lint(config, workspace, document, is_saved)
  settings = config.plugin_settings("pyright")
  if not is_saved and document.path in last_diagnostics:
      return last_diagnostics[document.path]          # stale positions accepted
  cmd = build_command(settings.get("executable") or "pyright", document.path)
  try:
      code, out, err = run_pyright(cmd, cwd=workspace.root_path)
  except FileNotFoundError:
      diags = [error_diagnostic("pyright executable ... not found ...")]
  else:
      if code >= 2:
          diags = [error_diagnostic(err or out)]
      else:
          try:    diags = parse_output(out, document.path)
          except ValueError:
                  diags = [error_diagnostic("could not parse pyright output: ...")]
  last_diagnostics[document.path] = diags
  return diags
```

Pyright runs with the workspace root as its working directory, so
`pyrightconfig.json` and `[tool.pyright]` in `pyproject.toml` apply exactly as
they do when running `pyright` in a terminal there.

Known limitation: between saves, cached diagnostics keep their old positions
and can drift as the user edits. pylsp-mypy has the same limitation in
non-live mode.

## Error handling

Each failure produces **one** diagnostic: `range` from line 0, character 0 to
line 0, character 1000 (clients clip to line length), `source = "pyright"`,
severity Error (1). The same message is also logged.

| Situation | Message |
|---|---|
| Executable not found (`FileNotFoundError`) | `pyright executable '<x>' not found; install pyright or set pylsp.plugins.pyright.executable` |
| Exit code ≥ 2 | pyright's stderr, or stdout if stderr is empty |
| stdout is not valid JSON | `could not parse pyright output: ` + the first 500 characters of stdout |

There is no subprocess timeout (same as pylsp-mypy). Error diagnostics are
cached like normal results, so they stay visible until the next save.

## Packaging

- `requires-python = ">=3.9"` (pylsp's own minimum), so the plugin installs
  into older project venvs. Code uses `from __future__ import annotations` so
  modern type hints work on 3.9.
- `dependencies = ["python-lsp-server"]`.
- Optional extra: `pyright = ["pyright"]`, which installs the PyPI pyright
  wrapper (it downloads Node and pyright on first run). Without the extra, the
  user provides pyright themselves (npm, pipx, …) on PATH or through the
  `executable` setting.
- Dev dependency group: `pytest`, `pyright`.
- README: installation (with and without the extra), settings, and the
  save-only behaviour.

## Testing

pytest, in `tests/test_plugin.py`.

1. **`parse_output` unit tests** using pyright JSON captured from a real run:
   the severity mapping for all three levels, `rule` → `code`, no `code` when
   `rule` is absent, entries for other files filtered out, ranges unchanged,
   an empty `generalDiagnostics` giving `[]`, and invalid JSON raising
   `ValueError`.
2. **`pylsp_lint` tests** with `run_pyright`/`subprocess.run` mocked, using a
   real pylsp `Workspace`/`Document` and `Config` for a temporary directory:
   - the command is `[executable, "--outputjson", path]` and the working
     directory is the workspace root; a custom `executable` setting is
     respected;
   - an unsaved lint with a cached result returns the cache without running
     pyright;
   - an unsaved lint with nothing cached runs pyright;
   - a saved lint always runs pyright and updates the cache;
   - `FileNotFoundError`, exit code ≥ 2 (with and without stderr), and
     non-JSON output each produce the single error diagnostic;
   - exit code 1 with diagnostics is treated as success.
3. **End-to-end test**: run `pylsp_lint` with the real `pyright` on a
   temporary file containing a known type error and check the resulting
   diagnostic. Skipped when `pyright` is not on PATH.
