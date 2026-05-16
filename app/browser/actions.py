import os
import time
from pathlib import Path

from browser.url_validate import validate_agent_url
from config import SCREENSHOT_DIR


class BrowserActions:

    def __init__(self, browser):

        self._browser = browser

    @property
    def page(self):

        return self._browser.page

    def _locator(self, selector: str):

        s = selector.strip()

        if s.startswith("aria-ref="):

            return self.page.locator(s)

        if len(s) > 1 and s[0] == "e" and s[1:].isdigit():

            return self.page.locator(f"aria-ref={s}")

        return self.page.locator(s)

    def open_url(self, url: str, allowed_urls=None):

        allowed = allowed_urls if allowed_urls is not None else frozenset()

        url = validate_agent_url(url, allowed_urls=allowed)

        wait = os.getenv("PLAYWRIGHT_GOTO_WAIT", "domcontentloaded").strip()

        self.page.goto(url, wait_until=wait)

    def go_back(self):

        self.page.go_back(wait_until="domcontentloaded")

    def take_screenshot(self, *, full_page: bool = False):

        raw = (os.getenv("AGENT_SCREENSHOT_DIR") or "").strip()

        base = SCREENSHOT_DIR if not raw else Path(raw)

        base.mkdir(parents=True, exist_ok=True)

        name = f"screenshot-{int(time.time() * 1000)}.png"

        path = base / name

        png = self.page.screenshot(
            full_page=full_page,
            type="png",
            animations="disabled",
        )

        path.write_bytes(png)

        return path, png

    def click(self, selector: str, *, force: bool = False):

        loc = self._locator(selector).first

        loc.scroll_into_view_if_needed(timeout=8000)

        timeout = 15000

        if force:

            loc.click(force=True, timeout=timeout)

            return

        try:

            loc.click(timeout=timeout)

        except Exception:

            loc.click(force=True, timeout=timeout)

    def dismiss_overlays(self) -> str:

        from browser.overlays import dismiss_overlays as _dismiss

        return _dismiss(self.page)

    def press_page_key(self, key: str):

        self.page.keyboard.press(key)

    def type(self, selector: str, text: str):

        self._locator(selector).first.fill(text, timeout=20000)

    def wait_ms(self, ms: int):

        self.page.wait_for_timeout(int(ms))

    def scroll(self, direction: str = "down", amount_px: int = 800):

        delta = -int(amount_px) if direction == "up" else int(amount_px)

        self.page.mouse.wheel(0, delta)

    def press(self, selector: str, key: str):

        self._locator(selector).first.press(key, timeout=20000)

    def add_to_cart(self, product_name: str = "") -> str:

        from browser.cart_plus import click_add_to_cart

        return click_add_to_cart(self.page, product_name)
