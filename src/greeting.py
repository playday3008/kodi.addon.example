"""
Pure greeting logic -- no Kodi imports, unit-testable.
"""

_STYLES: dict[str, str] = {
    "classic": "Hello, {name}",
    "formal": "Good day, {name}",
    "pirate": "Ahoy, {name}",
}


def build_greeting(name: str, style: str, count: int, excited: bool) -> list[str]:
    """
    Build the greeting lines shown in the dialog.

    Unknown styles fall back to classic and count clamps to >= 1: both values
    come straight from stored settings, which can be stale after the options
    change, and the greeting dialog must not crash over them.
    """

    shown: str = name.strip() or "World"
    template: str = _STYLES.get(style, _STYLES["classic"])
    line: str = template.format(name=shown) + ("!" if excited else ".")

    return [line] * max(count, 1)
