import zipfile
from pathlib import Path

import pytest

from build import NEWS_LIMIT, check_version, format_news, stamp_addon_xml, strip_xsi, write_zip


@pytest.mark.parametrize("version", ["1.0.0", "1.2", "1.2.3.4.5.6", "1.2.3~beta2", "1.0.0+matrix.1"])
def test_check_version_accepts_kodi_versions(version: str) -> None:
    assert check_version(version) == version


@pytest.mark.parametrize("version", ["1", "1.0.0-beta", "1.0.0-rc.1", "v1.0.0", "1.0.0 "])
def test_check_version_rejects_non_kodi_versions(version: str) -> None:
    with pytest.raises(SystemExit, match="not a valid Kodi add-on version"):
        check_version(version)


def test_format_news_header_and_bullets() -> None:
    news: str = format_news("1.2.0", "2026-07-13", ["fix crash (abc1234)", "add tests (def5678)"])

    assert news == "v1.2.0 (2026-07-13)\n- fix crash (abc1234)\n- add tests (def5678)"


def test_format_news_no_subjects() -> None:
    assert format_news("1.2.0", "2026-07-13", []) == "v1.2.0 (2026-07-13)"


def test_format_news_truncates_at_limit() -> None:
    news: str = format_news("1.0.0", "2026-07-13", ["x" * 100] * 50)

    assert len(news) <= NEWS_LIMIT
    assert news.startswith("v1.0.0 (2026-07-13)")


ADDON_XML = """<?xml version="1.0" encoding="UTF-8"?>
<addon xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
  xsi:noNamespaceSchemaLocation="../types/xml/addon.xsd"
  id="script.test" name="T" version="%VERSION%" provider-name="p">
  <extension point="xbmc.addon.metadata"><news>%NEWS%</news></extension>
</addon>
"""


def test_stamp_replaces_placeholders_and_escapes(tmp_path: Path) -> None:
    xml: Path = tmp_path / "addon.xml"
    xml.write_text(ADDON_XML)
    stamp_addon_xml(xml, "1.2.0", "v1.2.0\n- a & b")
    text: str = xml.read_text()

    assert 'version="1.2.0"' in text
    assert "a &amp; b" in text
    assert "%VERSION%" not in text
    assert "%NEWS%" not in text


def test_stamp_missing_placeholder_exits(tmp_path: Path) -> None:
    xml: Path = tmp_path / "addon.xml"
    xml.write_text(ADDON_XML.replace("%NEWS%", "none"))

    with pytest.raises(SystemExit, match="%NEWS%"):
        stamp_addon_xml(xml, "1.2.0", "news")


def test_strip_xsi_removes_schema_hint(tmp_path: Path) -> None:
    xml: Path = tmp_path / "settings.xml"
    xml.write_text(
        '<settings xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
        ' xsi:noNamespaceSchemaLocation="x.xsd" version="1"/>'
    )
    strip_xsi(xml)
    text: str = xml.read_text()

    assert "xsi" not in text
    assert 'version="1"' in text


def test_strip_xsi_leaves_plain_xml_alone(tmp_path: Path) -> None:
    xml: Path = tmp_path / "plain.xml"
    xml.write_text("<a><b/></a>")
    strip_xsi(xml)

    assert xml.read_text() == "<a><b/></a>"


def make_tree(root: Path) -> None:
    (root / "sub").mkdir(parents=True)
    (root / "addon.xml").write_text("<addon/>")
    (root / "sub" / "data.txt").write_text("data")


def test_write_zip_is_deterministic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1000000000")
    tree: Path = tmp_path / "tree"
    make_tree(tree)
    a, b = tmp_path / "a.zip", tmp_path / "b.zip"
    write_zip(a, tree, "my.addon")
    write_zip(b, tree, "my.addon")

    assert a.read_bytes() == b.read_bytes()


def test_write_zip_layout_and_order(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1000000000")
    tree: Path = tmp_path / "tree"
    make_tree(tree)
    archive: Path = tmp_path / "a.zip"
    write_zip(archive, tree, "my.addon")
    with zipfile.ZipFile(archive) as zf:
        names: list[str] = zf.namelist()

    assert names == sorted(names)
    assert "my.addon/addon.xml" in names
    assert "my.addon/sub/data.txt" in names


def test_write_zip_honors_source_date_epoch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "946684800")  # 2000-01-01T00:00:00Z
    tree: Path = tmp_path / "tree"
    make_tree(tree)
    archive: Path = tmp_path / "a.zip"
    write_zip(archive, tree, "my.addon")

    with zipfile.ZipFile(archive) as zf:
        assert all(i.date_time == (2000, 1, 1, 0, 0, 0) for i in zf.infolist())


def test_write_zip_rejects_symlink(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1000000000")
    tree: Path = tmp_path / "tree"
    make_tree(tree)
    (tree / "link.txt").symlink_to(tree / "addon.xml")

    with pytest.raises(SystemExit, match="non-regular"):
        write_zip(tmp_path / "a.zip", tree, "my.addon")
