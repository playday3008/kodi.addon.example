"""
Unit tests for the XSD 1.1 -> 1.0 transform in scripts/xsd10.py.

Each test builds a tiny 1.1 schema, runs generate(), and checks the emitted
1.0 text - and, where meaningful, that xmlschema compiles it as XSD 1.0 and
accepts documents the 1.1 original accepts (the laxness invariant).
"""

from pathlib import Path

import pytest
import xmlschema

from xsd10 import OUT, SCHEMAS, SRC, generate

WRAPPER = """<?xml version="1.0" encoding="UTF-8"?>
<xs:schema xmlns:xs="http://www.w3.org/2001/XMLSchema"
           xmlns:vc="http://www.w3.org/2007/XMLSchema-versioning"
           vc:minVersion="1.1">
{body}
</xs:schema>
"""


def make_schema(tmp_path: Path, body: str) -> Path:
    path: Path = tmp_path / "schema.xsd"
    path.write_text(WRAPPER.format(body=body))
    return path


MERGE_BODY = """
  <xs:complexType name="alphaType">
    <xs:choice maxOccurs="unbounded">
      <xs:element name="shared" type="xs:string" />
      <xs:element name="alphaOnly" type="xs:string" />
    </xs:choice>
    <xs:attribute name="kind" type="xs:string" use="required" />
    <xs:assert test="shared" />
  </xs:complexType>
  <xs:complexType name="betaType">
    <xs:sequence>
      <xs:element name="shared" type="xs:string" />
      <xs:element name="betaOnly" type="xs:string" />
    </xs:sequence>
    <xs:attribute name="beta" type="xs:boolean" />
  </xs:complexType>
  <xs:element name="thing">
    <xs:alternative test="@kind = 'alpha'" type="alphaType" />
    <xs:alternative test="@kind = 'beta'" type="betaType" />
    <xs:alternative type="xs:error" />
  </xs:element>
"""


def test_merge_strips_xsd11_constructs(tmp_path: Path) -> None:
    out: str = generate(make_schema(tmp_path, MERGE_BODY))

    assert "GENERATED" in out
    assert "xs:assert" not in out
    assert "xs:alternative" not in out
    assert "XMLSchema-versioning" not in out
    assert "xs:error" not in out


def test_merged_type_is_lax_union(tmp_path: Path) -> None:
    out: str = generate(make_schema(tmp_path, MERGE_BODY))
    schema = xmlschema.XMLSchema10(out)

    # Any order, any mixture of both variants' children; kind no longer required.
    doc = "<thing><betaOnly>x</betaOnly><shared>y</shared><alphaOnly>z</alphaOnly></thing>"
    assert schema.is_valid(doc)
    assert schema.is_valid('<thing kind="alpha" beta="true"><shared>y</shared></thing>')


CONFLICT_BODY = """
  <xs:complexType name="numericBox">
    <xs:choice maxOccurs="unbounded">
      <xs:element name="minimum" type="xs:decimal" />
    </xs:choice>
  </xs:complexType>
  <xs:complexType name="textBox">
    <xs:choice maxOccurs="unbounded">
      <xs:element name="allowempty" type="xs:boolean" />
    </xs:choice>
  </xs:complexType>
  <xs:complexType name="numericVariant">
    <xs:sequence>
      <xs:element name="box" type="numericBox" />
    </xs:sequence>
  </xs:complexType>
  <xs:complexType name="textVariant">
    <xs:sequence>
      <xs:element name="box" type="textBox" />
    </xs:sequence>
  </xs:complexType>
  <xs:element name="thing">
    <xs:alternative test="@kind = 'n'" type="numericVariant" />
    <xs:alternative type="textVariant" />
  </xs:element>
"""


def test_conflicting_named_types_merge_recursively(tmp_path: Path) -> None:
    out: str = generate(make_schema(tmp_path, CONFLICT_BODY))
    schema = xmlschema.XMLSchema10(out)

    assert "merged.box" in out
    doc = "<thing><box><minimum>1</minimum><allowempty>true</allowempty></box></thing>"
    assert schema.is_valid(doc)


