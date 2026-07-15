"""
Build an installable Kodi addon zip in ./build.

The version attribute and <news> element in the staged addon.xml are replaced
at build time:
- version comes from pyproject.toml,
- news from the git subjects since the last tag.

Reference: https://kodi.wiki/view/Add-on_structure
"""

import os
import re
import shutil
import subprocess
import time
import tomllib
import zipfile
from pathlib import Path
from xml.etree import ElementTree
from xml.sax.saxutils import escape

NEWS_LIMIT: int = 1500  # addon.xml spec limit for <news>


def addon_id() -> str:
    root: ElementTree.Element[str] = ElementTree.parse("addon/addon.xml").getroot()
    if root.tag != "addon" or not (value := root.get("id")):
        raise SystemExit("addon.xml: missing id attribute on <addon> element")

    return value


# Kodi add-on version format (official repo rule, mirrored in types/xml/addon.xsd);
# Kodi compares Debian-style, so validate the source version before it ships.
VERSION_RE: re.Pattern[str] = re.compile(r"\d+\.\d+(\.\d+){0,4}([+~\w]+(\.\d+)?)?")


def check_version(version: str) -> str:
    if not VERSION_RE.fullmatch(version):
        raise SystemExit(f"pyproject version {version!r} is not a valid Kodi add-on version")

    return version


def project_version() -> str:
    with Path("pyproject.toml").open("rb") as f:
        return check_version(str(tomllib.load(f)["project"]["version"]))


def git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout.strip()


def format_news(version: str, date: str, subjects: list[str]) -> str:
    """
    'vX.Y.Z (date)' plus '- subject' bullets, truncated to NEWS_LIMIT.
    """

    news: str = f"v{version} ({date})"
    for subject in subjects:
        line: str = f"\n- {subject}"
        if len(news) + len(line) > NEWS_LIMIT:
            break
        news += line

    return news


def news_from_git(version: str) -> str:
    """
    format_news over the commit subjects since the last tag.
    """

    try:
        date: str = git("log", "-1", "--format=%cs")
    except (subprocess.CalledProcessError, FileNotFoundError):
        return f"v{version}"

    try:
        rev_range: str = f"{git('describe', '--tags', '--abbrev=0')}..HEAD"
    except subprocess.CalledProcessError:
        rev_range = "HEAD"  # no tags yet

    subjects: list[str] = git("log", "--format=%s (%h)", rev_range).splitlines()
    return format_news(version, date, subjects)


# Dev-only xsi schema references; the xsd files are not shipped
XSI_ATTRS: re.Pattern[str] = re.compile(r'\s+(xmlns:xsi|xsi:noNamespaceSchemaLocation)="[^"]*"')


def strip_xsi(path: Path) -> None:
    text: str = path.read_text()
    stripped: str = XSI_ATTRS.sub("", text)
    if stripped != text:
        path.write_text(stripped)


def stamp_addon_xml(addon_xml: Path, version: str, news: str) -> None:
    text: str = addon_xml.read_text()
    for token, value in (("%VERSION%", version), ("%NEWS%", news)):
        if token not in text:
            raise SystemExit(f"addon.xml: missing {token} placeholder")
        text = text.replace(token, escape(value))

    try:
        ElementTree.fromstring(text)
    except ElementTree.ParseError as error:
        raise SystemExit(f"addon.xml is not well-formed after stamping: {error}") from error

    addon_xml.write_text(text)


def zip_datetime() -> tuple[int, int, int, int, int, int]:
    """
    Fixed zip entry timestamp:
    - SOURCE_DATE_EPOCH (reproducible-builds.org convention) wins;
    - falls back to the last commit time
      so rebuilding the same commit is byte-identical.
    Zip can't store pre-1980 dates.
    """

    epoch: int = int(os.environ.get("SOURCE_DATE_EPOCH") or git("log", "-1", "--format=%ct"))
    utc: time.struct_time = time.gmtime(max(epoch, 315532800))

    return (utc.tm_year, utc.tm_mon, utc.tm_mday, utc.tm_hour, utc.tm_min, utc.tm_sec)


def write_zip(archive: Path, root: Path, prefix: str) -> None:
    """
    Deterministic zip of root/ with entries under prefix/: sorted paths,
    fixed timestamp, normalized permissions, fixed compression.
    """

    stamp = zip_datetime()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in sorted(root.rglob("*")):
            if path.is_dir() and not path.is_symlink():
                continue
            if path.is_symlink() or not path.is_file():
                raise SystemExit(f"refusing to zip non-regular file: {path}")

            info: zipfile.ZipInfo = zipfile.ZipInfo(f"{prefix}/{path.relative_to(root).as_posix()}", date_time=stamp)
            info.external_attr = 0o644 << 16

            zf.writestr(info, path.read_bytes())


def tracked_files() -> list[Path]:
    """
    Files to ship = files git tracks under addon/ and src/
    (.gitignore is the single source of truth; untracked files never ship).
    """

    try:
        out: str = git("ls-files", "-z", "--", "addon", "src")
    except FileNotFoundError as error:
        raise SystemExit("git is required to build (staging and <news>)") from error
    except subprocess.CalledProcessError as error:
        raise SystemExit(f"git ls-files failed: {error.stderr.strip()}") from error
    return [Path(entry) for entry in out.split("\0") if entry]


def stage(staging: Path) -> None:
    """
    addon/* lands at the staging root, src/ keeps its prefix.
    """

    for source in tracked_files():
        inner: Path = source.relative_to("addon") if source.is_relative_to("addon") else source
        dest: Path = staging / inner
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)


def main() -> None:
    name: str = addon_id()
    version: str = project_version()
    staging: Path = Path("build") / name

    shutil.rmtree(staging, ignore_errors=True)
    stage(staging)
    for xml in staging.rglob("*.xml"):
        strip_xsi(xml)
    stamp_addon_xml(staging / "addon.xml", version, news_from_git(version))

    archive: Path = Path("build") / f"{name}-{version}.zip"
    write_zip(archive, staging, name)
    print(f"Created {archive} (version {version})")


if __name__ == "__main__":
    main()
