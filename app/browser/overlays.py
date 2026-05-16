"""Модалки (мешают работе) vs промо-баннеры (не кликать — откроют лишнее окно)."""

_HINT_JS = """
() => {
  const visible = (el) => {
    if (!el) return false;
    const r = el.getBoundingClientRect();
    if (r.width < 8 || r.height < 8) return false;
    const st = getComputedStyle(el);
    if (st.visibility === 'hidden' || st.display === 'none' || st.opacity === '0') return false;
    return r.bottom > 0 && r.right > 0 && r.top < innerHeight && r.left < innerWidth;
  };

  const promoRe = /кешбэк|кешбек|кэшбэк|приложени|баннер|carousel|slider|перейти в приложение|ещё больше скидок|скачать приложение/i;

  const isPromoNode = (el) => {
    if (!el || !visible(el)) return false;
    const r = el.getBoundingClientRect();
    if (r.top > innerHeight * 0.48) return false;
    const text = (
      (el.innerText || '') + ' ' +
      (el.getAttribute('aria-label') || '') + ' ' +
      (el.getAttribute('title') || '')
    );
    if (promoRe.test(text)) return true;
    const host = el.closest(
      '[class*="banner" i], [class*="Banner" i], [class*="carousel" i], [class*="Carousel" i], [class*="promo" i], [class*="Promo" i], [class*="Hero" i], [data-testid*="banner" i]'
    );
    if (host && visible(host)) {
      const hr = host.getBoundingClientRect();
      if (hr.top < innerHeight * 0.5 && hr.height > 60) return true;
    }
    return false;
  };

  const blockingModals = [];
  for (const el of document.querySelectorAll('[aria-modal="true"], dialog, [role="dialog"]')) {
    if (!visible(el)) continue;
    const r = el.getBoundingClientRect();
    const area = r.width * r.height;
    const areaPct = (area / (innerWidth * innerHeight)) * 100;
    const text = (el.innerText || '').trim().replace(/\\s+/g, ' ').slice(0, 280);
    const lower = text.toLowerCase();
    const st = getComputedStyle(el);
    const fixed = st.position === 'fixed' || st.position === 'absolute';
    const hasClose = !!el.querySelector(
      '[aria-label*="закрыть" i], [aria-label*="Закрыть" i], [aria-label*="close" i], button[class*="close" i], button[class*="Close" i]'
    );
    const ariaModal = el.getAttribute('aria-modal') === 'true';

    const looksLikeAddressOrCookie =
      lower.includes('мои адреса') || lower.includes('выберите адрес') ||
      lower.includes('cookie') || lower.includes('куки');

    const isBlocking =
      ariaModal ||
      looksLikeAddressOrCookie ||
      (hasClose && areaPct >= 12) ||
      (fixed && areaPct >= 18 && hasClose);

    if (!isBlocking) continue;
    if (promoRe.test(text) && !hasClose && !looksLikeAddressOrCookie) continue;

    const heading = el.querySelector('h1,h2,h3,[role="heading"]');
    blockingModals.push({
      heading: heading ? (heading.innerText || '').trim().slice(0, 120) : '',
      text,
      areaPct: Math.round(areaPct),
    });
    if (blockingModals.length >= 4) break;
  }

  const promos = [];
  const seen = new Set();
  for (const el of document.querySelectorAll('a, button, [role="button"], [role="link"]')) {
    if (!isPromoNode(el)) continue;
    const label = (
      (el.innerText || '').trim() ||
      el.getAttribute('aria-label') ||
      el.getAttribute('title') ||
      'промо-блок'
    ).replace(/\\s+/g, ' ').slice(0, 100);
    if (seen.has(label)) continue;
    seen.add(label);
    const r = el.getBoundingClientRect();
    promos.push({ label, y: Math.round(r.top) });
    if (promos.length >= 8) break;
  }

  const buttons = [];
  for (const el of document.querySelectorAll('button, [role="button"]')) {
    if (!visible(el)) continue;
    const label = (
      el.getAttribute('aria-label') ||
      (el.innerText || '').trim()
    ).replace(/\\s+/g, ' ').slice(0, 80);
    if (
      !label &&
      (el.innerText || '').trim() !== '+' &&
      (el.innerText || '').trim() !== '＋'
    ) continue;
    const low = label.toLowerCase();
    if (
      !(
        low.includes('добав') ||
        low.includes('корзин') ||
        low.includes('купить') ||
        label === '+' ||
        label === '＋'
      )
    ) continue;
    const r = el.getBoundingClientRect();
    buttons.push({
      label: label || '+',
      x: Math.round(r.x + r.width / 2),
      y: Math.round(r.y + r.height / 2),
    });
    if (buttons.length >= 12) break;
  }

  return { blockingModals, promos, buttons };
}
"""

