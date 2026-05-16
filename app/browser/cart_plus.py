"""Добавление в корзину: «В корзину» / «+» на карточке, CART_SENSOR с учётом счётчика на PDP."""

_CART_STATE_JS = """
() => {
  const norm = (s) => (s || '').replace(/\\s+/g, ' ').trim();
  const emptyPhrases = [
    'В корзине пока ничего нет',
    'Самое время наполнять',
    'Добавьте что-нибудь',
  ];
  const allText = norm(document.body.innerText || '');
  for (const p of emptyPhrases) {
    if (allText.includes(p)) {
      return { empty: true, filled: false, reason: 'empty_text' };
    }
  }
  const panels = document.querySelectorAll(
    '[class*="Cart" i], [class*="cart" i], [data-testid*="cart" i], aside'
  );
  for (const panel of panels) {
    const r = panel.getBoundingClientRect();
    if (r.width < 40 || r.height < 40) continue;
    if (r.left < window.innerWidth * 0.45) continue;
    const pt = norm(panel.innerText || '');
    if (!pt || pt.length < 3) continue;
    if (emptyPhrases.some((p) => pt.includes(p))) continue;
    if (pt.includes('₽') && (pt.includes('Оформить') || /\\d+\\s*шт/i.test(pt) || /[−-]\\s*\\d+/.test(pt))) {
      const qm = pt.match(/(\\d+)\\s*шт/i);
      const q = qm ? parseInt(qm[1], 10) : 1;
      return { empty: false, filled: true, reason: 'cart_panel', snippet: pt.slice(0, 120), qty: q };
    }
  }
  let qty = null;
  const qtyBody = allText.match(/(\\d+)\\s*шт/i);
  if (qtyBody) qty = parseInt(qtyBody[1], 10);
  if (/Оформить/i.test(allText) && !/Добавьте что-нибудь/i.test(allText)) {
    const m = allText.match(/(\\d+[\\s\\u00a0]*₽)/);
    if (m) {
      return {
        empty: false,
        filled: true,
        reason: 'checkout_cta',
        snippet: m[0],
        qty: qty || 1,
      };
    }
  }
  return { empty: true, filled: false, reason: 'assume_empty', qty: null };
}
"""

_STEPPER_QTY_JS = """
() => {
  const parseQty = (node) => {
    if (!node) return null;
    let v = node.getAttribute('aria-valuenow') || node.getAttribute('value') || node.value;
    if (v == null || v === '') v = (node.innerText || '').trim();
    const n = parseInt(String(v).replace(/\\D/g, ''), 10);
    return Number.isFinite(n) && n >= 0 ? n : null;
  };
  const isAdjust = (el) => {
    const al = (el.getAttribute('aria-label') || '').toLowerCase();
    return al.includes('увелич') || al.includes('уменьш') || al.includes('increase') || al.includes('decrease');
  };
  const adjustBtns = [...document.querySelectorAll('button, [role="button"]')].filter(isAdjust);
  if (!adjustBtns.length) return null;
  let root = adjustBtns[0];
  for (let i = 0; i < 14 && root; i++) {
    const spin = root.querySelector('[role="spinbutton"], input[type="number"]');
    const tb = root.querySelector('[role="textbox"]');
    const q = parseQty(spin) ?? parseQty(tb);
    if (q != null && q >= 0) return { qty: q, source: 'product_stepper' };
    root = root.parentElement;
  }
  return null;
}
"""

_HEADER_CART_JS = """
() => {
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    return r.width > 8 && r.height > 8 && r.bottom > 0 && r.top < innerHeight;
  };
  for (const el of document.querySelectorAll('a, button, [role="link"], [role="button"]')) {
    if (!visible(el)) continue;
    const al = (el.getAttribute('aria-label') || '').toLowerCase();
    const t = (el.innerText || '').trim();
    const blob = (al + ' ' + t).toLowerCase();
    if (!blob.includes('корзин')) continue;
    const m = blob.match(/(\\d+)/);
    if (m) {
      const q = parseInt(m[1], 10);
      if (q >= 1) return { qty: q, source: 'header_cart' };
    }
  }
  return null;
}
"""

