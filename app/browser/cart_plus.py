"""Добавление в корзину: карточка товара → «+», проверка CART_SENSOR."""

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
      return { empty: false, filled: true, reason: 'cart_panel', snippet: pt.slice(0, 120) };
    }
  }
  if (/Оформить/i.test(allText) && !/Добавьте что-нибудь/i.test(allText)) {
    const m = allText.match(/(\\d+[\\s\\u00a0]*₽)/);
    if (m) {
      return { empty: false, filled: true, reason: 'checkout_cta', snippet: m[0] };
    }
  }
  return { empty: true, filled: false, reason: 'assume_empty' };
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
    cards.push({
      score: sc,
      snippet: t.slice(0, 90),
      cardX: r.x + Math.min(r.width * 0.42, r.width - 40),
      cardY: r.y + r.height * 0.45,
      plusX: r.right - Math.min(28, r.width * 0.12),
      plusY: r.y + r.height * 0.55,
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
    if (raw === '+' || raw === '＋' || raw === '−') return true;
    const al = (el.getAttribute('aria-label') || '').toLowerCase();
    if (al.includes('добав') || al.includes('корзин') || al.includes('увелич')) return true;
    const cls = (el.className || '').toString().toLowerCase();
    if (/add|plus|counter|increment|basket/.test(cls) && el.tagName === 'BUTTON') return true;
    const r = el.getBoundingClientRect();
    if (r.width >= 20 && r.width <= 56 && r.height >= 20 && r.height <= 56) {
      if (raw === '' && el.querySelector('svg')) return true;
    }
    return false;
  };

  const out = [];
  const seen = new Set();
  const nodes = document.querySelectorAll(
    'button, [role="button"], a, div, span, [class*="Add" i], [class*="Counter" i], [class*="Plus" i]'
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


def read_cart_state(page) -> dict:

    try:

        return page.evaluate(_CART_STATE_JS)

    except Exception:

        return {"empty": True, "filled": False, "reason": "error"}


def cart_is_filled(cart: dict) -> bool:

    return bool(cart.get("filled"))


def format_cart_status_line(cart: dict) -> str:

    if cart_is_filled(cart):

        snip = cart.get("snippet") or ""

        return f"CART_SENSOR: items_present ({cart.get('reason', '')}) {snip}\n"

    return f"CART_SENSOR: appears_empty ({cart.get('reason', 'unknown')})\n"


def _click_xy(page, x: float, y: float) -> None:

    page.evaluate(_SCROLL_POINT_JS, {"x": x, "y": y})

    page.wait_for_timeout(200)

    page.mouse.click(x, y)

    page.wait_for_timeout(500)


def _try_plus_clicks(page, hint: str) -> bool:

    for t in page.evaluate(_FIND_PLUS_JS, hint)[:6]:

        try:

            _click_xy(page, t["x"], t["y"])

            if cart_is_filled(read_cart_state(page)):

                return True

        except Exception:

            continue

    return False


def click_add_to_cart(page, product_name: str = "") -> str:

    hint = (product_name or "").strip()

    cards = page.evaluate(_FIND_PRODUCT_CARDS_JS, hint)

    if not cards and hint:

        cards = page.evaluate(_FIND_PRODUCT_CARDS_JS, "")

    last_snippet = ""

    for card in cards[:4]:

        last_snippet = card.get("snippet") or last_snippet

        try:

            _click_xy(page, card["cardX"], card["cardY"])

            if cart_is_filled(read_cart_state(page)):

                return f"клик по карточке ({last_snippet})"

            _click_xy(page, card["plusX"], card["plusY"])

            if cart_is_filled(read_cart_state(page)):

                return f"карточка + зона «+» ({last_snippet})"

            if _try_plus_clicks(page, hint):

                return f"карточка, затем «+» ({last_snippet})"

            url_before = page.url

            page.wait_for_timeout(400)

            if page.url != url_before:

                if _try_plus_clicks(page, hint):

                    return f"страница товара + «+» ({last_snippet})"

                try:

                    page.go_back(wait_until="domcontentloaded")

                    page.wait_for_timeout(500)

                except Exception:

                    pass

        except Exception:

            continue

    if _try_plus_clicks(page, hint):

        return "клик по «+» в DOM"

    return (
        "add_to_cart: корзина не обновилась. dismiss_overlays, уточни product_name, take_screenshot."
    )
