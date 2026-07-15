"""
Validate addon.xml documents against types/xml/addon.xsd.
"""

from pathlib import Path

import pytest
import xmlschema

ROOT = Path(__file__).resolve().parents[2]

METADATA_EXT = '<extension point="xbmc.addon.metadata"><summary lang="en_GB">s</summary></extension>'


def addon_doc(version: str = "1.0.0", extra: str = "") -> str:
    return f'<addon id="script.test" name="Test" version="{version}" provider-name="me">{METADATA_EXT}{extra}</addon>'


def test_addon_xml_is_valid(addon_schema: xmlschema.XMLSchema11) -> None:
    # The %VERSION%/%NEWS% placeholders are schema-legal by design
    addon_schema.validate(str(ROOT / "addon" / "addon.xml"))


def test_minimal_addon_is_valid(addon_schema: xmlschema.XMLSchema11) -> None:
    assert addon_schema.is_valid(addon_doc())


@pytest.mark.parametrize("version", ["1.2.3~beta2", "1.0.0+matrix.1", "%VERSION%"])
def test_good_versions(addon_schema: xmlschema.XMLSchema11, version: str) -> None:
    assert addon_schema.is_valid(addon_doc(version=version))


@pytest.mark.parametrize("version", ["1.0.0-rc.1", "1", "v1.0.0", "1.0.0-beta"])
def test_bad_versions_rejected(addon_schema: xmlschema.XMLSchema11, version: str) -> None:
    # SemVer -prerelease parses as a Debian revision in Kodi and sorts ABOVE
    # the release -- reject it outright
    assert not addon_schema.is_valid(addon_doc(version=version))


def test_service_must_not_have_children(addon_schema: xmlschema.XMLSchema11) -> None:
    ext = '<extension point="xbmc.service" library="addon.py"><provides>executable</provides></extension>'
    assert not addon_schema.is_valid(addon_doc(extra=ext))


def test_script_requires_library(addon_schema: xmlschema.XMLSchema11) -> None:
    assert not addon_schema.is_valid(addon_doc(extra='<extension point="xbmc.python.script"/>'))


def test_script_with_library_is_valid(addon_schema: xmlschema.XMLSchema11) -> None:
    ext = '<extension point="xbmc.python.script" library="addon.py"><provides>executable</provides></extension>'
    assert addon_schema.is_valid(addon_doc(extra=ext))


def test_unknown_point_is_permissive(addon_schema: xmlschema.XMLSchema11) -> None:
    ext = '<extension point="my.custom.point"><anything attr="x">y</anything></extension>'
    assert addon_schema.is_valid(addon_doc(extra=ext))


def test_repo_addon_xml_is_valid(addon_schema: xmlschema.XMLSchema11) -> None:
    # The repository add-on exercises the repositoryExtension content model
    addon_schema.validate(str(ROOT / "repo" / "addon.xml"))


def test_repository_dir_form_is_valid(addon_schema: xmlschema.XMLSchema11) -> None:
    ext = (
        '<extension point="xbmc.addon.repository" name="R"><dir>'
        "<info>http://e/addons.xml</info>"
        '<checksum verify="sha256">http://e/addons.xml.sha256</checksum>'
        "<datadir>http://e/</datadir>"
        "<hashes>sha256</hashes>"
        "</dir></extension>"
    )
    assert addon_schema.is_valid(addon_doc(extra=ext))


def test_repository_flat_form_rejected(addon_schema: xmlschema.XMLSchema11) -> None:
    # Removed in Kodi v20 (Nexus); the v21 runtime only reads <dir> elements
    ext = (
        '<extension point="xbmc.addon.repository" name="R">'
        "<info>http://e/addons.xml</info>"
        "<checksum>http://e/addons.xml.md5</checksum>"
        '<datadir zip="true">http://e/</datadir>'
        "</extension>"
    )
    assert not addon_schema.is_valid(addon_doc(extra=ext))
