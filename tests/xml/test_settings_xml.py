"""
Validate settings.xml documents against types/xml/settings.xsd.
"""

from pathlib import Path

import pytest
import xmlschema

ROOT = Path(__file__).resolve().parents[2]


def settings_doc(setting: str) -> str:
    return (
        '<settings version="1"><section id="script.test">'
        '<category id="general" label="32100"><group id="1" label="32101">'
        f"{setting}</group></category></section></settings>"
    )


def test_settings_xml_is_valid(settings_schema: xmlschema.XMLSchema11) -> None:
    settings_schema.validate(str(ROOT / "addon" / "resources" / "settings.xml"))


def test_minimal_boolean_setting(settings_schema: xmlschema.XMLSchema11) -> None:
    setting = (
        '<setting id="flag" type="boolean" label="32102">'
        "<level>0</level><default>true</default>"
        '<control type="toggle"/></setting>'
    )
    assert settings_schema.is_valid(settings_doc(setting))


def test_unknown_setting_type_rejected(settings_schema: xmlschema.XMLSchema11) -> None:
    setting = '<setting id="x" type="whatever" label="32102"><level>0</level><control type="toggle"/></setting>'
    assert not settings_schema.is_valid(settings_doc(setting))


def test_path_setting_requires_button_control(settings_schema: xmlschema.XMLSchema11) -> None:
    # Kodi hard-errors on this pairing: CAddonSettings enforces button[path|file|image]
    setting = (
        '<setting id="p" type="path" label="32102">'
        "<level>0</level><default></default>"
        '<control type="edit" format="string"/></setting>'
    )
    assert not settings_schema.is_valid(settings_doc(setting))


def test_addon_setting_requires_addontype(settings_schema: xmlschema.XMLSchema11) -> None:
    setting = (
        '<setting id="a" type="addon" label="32102">'
        "<level>0</level><default></default>"
        '<control type="button" format="addon"/></setting>'
    )
    assert not settings_schema.is_valid(settings_doc(setting))


def test_setting_requires_control_unless_internal(
    settings_schema: xmlschema.XMLSchema11,
) -> None:
    no_control = '<setting id="x" type="boolean" label="32102"><level>0</level></setting>'
    internal = '<setting id="x" type="boolean" label="32102"><level>4</level></setting>'
    assert not settings_schema.is_valid(settings_doc(no_control))
    assert settings_schema.is_valid(settings_doc(internal))


def test_list_type_and_dependency(settings_schema: xmlschema.XMLSchema11) -> None:
    setting = (
        '<setting id="tags" type="list[string]" label="32102">'
        "<level>0</level><default>a|b</default>"
        "<constraints><delimiter>|</delimiter></constraints>"
        '<control type="list" format="string"><multiselect>true</multiselect>'
        "<heading>32102</heading></control>"
        '<dependencies><dependency type="visible" setting="flag">true</dependency>'
        "</dependencies></setting>"
    )
    assert settings_schema.is_valid(settings_doc(setting))


# --- pairing matrix: W-level pairings are schema-rejected too ---


@pytest.mark.parametrize(
    "setting",
    [
        # boolean must pair with toggle, not slider
        '<setting id="x" type="boolean" label="32102"><level>0</level>'
        '<control type="slider" format="integer"/></setting>',
        # action must pair with button[action], not edit
        '<setting id="x" type="action" label="32102"><level>0</level><control type="edit" format="string"/></setting>',
        # string must not pair with toggle
        '<setting id="x" type="string" label="32102"><level>0</level>'
        '<default></default><control type="toggle"/></setting>',
        # date requires button[date]
        '<setting id="x" type="date" label="32102"><level>0</level>'
        '<default></default><control type="edit" format="string"/></setting>',
        # number: slider[integer] is the wrong format
        '<setting id="x" type="number" label="32102"><level>0</level>'
        '<control type="slider" format="integer"/></setting>',
    ],
)
def test_pairing_matrix_rejects(settings_schema: xmlschema.XMLSchema11, setting: str) -> None:
    assert not settings_schema.is_valid(settings_doc(setting))


def test_colorbutton_on_string_is_valid(settings_schema: xmlschema.XMLSchema11) -> None:
    setting = (
        '<setting id="c" type="string" label="32102"><level>0</level>'
        '<default>FFFFFFFF</default><control type="colorbutton"/></setting>'
    )
    assert settings_schema.is_valid(settings_doc(setting))


def test_time_setting_with_button_time_is_valid(
    settings_schema: xmlschema.XMLSchema11,
) -> None:
    setting = (
        '<setting id="t" type="time" label="32102"><level>0</level>'
        '<default>00:00</default><control type="button" format="time"/></setting>'
    )
    assert settings_schema.is_valid(settings_doc(setting))


# --- Kodi-internal syntax accepted, marked internal in the schema ---


def test_label_control_is_schema_legal(settings_schema: xmlschema.XMLSchema11) -> None:
    # Kodi-internal control; syntax-legal, marked internal in the schema
    setting = (
        '<setting id="x" type="string" label="32102"><level>0</level>'
        '<default></default><control type="label" format="string"/></setting>'
    )
    assert settings_schema.is_valid(settings_doc(setting))


def test_requirement_condition_combination(settings_schema: xmlschema.XMLSchema11) -> None:
    setting = (
        '<setting id="x" type="boolean" label="32102">'
        "<requirement><and><condition>true</condition>"
        "<or><condition>has_web_server</condition><condition>true</condition></or>"
        "</and></requirement>"
        '<level>0</level><control type="toggle"/></setting>'
    )
    assert settings_schema.is_valid(settings_doc(setting))
