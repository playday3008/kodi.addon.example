import pytest

from src.greeting import build_greeting


@pytest.mark.parametrize(
    ("style", "expected"),
    [
        ("classic", "Hello, Ada."),
        ("formal", "Good day, Ada."),
        ("pirate", "Ahoy, Ada."),
        # Stale stored value after an options change must not crash the dialog
        ("no-such-style", "Hello, Ada."),
    ],
)
def test_styles(style: str, expected: str) -> None:
    assert build_greeting("Ada", style, 1, excited=False) == [expected]


def test_excited_uses_exclamation_mark() -> None:
    assert build_greeting("Ada", "classic", 1, excited=True) == ["Hello, Ada!"]


def test_count_repeats_lines() -> None:
    assert build_greeting("Ada", "classic", 3, excited=False) == ["Hello, Ada."] * 3


@pytest.mark.parametrize("count", [0, -5])
def test_count_clamped_to_one(count: int) -> None:
    assert len(build_greeting("Ada", "classic", count, excited=False)) == 1


@pytest.mark.parametrize("name", ["", "   "])
def test_blank_name_falls_back_to_world(name: str) -> None:
    assert build_greeting(name, "classic", 1, excited=False) == ["Hello, World."]
