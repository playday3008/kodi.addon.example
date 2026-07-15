import hashlib
import zipfile
from pathlib import Path

import pytest

from build import write_zip
from repo import addon_meta, build_repository_addon, generate, version_key


def make_addon_zip(tmp_path: Path, addon_id: str, version: str) -> Path:
    tree: Path = tmp_path / "trees" / f"{addon_id}-{version}"
    (tree / "resources").mkdir(parents=True)
    (tree / "addon.xml").write_text(
        f'<addon id="{addon_id}" name="T" version="{version}" provider-name="p">'
        '<extension point="xbmc.addon.metadata"><summary lang="en_GB">s</summary>'
        "<assets><icon>icon.png</icon><screenshot>resources/screenshot-01.png</screenshot></assets>"
        "</extension></addon>"
    )
    (tree / "icon.png").write_bytes(b"\x89PNG fake")
    (tree / "resources" / "screenshot-01.png").write_bytes(b"\x89PNG shot")
    archive: Path = tmp_path / f"{addon_id}-{version}.zip"
    write_zip(archive, tree, addon_id)
    return archive


@pytest.mark.parametrize(
    ("lower", "higher"),
    [
        ("1.9.0", "1.10.0"),
        ("1.0.0~beta2", "1.0.0"),
        ("1.0.0", "1.0.0+matrix.1"),
        ("1.0.0~alpha", "1.0.0~beta"),
        # Debian/Kodi CompareComponent semantics (AddonVersion.cpp):
        ("1.0.0~beta9", "1.0.0~beta10"),  # digit runs compare numerically
        ("1.0.0+build.9", "1.0.0+build.10"),
        ("1.0.0a~1", "1.0.0a"),  # '~' sorts before end-of-string at any position
        ("1.0.0~~", "1.0.0~"),
        # whole-string run encoding: '_' sorts above '.' in Debian order,
        # so a shorter dotted prefix with a '_' suffix outranks more components
        ("7.3.12.7", "7.3_b0"),
        ("3.10.11.2", "3.10.11__11.10"),
        ("1.0.0a1b2", "1.0.0a1b10"),  # digit runs inside suffixes stay numeric
    ],
)
def test_version_key_ordering(lower: str, higher: str) -> None:
    assert version_key(lower) < version_key(higher)


def test_version_key_rejects_garbage() -> None:
    with pytest.raises(SystemExit, match="unparsable"):
        version_key("not-a-version")


