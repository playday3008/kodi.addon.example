"""
Generate a Kodi repository tree in ./build/repo from the addon zips in ./build.

Every version per add-on id lands in addons.xml (newest first), so Kodi's
version picker can install or downgrade to any retained zip. Each zip gets a
.sha256 sidecar (verified via <hashes>sha256</hashes>) and addons.xml gets
addons.xml.sha256 (verified via <checksum verify="sha256">).

Layout (served via GitHub Pages):
.
├── addons.xml
├── addons.xml.sha256
├── <id1>
│   ├── <id1>-<version>.zip
│   ├── <id1>-<version>.zip.sha256
│   ├── icon.png
│   ├── fanart.jpg
│   └── resources/...      (declared <assets>)
├── <id2>
│   └── ...
└── ...

Reference: https://kodi.wiki/view/Add-on_repositories
"""

import hashlib
import re
import shutil
import zipfile
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree

from build import strip_xsi, write_zip

# Conventional artwork staged when present; declared <assets> are mandatory
LEGACY_ASSETS: tuple[str, str] = ("icon.png", "fanart.jpg")
XML_DECL: re.Pattern[str] = re.compile(r"^<\?xml[^>]*\?>\s*")


CharKey = tuple[int, str]
RunKey = tuple[CharKey, ...]
SuffixKey = tuple[tuple[RunKey, int], ...]

SUFFIX_RUNS: re.Pattern[str] = re.compile(r"(\D*)(\d*)")


def _char_key(char: str) -> CharKey:
    """Debian character order: '~' before end-of-run, letters before non-letters."""

    if char == "~":
        return (-1, "")
    if char.isalpha():
        return (1, char)
    return (2, char)


def _run_key(run: str) -> RunKey:
    # The (0, "") terminator sorts after '~' but before real characters, so
    # 'a' < 'ab' (prefix ends first) while 'a~' < 'a' (tilde beats ending).
    return (*tuple(_char_key(char) for char in run), (0, ""))


def version_key(version: str) -> SuffixKey:
    """
    Sort key matching Kodi's Debian-style ordering (AddonVersion.cpp
    CompareComponent) for our regex-conforming versions: the whole version
    as alternating non-digit/digit runs - digit runs compare numerically,
    '~' sorts before everything (end-of-string included), letters before
    non-letters ('.' is just another non-digit). The regex is only a
    validity gate.
    """

    if not re.match(r"\d+(?:\.\d+){1,5}", version):
        raise SystemExit(f"unparsable addon version: {version!r}")

    runs: list[tuple[RunKey, int]] = []
    for nondigit, digit in SUFFIX_RUNS.findall(version):
        if nondigit or digit:
            runs.append((_run_key(nondigit), int(digit or "0")))
    runs.append((_run_key(""), 0))  # end sentinel: beats a trailing '~' run

    return tuple(runs)


def addon_meta(zip_path: Path) -> tuple[str, str, str]:
    """
    (id, version, addon.xml text) from a built zip (<id>/addon.xml entry).
    """

    with zipfile.ZipFile(zip_path) as zf:
        names: list[str] = [n for n in zf.namelist() if n.count("/") == 1 and n.endswith("/addon.xml")]
        if len(names) != 1:
            raise SystemExit(f"{zip_path}: expected exactly one <id>/addon.xml, found {names}")
        text: str = zf.read(names[0]).decode()

    try:
        root: ElementTree.Element[str] = ElementTree.fromstring(text)
    except ElementTree.ParseError as error:
        raise SystemExit(f"{zip_path}: invalid addon.xml: {error}") from error

    addon_id: str | None = root.get("id")
    version: str | None = root.get("version")
    if root.tag != "addon" or not addon_id or not version:
        raise SystemExit(f"{zip_path}: addon.xml lacks id/version")

    return addon_id, version, text


def declared_assets(text: str) -> list[str]:
    """
    Asset paths declared under <extension point="xbmc.addon.metadata"><assets>.
    """

    root: ElementTree.Element[str] = ElementTree.fromstring(text)
    paths: list[str] = []
    for extension in root.iterfind('extension[@point="xbmc.addon.metadata"]'):
        for element in extension.iterfind("assets/*"):
            asset: str = (element.text or "").strip()
            if not asset:
                continue
            if asset.startswith("/") or ".." in PurePosixPath(asset).parts:
                raise SystemExit(f"unsafe asset path in addon.xml: {asset!r}")
            paths.append(asset)

    return paths