WIDEN_BODY = """
  <xs:complexType name="simpleVariant">
    <xs:sequence>
      <xs:element name="field" type="xs:string" />
    </xs:sequence>
    <xs:attribute name="mode" type="xs:string" />
  </xs:complexType>
  <xs:complexType name="enumVariant">
    <xs:sequence>
      <xs:element name="field" type="xs:integer" />
    </xs:sequence>
    <xs:attribute name="mode">
      <xs:simpleType>
        <xs:restriction base="xs:string">
          <xs:enumeration value="a" />
        </xs:restriction>
      </xs:simpleType>
    </xs:attribute>
  </xs:complexType>
  <xs:element name="thing">
    <xs:alternative test="@kind = 's'" type="simpleVariant" />
    <xs:alternative type="enumVariant" />
  </xs:element>
"""


def test_unmergeable_conflicts_widen(tmp_path: Path) -> None:
    out: str = generate(make_schema(tmp_path, WIDEN_BODY))
    schema = xmlschema.XMLSchema10(out)

    # field held xs:string in one variant, xs:integer in the other -> anyType;
    # mode held a plain string vs an enum -> untyped. Both originals must pass.
    assert schema.is_valid('<thing mode="zzz"><field>text</field></thing>')
    assert schema.is_valid('<thing mode="a"><field>7</field></thing>')


WILDCARD_BODY = """
  <xs:complexType name="knownType">
    <xs:sequence>
      <xs:element name="known" type="xs:string" />
    </xs:sequence>
  </xs:complexType>
  <xs:complexType name="wildType">
    <xs:sequence>
      <xs:any processContents="lax" />
    </xs:sequence>
  </xs:complexType>
  <xs:element name="thing">
    <xs:alternative test="@kind = 'k'" type="knownType" />
    <xs:alternative type="wildType" />
  </xs:element>
"""


def test_wildcard_variants_are_skipped(tmp_path: Path) -> None:
    out: str = generate(make_schema(tmp_path, WILDCARD_BODY))

    # The unused wildType passes through (xs:any is legal 1.0), but the merged
    # type on <thing> must not contain the wildcard - that would break UPA.
    merged_part: str = out.split('<xs:element name="thing">')[1]
    assert "xs:any" not in merged_part
    assert "known" in merged_part
    assert xmlschema.XMLSchema10(out).is_valid("<thing><known>x</known></thing>")


def test_unknown_xsd11_construct_aborts(tmp_path: Path) -> None:
    body = '<xs:override schemaLocation="other.xsd" />'

    with pytest.raises(SystemExit, match="override"):
        generate(make_schema(tmp_path, body))


def test_element_with_type_and_alternatives_aborts(tmp_path: Path) -> None:
    body = """
  <xs:complexType name="aType">
    <xs:sequence>
      <xs:element name="x" type="xs:string" />
    </xs:sequence>
  </xs:complexType>
  <xs:element name="thing" type="aType">
    <xs:alternative test="@k = '1'" type="aType" />
  </xs:element>
"""

    with pytest.raises(SystemExit, match="thing"):
        generate(make_schema(tmp_path, body))


ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("name", SCHEMAS)
def test_committed_schemas_are_fresh(name: str) -> None:
    """types/xml/1.0 must match a regeneration - run `uv run poe xsd10` if not."""
    assert (ROOT / OUT / name).read_text() == generate(ROOT / SRC / name)


@pytest.mark.parametrize("name", SCHEMAS)
def test_committed_schemas_compile_as_xsd10(name: str) -> None:
    xmlschema.XMLSchema10(str(ROOT / OUT / name))


@pytest.mark.parametrize("doc", ["addon/addon.xml", "repo/addon.xml"])
def test_addon_xml_valid_under_generated_schema(doc: str) -> None:
    schema = xmlschema.XMLSchema10(str(ROOT / OUT / "addon.xsd"))
    schema.validate(str(ROOT / doc))


def test_settings_xml_valid_under_generated_schema() -> None:
    schema = xmlschema.XMLSchema10(str(ROOT / OUT / "settings.xsd"))
    schema.validate(str(ROOT / "addon" / "resources" / "settings.xml"))
