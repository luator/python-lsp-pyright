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