_CLICK_CHECK_JS = """
(el) => {
  if (!el) return null;
  const r = el.getBoundingClientRect();
  if (r.width < 1 || r.height < 1) return null;
  const raw = (el.innerText || '').trim();
  if (raw === '+' || raw === '＋') return null;
  const text = (
    (el.innerText || '') + ' ' +
    (el.getAttribute('aria-label') || '') + ' ' +
    (el.getAttribute('title') || '')
  );
  const low = text.toLowerCase();
  if (low.includes('₽') || /\\d[\\d\\s]*₽/.test(text)) return null;
  if (low.includes('добав') && low.includes('корзин')) return null;
  const promoRe = /кешбэк|кешбек|кэшбэк|приложени|баннер|carousel|slider|перейти в приложение|ещё больше скидок|скачать приложение/i;
  if (r.top < window.innerHeight * 0.42) {
    if (promoRe.test(low)) return 'promo_text';
    const host = el.closest(
      '[class*="banner" i], [class*="Banner" i], [class*="carousel" i], [class*="Carousel" i], [class*="Hero" i], [data-testid*="banner" i]'
    );
    if (host) {
      const hr = host.getBoundingClientRect();
      if (hr.top < window.innerHeight * 0.45 && hr.height > 50) return 'promo_container';
    }
  }
  return null;
}
"""

_BANNER_BLOCK_MESSAGE = (
    "Клик заблокирован: верхний промо-баннер (TOP_PROMO_REGIONS). "
    "Для добавления в корзину без ref «+» в ARIA используй add_to_cart с product_name из CURRENT PAGE."
)


def _normalize_selector(selector: str) -> str:

    s = selector.strip()

    if s.startswith("aria-ref="):

        return s

    if len(s) > 1 and s[0] == "e" and s[1:].isdigit():

        return f"aria-ref={s}"

    return s


def extract_overlay_hints(page) -> str:

    try:

        data = page.evaluate(_HINT_JS)

    except Exception as exc:

        return f"[overlay scan failed: {exc}]"

    lines = []

    modals = data.get("blockingModals") or []

    if modals:

        lines.append("BLOCKING_OVERLAY: detected (large overlay / dialog on page):")

        for i, d in enumerate(modals, 1):

            lines.append(
                f"  [{i}] heading={d.get('heading')!r} area≈{d.get('areaPct')}% "
                f"text={d.get('text')!r}"
            )

    promos = data.get("promos") or []

    if promos:

        lines.append("TOP_PROMO_REGIONS: clickable elements in upper viewport:")

        for p in promos:

            lines.append(f"  — label={p.get('label')!r} y≈{p.get('y')}")

    buttons = data.get("buttons") or []

    if buttons:

        lines.append("ADD_TO_CART_BUTTONS_DETECTED: (viewport coordinates, informational):")

        for b in buttons:

            lines.append(
                f"  label={b.get('label')!r} center≈({b.get('x')},{b.get('y')})"
            )

    if not lines:

        return ""

    return "PAGE_HINTS:\n" + "\n".join(lines)


def click_blocked_reason(page, selector: str) -> str | None:

    sel = _normalize_selector(selector)

    try:

        root = page.locator(sel)

        if root.count() == 0:

            return None

        kind = root.first.evaluate(_CLICK_CHECK_JS)

    except Exception:

        return None

    if kind:

        return _BANNER_BLOCK_MESSAGE

    return None


def dismiss_overlays(page) -> str:

    steps = []

    try:

        page.keyboard.press("Escape")

        steps.append("Escape")

    except Exception as exc:

        steps.append(f"Escape failed: {exc}")

    page.wait_for_timeout(400)

    close_selectors = [
        '[aria-modal="true"] [aria-label*="Закрыть" i]',
        '[aria-modal="true"] [aria-label*="закрыть" i]',
        '[role="dialog"] [aria-label*="Закрыть" i]',
        '[role="dialog"] [aria-label*="закрыть" i]',
        'dialog [aria-label*="закрыть" i]',
        '[aria-label*="Закрыть" i]',
        '[aria-label*="закрыть" i]',
        '[data-testid*="close" i]',
        '[class*="CloseButton" i]',
        '[class*="closeButton" i]',
        '[role="dialog"] button:has-text("×")',
    ]

    for sel in close_selectors:

        try:

            loc = page.locator(sel).first

            if loc.is_visible(timeout=400):

                loc.click(timeout=5000)

                steps.append(f"click {sel}")

                page.wait_for_timeout(300)

        except Exception:

            continue

    try:

        page.keyboard.press("Escape")

    except Exception:

        pass

    return "; ".join(steps) if steps else "nothing done"