_FIND_ADD_TO_CART_BTN_JS = """
() => {
  const visible = (el) => {
    if (!el) return false;
    const r = el.getBoundingClientRect();
    if (r.width < 40 || r.height < 24) return false;
    const st = getComputedStyle(el);
    if (st.visibility === 'hidden' || st.display === 'none' || st.pointerEvents === 'none') return false;
    return r.bottom > 0 && r.top < innerHeight && r.right > 0 && r.left < innerWidth;
  };
  const isAdjust = (al, raw) => {
    const t = raw.toLowerCase();
    if (al.includes('увелич') || al.includes('уменьш') || al.includes('increase') || al.includes('decrease')) return true;
    if (raw === '+' || raw === '−' || raw === '-' || raw === '＋') return true;
    return false;
  };
  const candidates = [];
  for (const el of document.querySelectorAll('button, [role="button"]')) {
    if (!visible(el)) continue;
    const al = (el.getAttribute('aria-label') || '').toLowerCase();
    const raw = (el.innerText || '').trim();
    if (isAdjust(al, raw)) continue;
    const t = raw.toLowerCase();
    if (t.includes('в корзину') || al.includes('в корзин') || al.includes('добавить в корзин')) {
      const r = el.getBoundingClientRect();
      candidates.push({
        y: r.y,
        x: r.x + r.width / 2,
        cy: r.y + r.height / 2,
        label: raw || al,
      });
    }
  }
  if (!candidates.length) return null;
  candidates.sort((a, b) => b.y - a.y);
  const best = candidates[0];
  return { x: best.x, y: best.cy, label: best.label };
}
"""

_FIND_PRODUCT_CARDS_JS = """
(hint) => {
  const norm = (s) => (s || '').toLowerCase().replace(/ё/g, 'е').replace(/[-—–]/g, ' ').replace(/\\s+/g, ' ').trim();
  const hintN = norm(hint || '');
  const words = hintN ? hintN.split(' ').filter((w) => w.length > 2) : [];

  const visible = (el) => {
    if (!el || el.closest('[aria-modal="true"], [role="dialog"]')) return false;
    const r = el.getBoundingClientRect();
    if (r.width < 70 || r.height < 55) return false;
    if (r.bottom < 0 || r.top > innerHeight || r.right < 0 || r.left > innerWidth) return false;
    const st = getComputedStyle(el);
    if (st.visibility === 'hidden' || st.display === 'none' || st.pointerEvents === 'none') return false;
    if (r.left > innerWidth * 0.72) return false;
    if (r.top < innerHeight * 0.08 && r.height < 120) return false;
    return true;
  };

  const scoreText = (t) => {
    const n = norm(t);
    if (!n.includes('₽')) return -1;
    if (n.length < 10 || n.length > 700) return -1;
    if (!hintN) return 1;
    if (n.includes(hintN)) return 100;
    if (words.length && words.every((w) => n.includes(w))) return 80;
    let s = 0;
    for (const w of words) if (n.includes(w)) s += 20;
    return s;
  };

  const findAddBtnInRoot = (root) => {
    for (const b of root.querySelectorAll('button, [role="button"]')) {
      const al = (b.getAttribute('aria-label') || '').toLowerCase();
      if (al.includes('увелич') || al.includes('уменьш')) continue;
      const raw = (b.innerText || '').trim();
      if (raw === '+' || raw === '＋' || al.includes('добав') || al.includes('корзин')) {
        const br = b.getBoundingClientRect();
        if (br.width >= 12 && br.width <= 64 && br.height >= 12) {
          return { x: br.x + br.width / 2, y: br.y + br.height / 2 };
        }
      }
    }
    return null;
  };

  const pickCardRoot = (el) => {
    let best = el;
    let bestScore = -1;
    let n = el;
    for (let i = 0; i < 12 && n; i++) {
      const r = n.getBoundingClientRect();
      const t = n.innerText || '';
      const sc = scoreText(t);
      if (sc >= 0 && r.width >= 70 && r.height >= 55 && r.width < innerWidth * 0.65) {
        if (sc > bestScore || (sc === bestScore && r.width * r.height < (best.getBoundingClientRect().width * best.getBoundingClientRect().height))) {
          best = n;
          bestScore = sc;
        }
      }
      n = n.parentElement;
    }
    return bestScore >= 0 ? best : null;
  };

  const seen = new Set();
  const cards = [];
  const seeds = document.querySelectorAll('a, article, li, [role="listitem"], [role="button"], div');

  for (const el of seeds) {
    if (!visible(el)) continue;
    const root = pickCardRoot(el);
    if (!root || seen.has(root)) continue;
    const r = root.getBoundingClientRect();
    const key = Math.round(r.x) + ':' + Math.round(r.y) + ':' + Math.round(r.width);
    if (seen.has(key)) continue;
    seen.add(root);
    seen.add(key);
    const t = (root.innerText || '').replace(/\\s+/g, ' ').trim();
    const sc = scoreText(t);
    if (sc < 0) continue;
    const addBtn = findAddBtnInRoot(root);
    cards.push({
      score: sc,
      snippet: t.slice(0, 90),
      cardX: r.x + Math.min(r.width * 0.42, r.width - 40),
      cardY: r.y + r.height * 0.45,
      plusX: addBtn ? addBtn.x : r.right - Math.min(28, r.width * 0.12),
      plusY: addBtn ? addBtn.y : r.y + r.height * 0.55,
      hasAddBtn: !!addBtn,
      top: r.top,
    });
  }

  cards.sort((a, b) => b.score - a.score || a.top - b.top);
  return cards.slice(0, 8);
}
"""

