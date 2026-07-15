"""
Regenerate Kodi API stubs into ./types/python.

Use stubgen (mypy) and then inserts the cross-module imports that stubgen drops:
kodistubs annotates foreign types as strings ("xbmcgui.ListItem"),
so the generated stubs reference sibling modules without importing them.
"""

import ast
import re
import subprocess
from pathlib import Path

MODULES: list[str] = [
    "xbmc",
    "xbmcaddon",
    "xbmcdrm",
    "xbmcgui",
    "xbmcplugin",
    "xbmcvfs",
]
OUT = Path("types/python")


def insert_imports(text: str, modules: list[str]) -> str:
    """
    Add imports for the given modules where text references them.

    The import block lands after the module docstring, if any,
    so the docstring keeps being recognized as one.
    """

    needed: list[str] = [m for m in modules if re.search(rf"\b{m}\.", text)]
    if not needed:
        return text
    imports: str = "".join(f"import {module}\n" for module in needed)

    body: list[ast.stmt] = ast.parse(text).body
    has_docstring: bool = (
        bool(body)
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    )

    if has_docstring:
        end: int = body[0].end_lineno or 0
        lines: list[str] = text.splitlines(keepends=True)
        return "".join(lines[:end]) + "\n" + imports + "".join(lines[end:])

    return imports + "\n" + text


def main() -> None:
    args: list[str] = [arg for module in MODULES for arg in ("-m", module)]
    subprocess.run(["stubgen", "--include-docstrings", "-o", str(OUT), *args], check=True)

    for path in OUT.glob("*.pyi"):
        text: str = path.read_text()
        updated: str = insert_imports(text, [m for m in MODULES if m != path.stem])
        if updated != text:
            path.write_text(updated)
            print(f"Added imports to {path.name}")


if __name__ == "__main__":
    main()
