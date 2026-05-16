from browser.cart_plus import format_cart_status_line, read_cart_state
from browser.overlays import extract_overlay_hints
from config import (
    ARIA_SNAPSHOT_TIMEOUT_MS,
    BODY_INNER_TEXT_TIMEOUT_MS,
    MAX_ARIA_SNAPSHOT_CHARS,
    MAX_BODY_FALLBACK_CHARS,
    PAGE_ARIA_DEPTH,
)


def extract_page_context(page):

    url = page.url

    title = page.title()

    aria = ""

    try:

        aria = page.aria_snapshot(
            mode="ai",
            depth=PAGE_ARIA_DEPTH,
            timeout=ARIA_SNAPSHOT_TIMEOUT_MS,
        )

    except Exception as exc:

        aria = f"[aria_snapshot failed: {exc}]"

    if len(aria) > MAX_ARIA_SNAPSHOT_CHARS:

        aria = (
            aria[:MAX_ARIA_SNAPSHOT_CHARS]
            + "\n...[aria snapshot truncated]..."
        )

    body_preview = ""

    try:

        body_preview = page.locator("body").inner_text(timeout=BODY_INNER_TEXT_TIMEOUT_MS)

        if len(body_preview) > MAX_BODY_FALLBACK_CHARS:

            body_preview = (
                body_preview[:MAX_BODY_FALLBACK_CHARS]
                + "\n...[body text truncated]..."
            )

    except Exception as exc:

        body_preview = f"[body inner_text failed: {exc}]"

    overlay_block = extract_overlay_hints(page)

    overlay_section = ""

    if overlay_block:

        overlay_section = f"\n{overlay_block}\n"

    cart_line = format_cart_status_line(read_cart_state(page))

    return f"""
URL: {url}
TITLE: {title}
{cart_line}{overlay_section}
ARIA_SNAPSHOT (mode=ai; to click/type use selector "aria-ref=eN" from lines like [ref=eN]):
{aria}

BODY_TEXT_FALLBACK:
{body_preview}
"""