_FIND_PLUS_JS = """
(hint) => {
  const norm = (s) => (s || '').toLowerCase().replace(/ё/g, 'е').replace(/[-—–]/g, ' ').replace(/\\s+/g, ' ').trim();
  const hintN = norm(hint || '');
  const words = hintN ? hintN.split(' ').filter((w) => w.length > 2) : [];

  const visible = (el) => {
    if (!el) return false;
    const r = el.getBoundingClientRect();
    if (r.width < 8 || r.height < 8) return false;
    const st = getComputedStyle(el);
    if (st.visibility === 'hidden' || st.display === 'none' || st.pointerEvents === 'none') return false;
    return r.bottom > 0 && r.top < innerHeight && r.right > 0 && r.left < innerWidth;
  };

  const cardText = (el) => {
    let n = el;
    for (let i = 0; i < 16 && n; i++) {
      const t = norm(n.innerText || '');
      if (t.includes('₽') && t.length > 8 && t.length < 650) return t;
      n = n.parentElement;
    }
    return '';
  };

  const matchesHint = (t) => {
    if (!hintN) return true;
    if (!t) return false;
    if (t.includes(hintN)) return true;
    return words.length > 0 && words.every((w) => t.includes(w));
  };

  const isPlusEl = (el) => {
    const raw = (el.innerText || '').trim();
    const al = (el.getAttribute('aria-label') || '').toLowerCase();
    if (al.includes('увелич') || al.includes('уменьш') || al.includes('increase') || al.includes('decrease')) {
      return false;
    }
    if (raw === '+' || raw === '＋') return true;
    if (al.includes('добав') || al.includes('корзин')) return true;
    const cls = (el.className || '').toString().toLowerCase();
    if (/add|plus|basket/.test(cls) && el.tagName === 'BUTTON' && !/counter|increment/.test(cls)) return true;
    return false;
  };

  const out = [];
  const seen = new Set();
  const nodes = document.querySelectorAll(
    'button, [role="button"], [class*="Add" i], [class*="Plus" i]'
  );

  for (const el of nodes) {
    if (!visible(el) || !isPlusEl(el)) continue;
    const ct = cardText(el);
    if (!matchesHint(ct) && hintN) continue;
    const r = el.getBoundingClientRect();
    const key = Math.round(r.x) + ',' + Math.round(r.y);
    if (seen.has(key)) continue;
    seen.add(key);
    out.push({
      x: r.x + r.width / 2,
      y: r.y + r.height / 2,
      card: ct.slice(0, 80),
      label: (el.innerText || '').trim() || '+',
    });
    if (out.length >= 10) break;
  }
  return out;
}
"""

_SCROLL_POINT_JS = """
(p) => {
  const x = p.x, y = p.y;
  const el = document.elementFromPoint(x, y);
  if (el && el.scrollIntoView) {
    try { el.scrollIntoView({ block: 'center', inline: 'nearest' }); } catch (e) {}
  } else {
    window.scrollBy(0, y - innerHeight / 2);
  }
}
"""


def _merge_cart_signals(base: dict, stepper: dict | None, header: dict | None, *, page_url: str) -> dict:

    url = page_url or ""

    if stepper and int(stepper.get("qty") or 0) >= 1:

        return {
            "empty": False,
            "filled": True,
            "reason": stepper.get("source") or "product_stepper",
            "qty": int(stepper["qty"]),
            "snippet": base.get("snippet") or f"счётчик на странице: {stepper['qty']}",
        }

    if header and int(header.get("qty") or 0) >= 1:

        merged = {
            "empty": False,
            "filled": True,
            "reason": header.get("source") or "header_cart",
            "qty": int(header["qty"]),
            "snippet": base.get("snippet") or f"корзина в шапке: {header['qty']}",
        }

        if "/good/" not in url:

            return merged

        if not base.get("filled"):

            return merged

    if base.get("filled"):

        return base

    return base


def read_cart_state(page) -> dict:

    try:

        base = page.evaluate(_CART_STATE_JS)

        stepper = page.evaluate(_STEPPER_QTY_JS)

        header = page.evaluate(_HEADER_CART_JS)

        return _merge_cart_signals(
            base,
            stepper,
            header,
            page_url=page.url or "",
        )

    except Exception:

        return {"empty": True, "filled": False, "reason": "error"}


def cart_is_filled(cart: dict) -> bool:

    return bool(cart.get("filled"))


def cart_item_quantity(cart: dict) -> int:

    try:

        q = cart.get("qty")

        if q is None:

            return 1 if cart_is_filled(cart) else 0

        return max(0, int(q))

    except (TypeError, ValueError):

        return 1 if cart_is_filled(cart) else 0