def stage_assets(zip_path: Path, addon_id: str, text: str, target: Path) -> None:
    """
    Copy artwork out of the zip so Kodi can show it pre-install (asset paths
    resolve against <datadir>/<id>/, never inside the zip): the conventional
    icon/fanart pair when present, plus every declared <assets> path -
    declared art that cannot render is a packaging bug, so missing is fatal.
    """

    with zipfile.ZipFile(zip_path) as zf:
        names: frozenset[str] = frozenset(zf.namelist())
        for asset in LEGACY_ASSETS:
            if (entry := f"{addon_id}/{asset}") in names:
                (target / asset).write_bytes(zf.read(entry))

        for asset in declared_assets(text):
            entry = f"{addon_id}/{asset}"
            if entry not in names:
                raise SystemExit(f"{zip_path}: declared asset missing from zip: {asset}")
            dest: Path = target / asset
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(zf.read(entry))


def build_repository_addon(build_dir: Path) -> Path:
    """
    Stage repo/ verbatim (its version is hand-managed - no %VERSION% stamping),
    strip the dev-only xsi attrs, zip deterministically.
    """

    root: ElementTree.Element[str] = ElementTree.parse("repo/addon.xml").getroot()

    addon_id: str | None = root.get("id")
    version: str | None = root.get("version")
    if not addon_id or not version:
        raise SystemExit("repo/addon.xml: missing id/version")

    staging: Path = build_dir / addon_id
    shutil.rmtree(staging, ignore_errors=True)
    shutil.copytree("repo", staging)

    for xml in staging.rglob("*.xml"):
        strip_xsi(xml)

    archive: Path = build_dir / f"{addon_id}-{version}.zip"
    write_zip(archive, staging, addon_id)

    return archive


def write_sha256(path: Path) -> None:
    """
    <name>.sha256 sidecar next to path. Kodi fetches '<url>.sha256' when the
    repository declares <hashes>sha256</hashes> and truncates the content at
    the first whitespace, so a bare hash + newline is compatible.
    """

    digest: str = hashlib.sha256(path.read_bytes()).hexdigest()
    path.with_name(f"{path.name}.sha256").write_text(f"{digest}\n")


def generate(zips: list[Path], out: Path) -> None:
    """
    Build the repository tree in out/ from the given addon zips.

    Every version of every add-on is published in addons.xml (newest first
    per id) - Kodi discovers installable versions only from addons.xml, so
    this is what makes the retained old zips reachable for downgrades.
    """

    if not zips:
        raise SystemExit("no addon zips found in build/ - run 'poe build' first")

    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)

    texts: dict[tuple[str, str], str] = {}  # (id, version) -> addon.xml
    newest: dict[str, tuple[str, str, Path]] = {}  # id -> (version, addon.xml, zip)
    for zip_path in zips:
        addon_id, version, text = addon_meta(zip_path)

        dest: Path = out / addon_id / f"{addon_id}-{version}.zip"
        dest.parent.mkdir(exist_ok=True)

        if dest.exists() and dest.read_bytes() != zip_path.read_bytes():
            raise SystemExit(f"conflicting zips for {addon_id} {version}")

        shutil.copy2(zip_path, dest)
        write_sha256(dest)

        texts[(addon_id, version)] = text
        if addon_id not in newest or version_key(version) > version_key(newest[addon_id][0]):
            newest[addon_id] = (version, text, zip_path)

    for addon_id in sorted(newest):
        _, text, zip_path = newest[addon_id]
        stage_assets(zip_path, addon_id, text, out / addon_id)

    # id ascending, version descending - deterministic, newest first per id
    ordered: list[tuple[str, str]] = sorted(texts, key=lambda key: version_key(key[1]), reverse=True)
    ordered.sort(key=lambda key: key[0])
    documents: list[str] = [XML_DECL.sub("", texts[key]).strip() for key in ordered]

    addons_xml: str = '<?xml version="1.0" encoding="UTF-8"?>\n<addons>\n' + "\n".join(documents) + "\n</addons>\n"
    (out / "addons.xml").write_text(addons_xml)
    write_sha256(out / "addons.xml")


def main() -> None:
    build_dir = Path("build")
    build_repository_addon(build_dir)

    # versioned zips only ("<id>-<version>.zip"); ignores stale unversioned ones
    zips: list[Path] = sorted(build_dir.glob("*-*.zip"))
    generate(zips, build_dir / "repo")

    print(f"Repository generated in {build_dir / 'repo'} ({len(zips)} zip(s))")


if __name__ == "__main__":
    main()