def test_addon_meta_reads_id_and_version(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1000000000")
    archive: Path = make_addon_zip(tmp_path, "script.test", "1.2.0")
    addon_id, version, text = addon_meta(archive)

    assert (addon_id, version) == ("script.test", "1.2.0")
    assert text.startswith("<addon")


def test_generate_tree_publishes_all_versions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1000000000")
    zips: list[Path] = [
        make_addon_zip(tmp_path, "script.test", "1.0.0"),
        make_addon_zip(tmp_path, "script.test", "1.1.0"),
    ]
    out: Path = tmp_path / "repo"
    generate(zips, out)

    assert (out / "script.test" / "script.test-1.0.0.zip").is_file()
    assert (out / "script.test" / "script.test-1.1.0.zip").is_file()
    assert (out / "script.test" / "icon.png").is_file()

    addons_xml: str = (out / "addons.xml").read_text()
    assert addons_xml.count("<addon ") == 2  # every version is installable (downgrades)
    assert addons_xml.index('version="1.1.0"') < addons_xml.index('version="1.0.0"')  # newest first
    assert "<?xml" not in addons_xml.split("\n", 1)[1]  # inner decls stripped


def test_generate_writes_sha256_sidecars(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1000000000")
    zips: list[Path] = [make_addon_zip(tmp_path, "script.test", "1.0.0")]
    out: Path = tmp_path / "repo"
    generate(zips, out)

    manifest_hash: str = hashlib.sha256((out / "addons.xml").read_bytes()).hexdigest()
    assert (out / "addons.xml.sha256").read_text() == f"{manifest_hash}\n"
    assert not (out / "addons.xml.md5").exists()

    dest: Path = out / "script.test" / "script.test-1.0.0.zip"
    zip_hash: str = hashlib.sha256(dest.read_bytes()).hexdigest()
    assert (out / "script.test" / "script.test-1.0.0.zip.sha256").read_text() == f"{zip_hash}\n"


def test_generate_is_deterministic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1000000000")
    zips: list[Path] = [make_addon_zip(tmp_path, "script.test", "1.0.0")]
    out1, out2 = tmp_path / "repo1", tmp_path / "repo2"
    generate(zips, out1)
    generate(zips, out2)

    for name in ("addons.xml", "addons.xml.sha256"):
        assert (out1 / name).read_bytes() == (out2 / name).read_bytes()
    sidecar = Path("script.test") / "script.test-1.0.0.zip.sha256"
    assert (out1 / sidecar).read_bytes() == (out2 / sidecar).read_bytes()


def test_generate_empty_zip_list_exits(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="no addon zips"):
        generate([], tmp_path / "repo")


def test_generate_conflicting_duplicate_exits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1000000000")
    a = make_addon_zip(tmp_path, "script.test", "1.0.0")
    # same id+version, different content: copy the zip and add an extra entry
    # (appending raw bytes instead would corrupt the end-of-central-directory)
    conflicting: Path = tmp_path / "other" / "script.test-1.0.0.zip"
    conflicting.parent.mkdir()
    conflicting.write_bytes(a.read_bytes())
    with zipfile.ZipFile(conflicting, "a") as zf:
        zf.writestr("script.test/extra.txt", "x")

    with pytest.raises(SystemExit, match="conflicting"):
        generate([a, conflicting], tmp_path / "repo")


def test_addon_meta_rejects_zip_without_addon_xml(tmp_path: Path) -> None:
    archive: Path = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("readme.txt", "hi")

    with pytest.raises(SystemExit, match=r"addon\.xml"):
        addon_meta(archive)


def test_addon_meta_rejects_invalid_xml(tmp_path: Path) -> None:
    archive: Path = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("script.test/addon.xml", "﻿<addon garbage")

    with pytest.raises(SystemExit, match=r"invalid addon\.xml"):
        addon_meta(archive)


def test_build_repository_addon_stages_verbatim(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1000000000")
    archive: Path = build_repository_addon(tmp_path)
    assert archive == tmp_path / "repository.example-1.0.0.zip"
    with zipfile.ZipFile(archive) as zf:
        text: str = zf.read("repository.example/addon.xml").decode()

    assert 'version="1.0.0"' in text  # hand-managed, not stamped
    assert "%VERSION%" not in text
    assert "<dir>" in text  # flat form was removed in Kodi v20
    assert 'verify="sha256"' in text
    assert "xsi" not in text  # dev-only schema hint stripped


def test_generate_multiple_ids_sorted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1000000000")
    zips: list[Path] = [
        make_addon_zip(tmp_path, "script.zzz", "1.0.0"),
        make_addon_zip(tmp_path, "script.aaa", "2.0.0"),
    ]
    out: Path = tmp_path / "repo"
    generate(zips, out)
    addons_xml: str = (out / "addons.xml").read_text()

    assert addons_xml.count("<addon ") == 2
    assert addons_xml.index('id="script.aaa"') < addons_xml.index('id="script.zzz"')
    assert (out / "script.aaa" / "script.aaa-2.0.0.zip").is_file()
    assert (out / "script.zzz" / "script.zzz-1.0.0.zip").is_file()


def test_generate_stages_declared_assets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1000000000")
    zips: list[Path] = [make_addon_zip(tmp_path, "script.test", "1.0.0")]
    out: Path = tmp_path / "repo"
    generate(zips, out)

    # Kodi resolves <assets> paths against <datadir>/<id>/ - never inside zips
    assert (out / "script.test" / "icon.png").is_file()
    assert (out / "script.test" / "resources" / "screenshot-01.png").is_file()


def test_generate_missing_declared_asset_exits(tmp_path: Path) -> None:
    archive: Path = tmp_path / "script.bad-1.0.0.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr(
            "script.bad/addon.xml",
            '<addon id="script.bad" name="T" version="1.0.0" provider-name="p">'
            '<extension point="xbmc.addon.metadata">'
            "<assets><banner>resources/banner.jpg</banner></assets>"
            "</extension></addon>",
        )

    with pytest.raises(SystemExit, match="declared asset missing"):
        generate([archive], tmp_path / "repo")
