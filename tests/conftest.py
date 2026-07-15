"""Shared fixtures: the XSD 1.1 schemas (xmlschema is the only validator that does 1.1)."""

from pathlib import Path

import pytest
import xmlschema

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def addon_schema() -> xmlschema.XMLSchema11:
    return xmlschema.XMLSchema11(str(ROOT / "types" / "xml" / "addon.xsd"))


@pytest.fixture(scope="session")
def settings_schema() -> xmlschema.XMLSchema11:
    return xmlschema.XMLSchema11(str(ROOT / "types" / "xml" / "settings.xsd"))
