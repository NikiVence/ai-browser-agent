import os
import platform
from pathlib import Path

from typing import Optional

from playwright.sync_api import sync_playwright

from config import USER_DATA_DIR


def _yandex_exe_search_paths() -> list[Path]:

    paths: list[Path] = []

    if platform.system() == "Windows":

        local = os.environ.get("LOCALAPPDATA", "")

        if local:

            base = Path(local) / "Yandex" / "YandexBrowser" / "Application"

            paths.extend(
                [
                    base / "browser.exe",
                    base / "yandexbrowser.exe",
                ]
            )

        pf86 = os.environ.get("PROGRAMFILES(X86)", "")

        if pf86:

            base_pf = Path(pf86) / "Yandex" / "YandexBrowser" / "Application"

            paths.extend(
                [
                    base_pf / "browser.exe",
                    base_pf / "yandexbrowser.exe",
                ]
            )

        pf = os.environ.get("PROGRAMFILES", "")

        if pf:

            base_p = Path(pf) / "Yandex" / "YandexBrowser" / "Application"

            paths.extend(
                [
                    base_p / "browser.exe",
                    base_p / "yandexbrowser.exe",
                ]
            )

    elif platform.system() == "Linux":

        paths.extend(
            [
                Path("/opt/yandex/browser/yandex-browser"),
                Path("/usr/bin/yandex-browser"),
            ]
        )

    elif platform.system() == "Darwin":

        paths.append(
            Path("/Applications/Yandex.app/Contents/MacOS/Yandex")
        )

    return paths


def _find_yandex_browser_on_disk() -> Optional[str]:

    for candidate in _yandex_exe_search_paths():

        if candidate.is_file():

            return str(candidate.resolve())

    return None


def _launch_kwargs() -> dict:

    ignore = [
        "--enable-automation",
    ]

    if not os.getenv("PLAYWRIGHT_DOCKER", "").strip():

        ignore.extend(
            [
                "--no-sandbox",
                "--disable-setuid-sandbox",
            ]
        )

    kwargs: dict = {
        "user_data_dir": str(USER_DATA_DIR),
        "headless": False,
        "ignore_default_args": ignore,
    }

    if os.getenv("PLAYWRIGHT_BLINK_AUTOMATION_DISABLED", "").strip().lower() in (
        "1",
        "true",
        "yes",
    ):

        kwargs["args"] = [
            "--disable-blink-features=AutomationControlled",
        ]

    exe_env = os.getenv("PLAYWRIGHT_EXECUTABLE", "").strip()

    if exe_env:

        p = Path(exe_env)

        if not p.is_file():

            raise FileNotFoundError(
                f"PLAYWRIGHT_EXECUTABLE: файл не найден: {exe_env}"
            )

        kwargs["executable_path"] = str(p.resolve())

        return kwargs

    channel = os.getenv("PLAYWRIGHT_CHANNEL", "").strip().lower()

    if channel == "yandex":

        yandex = _find_yandex_browser_on_disk()

        if not yandex:

            raise RuntimeError(
                "Яндекс.Браузер не найден по стандартным путям. "
                "Укажи полный путь к browser.exe в .env, например:\n"
                "PLAYWRIGHT_EXECUTABLE=C:\\Users\\ИМЯ\\AppData\\Local\\Yandex\\YandexBrowser\\Application\\browser.exe"
            )

        kwargs["executable_path"] = yandex

        return kwargs

    if channel:

        kwargs["channel"] = channel

    return kwargs


class Browser:

    def __init__(self):

        self.playwright = sync_playwright().start()

        self._cdp_browser = None

        cdp_url = os.getenv("PLAYWRIGHT_CDP_URL", "").strip()

        if cdp_url:

            self._cdp_browser = self.playwright.chromium.connect_over_cdp(cdp_url)

            contexts = self._cdp_browser.contexts

            if not contexts:

                raise RuntimeError(
                    "CDP: подключились, но у Chrome нет открытых контекстов. "
                    "Оставь хотя бы одно окно Chrome с вкладкой."
                )

            self.context = contexts[0]

            if self.context.pages:

                self.page = self.context.pages[0]

            else:

                self.page = self.context.new_page()

            self._known_page_count = self._alive_page_count()

            return

        USER_DATA_DIR.mkdir(parents=True, exist_ok=True)

        self.context = self.playwright.chromium.launch_persistent_context(
            **_launch_kwargs()
        )

        if self.context.pages:

            self.page = self.context.pages[0]

        else:

            self.page = self.context.new_page()

        self._known_page_count = self._alive_page_count()

    def _alive_page_count(self) -> int:

        try:

            return len([p for p in self.context.pages if not p.is_closed()])

        except Exception:

            return 0

    def adopt_new_tab_after_action(self) -> None:

        if os.getenv("PLAYWRIGHT_FOLLOW_NEWEST_TAB", "1").strip().lower() in (
            "0",
            "false",
            "no",
        ):

            return

        try:

            pages = [p for p in self.context.pages if not p.is_closed()]

        except Exception:

            return

        now = len(pages)

        if now > self._known_page_count and pages:

            self.page = pages[-1]

            try:

                self.page.bring_to_front()

            except Exception:

                pass

        self._known_page_count = now