def format_cart_status_line(cart: dict) -> str:

    if cart_is_filled(cart):

        snip = cart.get("snippet") or ""

        q = cart_item_quantity(cart)

        hint = ""

        if cart.get("reason") == "product_stepper":

            hint = " (счётчик на карточке товара — не путать с «Увеличить» для добавления)"

        return (
            f"CART_SENSOR: items_present qty={q} ({cart.get('reason', '')}){hint} {snip}\n"
        )

    return f"CART_SENSOR: appears_empty ({cart.get('reason', 'unknown')})\n"


def _element_label(page, selector: str) -> str:

    s = (selector or "").strip()

    if not s:

        return ""

    if s.startswith("aria-ref="):

        loc = page.locator(s).first

    elif len(s) > 1 and s[0] == "e" and s[1:].isdigit():

        loc = page.locator(f"aria-ref={s}").first

    else:

        loc = page.locator(s).first

    try:

        return (
            (loc.inner_text(timeout=2500) or "")
            + " "
            + (loc.get_attribute("aria-label") or "")
        ).lower()

    except Exception:

        return ""


def click_targets_quantity_increase(page, selector: str) -> bool:

    combined = _element_label(page, selector)

    if not combined:

        return False

    return any(x in combined for x in ("увелич", "increase"))


def click_targets_quantity_decrease(page, selector: str) -> bool:

    combined = _element_label(page, selector)

    if not combined:

        return False

    return any(x in combined for x in ("уменьш", "decrease"))


def click_targets_quantity_adjust(page, selector: str) -> bool:

    return click_targets_quantity_increase(page, selector) or click_targets_quantity_decrease(
        page, selector
    )


def click_targets_cart_nav(page, selector: str) -> bool:

    combined = _element_label(page, selector)

    if not combined:

        return False

    if any(x in combined for x in ("увелич", "уменьш", "increase", "decrease")):

        return False

    return "корзин" in combined


def _click_xy(page, x: float, y: float) -> None:

    page.evaluate(_SCROLL_POINT_JS, {"x": x, "y": y})

    page.wait_for_timeout(200)

    page.mouse.click(x, y)

    page.wait_for_timeout(650)


def _page_has_stepper(page) -> bool:

    try:

        st = page.evaluate(_STEPPER_QTY_JS)

        return st is not None

    except Exception:

        return False


def _try_single_plus_click(page, hint: str) -> bool:

    if _page_has_stepper(page):

        return False

    targets = page.evaluate(_FIND_PLUS_JS, hint)

    if not targets:

        return False

    t = targets[0]

    try:

        _click_xy(page, t["x"], t["y"])

    except Exception:

        return False

    return cart_is_filled(read_cart_state(page))


def click_add_to_cart(page, product_name: str = "") -> str:

    hint = (product_name or "").strip()

    cart0 = read_cart_state(page)

    if cart_is_filled(cart0) and cart_item_quantity(cart0) >= 1:

        return "корзина уже не пуста — повторное добавление пропущено"

    btn = page.evaluate(_FIND_ADD_TO_CART_BTN_JS)

    if btn:

        try:

            _click_xy(page, btn["x"], btn["y"])

            if cart_is_filled(read_cart_state(page)):

                return f"кнопка «В корзину» ({btn.get('label', '')})"

        except Exception:

            pass

    cards = page.evaluate(_FIND_PRODUCT_CARDS_JS, hint)

    if not cards and hint:

        cards = page.evaluate(_FIND_PRODUCT_CARDS_JS, "")

    if cards:

        card = cards[0]

        snippet = card.get("snippet") or ""

        try:

            if card.get("hasAddBtn"):

                _click_xy(page, card["plusX"], card["plusY"])

                if cart_is_filled(read_cart_state(page)):

                    return f"«+» на карточке в DOM ({snippet})"

            _click_xy(page, card["cardX"], card["cardY"])

            page.wait_for_timeout(500)

            if cart_is_filled(read_cart_state(page)):

                return f"карточка товара ({snippet})"

            btn2 = page.evaluate(_FIND_ADD_TO_CART_BTN_JS)

            if btn2:

                _click_xy(page, btn2["x"], btn2["y"])

                if cart_is_filled(read_cart_state(page)):

                    return f"«В корзину» на странице товара ({snippet})"

            if not _page_has_stepper(page) and _try_single_plus_click(page, hint):

                return f"«+» после карточки ({snippet})"

        except Exception:

            pass

    elif _try_single_plus_click(page, hint):

        return "один клик «+» в DOM"

    return (
        "add_to_cart: корзина не обновилась. dismiss_overlays, уточни product_name, take_screenshot."
    )
