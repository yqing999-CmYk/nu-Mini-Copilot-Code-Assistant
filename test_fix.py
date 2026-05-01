from codeassist.commands.fix import _extract_code_block, _render_diff


# ---------------------------------------------------------------------------
# _extract_code_block
# ---------------------------------------------------------------------------

def test_extracts_python_block():
    response = "Here is the fix:\n\n```python\ndef foo():\n    return 1\n```\n"
    code = _extract_code_block(response)
    assert code == "def foo():\n    return 1\n"


def test_extracts_plain_block():
    response = "Fixed:\n\n```\nx = 1\n```"
    code = _extract_code_block(response)
    assert code == "x = 1\n"


def test_extracts_first_block_when_multiple():
    response = "```python\nfirst\n```\n\n```python\nsecond\n```"
    code = _extract_code_block(response)
    assert code == "first\n"


def test_returns_none_when_no_block():
    assert _extract_code_block("No code here at all.") is None


def test_returns_none_on_empty_string():
    assert _extract_code_block("") is None


def test_extracts_multiline_block():
    response = "```python\ndef a():\n    x = 1\n    return x\n```"
    code = _extract_code_block(response)
    assert "def a():" in code
    assert "return x" in code


# ---------------------------------------------------------------------------
# _render_diff
# ---------------------------------------------------------------------------

def test_diff_shows_added_line():
    orig = "def foo():\n    pass\n"
    fixed = "def foo() -> None:\n    pass\n"
    diff = _render_diff(orig, fixed, "sample.py")
    assert "-def foo():" in diff
    assert "+def foo() -> None:" in diff


def test_diff_shows_file_names():
    diff = _render_diff("a\n", "b\n", "myfile.py")
    assert "a/myfile.py" in diff
    assert "b/myfile.py" in diff


def test_diff_empty_when_identical():
    src = "x = 1\n"
    assert _render_diff(src, src, "f.py") == ""


def test_diff_multiline_change():
    orig = "x = 1\ny = 2\nz = 3\n"
    fixed = "x = 1\ny = 99\nz = 3\n"
    diff = _render_diff(orig, fixed, "f.py")
    assert "-y = 2" in diff
    assert "+y = 99" in diff
