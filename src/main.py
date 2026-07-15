import xbmcaddon
import xbmcgui

from src.greeting import build_greeting

DIALOG_LINE_BREAK = "[CR]"  # Kodi's line break in dialog text


def main() -> None:
    addon = xbmcaddon.Addon()
    name: str = addon.getAddonInfo("name")
    settings: xbmcaddon.Settings = addon.getSettings()

    lines: list[str] = build_greeting(
        settings.getString("username"),
        settings.getString("greeting_style"),
        settings.getInt("greeting_count"),
        settings.getBool("excited"),
    )

    if settings.getBool("excited") and (suffix := settings.getString("custom_suffix")):
        lines.append(suffix)

    lines += [
        f"Pause between greetings: {settings.getNumber('pause_seconds')}s",
        f"Export folder: {settings.getString('export_path') or '(unset)'}",
    ]

    xbmcgui.Dialog().ok(name, DIALOG_LINE_BREAK.join(lines))


if __name__ == "__main__":
    main()
