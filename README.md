# Kodi Addon Example

Full example of a Kodi script add-on -- settings with several field types,
localized labels, artwork, and a dialog showing the configured values --
structured so the add-on skeleton, the Python code, and the dev tooling stay
separate.

Targets Kodi **v21 Omega** or later.

## Layout

| Path                     | Purpose                                                                              |
| ------------------       | ------------------------------------------------------------------------------------ |
| `addon/`                 | Static add-on skeleton: `addon.xml`, entry shim, assets                              |
| `addon/addon.py`         | Entry point (`library=`); only calls `src.main.main()`                               |
| `addon/resources/`       | Settings, localization (`strings.po`), extra artwork                                 |
| `src/`                   | The actual Python code; ships as `src/` inside the add-on                            |
| `repo/`                  | Repository add-on (points Kodi at the Pages repo)                                    |
| `scripts/build.py`       | Assembles `build/<id>/` from `addon/` + `src/` and zips it                           |
| `scripts/repo.py`        | Builds the repository add-on zip and generates `build/repo/` (addons.xml, md5, zips) |
| `types/xml/addon.xsd`    | Schema validating `addon/addon.xml` (XSD 1.1)                                        |
| `types/xml/settings.xsd` | Schema validating `addon/resources/settings.xml` (XSD 1.1)                           |
| `types/xml/1.0/`         | Generated XSD 1.0 companions of the schemas, for the IDE (`poe xsd10`)               |
| `types/python/`          | Generated Kodi API stubs for pyright/mypy (`poe stubs`)                              |
| `tests/`                 | pytest suite: greeting logic, schemas, build/stubs helpers                           |
| `.github/workflows/`     | CI: `check.yml` (push/PR gate), `release.yml` (on demand)                            |

The installed add-on looks like:

```tree
script.example/
├── addon.xml
├── addon.py        <- shim
├── icon.png
├── fanart.jpg
├── resources/
│   ├── settings.xml
│   ├── language/resource.language.en_gb/strings.po
│   ├── banner.jpg / clearlogo.png / screenshot-*.png
└── src/
    ├── __init__.py
    └── main.py     <- main()
```

Settings (*Add-ons -> Example -> Configure*) demonstrate the new-style format:
a text field, a bounded slider, a toggle, and a fixed choice list, all with
labels/help from `strings.po`. Running the add-on shows the current values in
a dialog.

Kodi puts the add-on root on `sys.path`, so `from src.main import main` works
identically at runtime and for the type checkers running from the repo root.

## Install

```sh
uv run poe build
```

Then in Kodi: *Settings -> System -> Add-ons* -> enable **Unknown sources**, and
*Settings -> Add-ons -> Install from zip file* -> pick `build/script.example-<version>.zip`.

Alternatively, install the repository add-on once
(`repository.example-<version>.zip` from
<https://playday3008.github.io/kodi.addon.example/>) -- Kodi then updates the
example add-on automatically from GitHub Pages.

Run it from *Add-ons -> Program add-ons -> Example*.

## Development

Requires [uv](https://docs.astral.sh/uv/):

```sh
uv sync
uv run poe build   # build the zip; stamps addon.xml version (from pyproject)
                   # and news (from git subjects since the last tag)
uv run poe stubs   # regenerate Kodi stubs into types/python/
uv run poe test    # pytest: greeting logic, XML schema validation, build/stubs
uv run poe check   # full gate: ruff + mypy + pyright + pytest
uv run poe repo    # build zips + generate the Kodi repository tree in build/repo
```

The build stages exactly the **git-tracked** files under `addon/` and `src/` --
`.gitignore` is the single source of truth for what ships.

## Schemas

`types/xml/addon.xsd` and `types/xml/settings.xsd` are self-contained **XSD 1.1**
schemas (no network needed). `poe test` validates both XML files against them via
`xmlschema` -- that is the authoritative check. Editor validation is a convenience
on top: VS Code's XML extension only implements XSD 1.0, so `.vscode/settings.json`
binds the XML files to generated 1.0 companions in `types/xml/1.0/` (`poe xsd10`
regenerates them; deliberately laxer -- asserts and per-type content models are
enforced by pytest only). Each type in the schemas cites its source: the upstream
fragment schemas at the `21.3-Omega` tag, the Kodi C++ parsers, kodi-addon-checker,
or the wiki.

Version policy: Kodi compares versions **Debian-style**, not SemVer
(`xbmc/addons/AddonVersion.cpp`). Use `~alpha`/`~beta` for prereleases -- a SemVer
`1.0.0-rc.1` would sort *above* `1.0.0` in Kodi. The schema enforces the official
repo's rule: `\d+\.\d+(\.\d+){0,4}([+~\w]+(\.\d+)?)?`.

## Release

1. Bump `project.version` in `pyproject.toml` (Kodi ordering, not SemVer:
   `~alpha`/`~beta` for prereleases) and merge to `main`.
2. Run the **Release** workflow (*Actions -> Release -> Run workflow*). It refuses
   existing tags, runs the full gate, tags `v<version>`, attaches the zip to a
   GitHub Release, and redeploys the Kodi repository to GitHub Pages with every
   released version still installable.

One-time GitHub setup: push `main` (`git push -u origin main`), make it the
default branch (`gh repo edit --default-branch main`), and enable Pages with
source **GitHub Actions** (*Settings -> Pages*).

## Reproducible builds

Zips are byte-identical for the same commit: entries are sorted, permissions
normalized, and timestamps fixed from `SOURCE_DATE_EPOCH` (falling back to the
last commit time). `build/repo/` (addons.xml + md5) is deterministic too.

## References

- [Add-on structure](https://kodi.wiki/view/Add-on_structure)
- [Addon.xml spec](https://kodi.wiki/view/Addon.xml)
- [Add-on settings conversion](https://kodi.wiki/view/Add-on_settings_conversion)
