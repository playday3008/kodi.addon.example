from stubs import insert_imports


def test_inserts_after_docstring() -> None:
    text = '"""Mod doc."""\n\ndef f() -> xbmcgui.ListItem: ...\n'
    result: str = insert_imports(text, ["xbmc", "xbmcgui"])

    assert result.startswith('"""Mod doc."""\n')
    assert "import xbmcgui\n" in result


def test_no_docstring_prepends() -> None:
    text = "def f() -> xbmc.Monitor: ...\n"

    assert insert_imports(text, ["xbmc"]).startswith("import xbmc\n")


def test_untouched_when_nothing_referenced() -> None:
    text = "def f() -> int: ...\n"

    assert insert_imports(text, ["xbmc", "xbmcgui"]) == text


def test_only_referenced_modules_added() -> None:
    text = "def f() -> xbmcvfs.File: ...\n"
    result: str = insert_imports(text, ["xbmc", "xbmcvfs"])

    assert "import xbmcvfs\n" in result
    assert "import xbmc\n" not in result
