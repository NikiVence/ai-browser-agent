import os
import re

from agent.action_fingerprint import action_fingerprint
from agent.cover_letter import compose_cover_letter_text
from agent.dom_subagent import run_dom_query
from agent.parser import parse_action
from agent.profile_context import (
    answer_indicates_resume_content,
    append_session_note,
    click_targets_apply_submission,
    click_targets_final_submit,
    expected_application_count,
    page_has_apply_modal,
    page_indicates_application_sent,
    profile_navigation_hint,
    query_targets_profile,
    session_notes_indicate_profile,
    task_needs_cover_letter,
    task_needs_profile_before_submit,
)
from agent.prompts import SYSTEM_PROMPT
from agent.tool_log import (
    log_assistant,
    log_dom_subagent_answer,
    log_dom_subagent_start,
    log_line,
    log_stopped,
    log_task_finished,
    log_tool_result,
    log_using_tool,
    payload_for_log,
    split_assistant_preamble,
)
from browser.cart_plus import cart_is_filled, read_cart_state
from browser.extractor import extract_page_context
from browser.overlays import click_blocked_reason
from browser.url_validate import (
    collect_urls_from_user_task,
    navigation_is_redundant,
    validate_agent_url,
)
from config import MAX_AGENT_STEPS
from llm.client import ask_llm


def _task_site_warning(user_task: str, url: str, task_urls: frozenset) -> str:

    if not task_urls:

        return ""

    from urllib.parse import urlparse

    cur_host = (urlparse(url or "").hostname or "").lower()

    if not cur_host:

        return (
            "⚠️ В задаче указаны URL, а текущая вкладка без адреса. "
            "Открой нужный сайт через navigate_to_url из задачи."
        )

    for task_url in task_urls:

        task_host = (urlparse(task_url).hostname or "").lower()

        if not task_host:

            continue

        if cur_host == task_host or cur_host.endswith("." + task_host) or task_host.endswith("." + cur_host):

            return ""

    return (
        f"⚠️ Хост вкладки ({cur_host}) не совпадает с URL из задачи ({', '.join(sorted(task_urls))}). "
        "Если это не та страница — navigate_to_url или go_back."
    )


def _canonical_action(action: dict) -> dict:

    alias = {
        "open_url": "navigate_to_url",
        "click": "click_element",
        "type": "type_text",
        "press": "press_key",
        "wait_ms": "wait",
        "screenshot": "take_screenshot",
        "dismiss_overlay": "dismiss_overlays",
        "close_modal": "dismiss_overlays",
        "add_to_cart_plus": "add_to_cart",
    }

    act = action.get("action")

    if act in alias:

        out = dict(action)

        out["action"] = alias[act]

        action = out

        act = action.get("action")

    if act == "add_to_cart":

        name = (action.get("product_name") or action.get("product") or "").strip()

        return {"action": "add_to_cart", "product_name": name}

    return action


def _tool_fingerprint(action: dict) -> str:

    if action.get("action") == "add_to_cart":

        name = (action.get("product_name") or "").strip()

        return f'{{"action":"add_to_cart","product_name":{name!r}}}'

    return action_fingerprint(action)


_MAX_ADD_TO_CART_PER_RUN = 3


def _guess_product_name_from_task(user_task: str) -> str:

    t = user_task.lower()

    patterns = (
        r"закаж(?:и|ить)(?:\s+мне)?\s+([^.,;]+)",
        r"добав(?:ь|ить)(?:\s+в\s+корзин[уа])?\s+([^.,;]+)",
        r"купи(?:ть)?\s+([^.,;]+)",
        r"полож(?:и|ить)\s+(?:в\s+корзин[уа]\s+)?([^.,;]+)",
    )

    for pat in patterns:

        m = re.search(pat, t)

        if m:

            return m.group(1).strip()[:120]

    return ""


def _task_expects_cart_items(user_task: str) -> bool:

    t = user_task.lower()

    markers = (
        "корзин",
        "корзину",
        "добав",
        "полож",
        "заказ",
        "купи",
        "cart",
        "лавк",
        "lavka",
        "хот-дог",
        "хот дог",
    )

    return any(m in t for m in markers)


class AgentLoop:

    def __init__(self, browser, actions):

        self.browser = browser

        self.actions = actions

    def run(self, user_task: str):

        self._user_task = user_task

        self._task_urls = collect_urls_from_user_task(user_task)

        self._pending_vision_pngs: list[bytes] = []

        self._session_notes = ""

        self._profile_context_ready = False

        self._applications_sent = 0

        self._expected_applications = expected_application_count(user_task)

        self._needs_profile_flow = task_needs_profile_before_submit(user_task)

        self._needs_cover_letter = task_needs_cover_letter(user_task)

        self._cover_letter_entered = False

        self._draft_cover_letter = ""

        last_error = None

        last_nav_url = None

        last_tool_fingerprint = None

        last_step_ok = None

        add_to_cart_calls = 0

        scroll_streak = 0

        expects_cart = _task_expects_cart_items(user_task)

        for step in range(1, MAX_AGENT_STEPS + 1):

            page_url = self.browser.page.url or ""

            context = extract_page_context(self.browser.page)

            site_warn = _task_site_warning(user_task, page_url, self._task_urls)

            if site_warn:

                context = f"{site_warn}\n{context}"

            vision_batch = self._pending_vision_pngs

            self._pending_vision_pngs = []

            error_block = ""

            if last_step_ok:

                error_block = f"""
LAST_STEP_OK:
{last_step_ok}
"""

                last_step_ok = None

            if last_error:

                error_block += f"""
LAST_TOOL_ERROR (исправь или обойди):
{last_error}
"""

                last_error = None

            session_block = ""

            if self._session_notes.strip():

                session_block = f"""
SESSION_NOTES (накоплено из query_dom на этой задаче):
{self._session_notes.strip()}
"""

            runtime_block = ""

            if self._needs_profile_flow and not self._profile_context_ready:

                runtime_block = "TASK_RUNTIME: PROFILE_CONTEXT: missing\n"

            elif self._needs_profile_flow:

                runtime_block = "TASK_RUNTIME: PROFILE_CONTEXT: gathered\n"

            if self._expected_applications is not None:

                runtime_block += (
                    f"APPLICATIONS_PROGRESS: {self._applications_sent}/"
                    f"{self._expected_applications} (по эвристике страницы после отправки).\n"
                )

            nav_hint = profile_navigation_hint(page_url, self._session_notes)

            if nav_hint:

                runtime_block += nav_hint + "\n"

            if page_has_apply_modal(self.browser.page):

                if self._draft_cover_letter:

                    runtime_block += "TASK_RUNTIME: DRAFT_COVER_LETTER: ready\n"

                elif self._needs_cover_letter and not self._cover_letter_entered:

                    runtime_block += "TASK_RUNTIME: COVER_TEXT: required\n"

            prompt = f"""USER TASK:
{user_task}
{runtime_block}{session_block}{error_block}
CURRENT PAGE:
{context}
"""

            response = ask_llm(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=prompt,
                vision_png_bytes=vision_batch if vision_batch else None,
            )

            pre, _ = split_assistant_preamble(response)

            if pre:

                log_assistant(pre)

            if os.getenv("AGENT_DEBUG_LLM", "").strip().lower() in ("1", "true", "yes"):

                print("LLM RAW:")

                print(response)

                print()

            action = parse_action(response)

            if not action:

                self._pending_vision_pngs = vision_batch + self._pending_vision_pngs

                last_error = "Модель не вернула валидный JSON с полем action."

                continue

            action = _canonical_action(action)

            act = action.get("action")

            if not act:

                self._pending_vision_pngs = vision_batch + self._pending_vision_pngs

                last_error = "В JSON нет поля action."

                continue

            if act == "done":

                if expects_cart and not cart_is_filled(read_cart_state(self.browser.page)):

                    last_error = (
                        "CART_SENSOR: appears_empty — в корзине нет товара. "
                        'Используй add_to_cart с product_name из результатов поиска, не только scroll.'
                    )

                    self._pending_vision_pngs = vision_batch + self._pending_vision_pngs

                    continue

                if (
                    self._expected_applications is not None
                    and self._applications_sent < self._expected_applications
                ):

                    last_error = (
                        f"Нужно минимум {self._expected_applications} отправок формы "
                        f"(зафиксировано {self._applications_sent}). "
                        "Продолжай по USER TASK."
                    )

                    self._pending_vision_pngs = vision_batch + self._pending_vision_pngs

                    continue

                if self._needs_profile_flow and not self._profile_context_ready:

                    last_error = (
                        "PROFILE_CONTEXT: missing в SESSION_NOTES — нужен query_dom по профилю."
                    )

                    self._pending_vision_pngs = vision_batch + self._pending_vision_pngs

                    continue

                log_using_tool("done", payload_for_log(action))

                log_task_finished(action.get("message", ""))

                return

            if act == "navigate_to_url":

                raw_target = (action.get("url") or "").strip()

                try:

                    validated = validate_agent_url(
                        raw_target,
                        allowed_urls=self._task_urls,
                    )

                except ValueError as exc:

                    self._pending_vision_pngs = vision_batch + self._pending_vision_pngs

                    last_error = str(exc)

                    continue

                cur = self.browser.page.url or ""

                if navigation_is_redundant(cur, validated):

                    log_line(
                        f"Skipping navigate_to_url: уже на этом сайте / совпадает URL "
                        f"(сейчас: {cur})"
                    )

                    last_error = (
                        "По URL в CURRENT PAGE переход не нужен. Не вызывай navigate_to_url с тем же адресом. "
                        "Следующий шаг выбери по свежему снимку страницы: другой ref из ARIA, другой инструмент "
                        "(другой ref, take_screenshot, query_dom, wait, scroll, go_back)."
                    )

                    self._pending_vision_pngs = vision_batch + self._pending_vision_pngs

                    continue

                if (
                    last_nav_url == validated
                    and not navigation_is_redundant(cur, validated)
                ):

                    last_error = (
                        f"Переход на тот же URL уже запрашивали, а адресная строка всё ещё «{cur}». "
                        "Не повторяй navigate_to_url. Сделай wait, take_screenshot, query_dom, go_back или проверь, "
                        "что управляется нужное окно/вкладка браузера."
                    )

                    self._pending_vision_pngs = vision_batch + self._pending_vision_pngs

                    continue

                last_nav_url = validated

            else:

                last_nav_url = None

            if action.get("safety") == "destructive":

                confirm = input(
                    "\nПотенциально деструктивное действие. "
                    "Введите YES чтобы выполнить: "
                ).strip()

                if confirm != "YES":

                    last_error = (
                        "Пользователь отклонил деструктивное действие; "
                        "предложи безопасный шаг или заверши с объяснением."
                    )

                    self._pending_vision_pngs = vision_batch + self._pending_vision_pngs

                    continue

            fp = _tool_fingerprint(action)

            if last_tool_fingerprint is not None and fp == last_tool_fingerprint:

                if act == "add_to_cart":

                    cart = read_cart_state(self.browser.page)

                    if cart_is_filled(cart):

                        last_error = (
                            "CART_SENSOR: items_present. Если цель достигнута — "
                            '{"action": "done", "message": "..."}.'
                        )

                    else:

                        last_error = (
                            "Повтор add_to_cart без эффекта. dismiss_overlays, уточни product_name "
                            "или take_screenshot."
                        )

                else:

                    last_error = (
                        "Ты дважды подряд выбрал один и тот же инструмент с теми же аргументами. "
                        "Снимок страницы после шага мог обновиться — ref из прошлого ответа может быть неверен "
                        "или элемент не принимает клик. Не повторяй тот же JSON: возьми другой ref из текущего "
                        "CURRENT PAGE или другой инструмент (add_to_cart, dismiss_overlays, take_screenshot, wait, query_dom)."
                    )

                self._pending_vision_pngs = vision_batch + self._pending_vision_pngs

                continue

            if act == "add_to_cart":

                if cart_is_filled(read_cart_state(self.browser.page)):

                    last_error = (
                        "CART_SENSOR: items_present. Если USER TASK выполнен — done; "
                        "иначе продолжай без повторного add_to_cart."
                    )

                    self._pending_vision_pngs = vision_batch + self._pending_vision_pngs

                    continue

                if add_to_cart_calls >= _MAX_ADD_TO_CART_PER_RUN:

                    last_error = (
                        f"Лимит add_to_cart ({_MAX_ADD_TO_CART_PER_RUN}). "
                        "Сверь CART_SENSOR; при успехе — done."
                    )

                    self._pending_vision_pngs = vision_batch + self._pending_vision_pngs

                    continue

            if act == "scroll" and expects_cart:

                if scroll_streak >= 2 and not cart_is_filled(read_cart_state(self.browser.page)):

                    last_error = (
                        "Много scroll подряд, корзина пуста. "
                        '{"action":"add_to_cart","product_name":"фрагмент названия из CURRENT PAGE"}'
                    )

                    self._pending_vision_pngs = vision_batch + self._pending_vision_pngs

                    continue

            if act == "click_element":

                block = click_blocked_reason(
                    self.browser.page,
                    action.get("selector") or "",
                )

                if block:

                    log_line("Skipping click: promo banner / top carousel")

                    last_error = block

                    if expects_cart:

                        last_error += (
                            ' Следующий шаг: {"action":"add_to_cart","product_name":"..."} '
                            "по названию товара из CURRENT PAGE."
                        )

                    self._pending_vision_pngs = vision_batch + self._pending_vision_pngs

                    continue

                sel = action.get("selector") or ""

                if (
                    self._needs_profile_flow
                    and not self._profile_context_ready
                    and click_targets_apply_submission(self.browser.page, sel)
                ):

                    last_error = (
                        "PROFILE_CONTEXT_REQUIRED: нужна сводка в SESSION_NOTES (query_dom по профилю)."
                    )

                    self._pending_vision_pngs = vision_batch + self._pending_vision_pngs

                    continue

                if (
                    self._needs_cover_letter
                    and self._profile_context_ready
                    and not self._cover_letter_entered
                    and click_targets_final_submit(self.browser.page, sel)
                ):

                    last_error = (
                        "COVER_LETTER_REQUIRED: compose_cover_letter, затем fill_cover_letter "
                        "или type_text в обязательное поле из ARIA."
                    )

                    self._pending_vision_pngs = vision_batch + self._pending_vision_pngs

                    continue

            log_using_tool(act, payload_for_log(action))

            try:

                step_ok, result_detail = self._execute_action(action)

                log_tool_result(result_detail, ok=True)

                if step_ok:

                    last_step_ok = step_ok

                last_tool_fingerprint = fp

                if act == "scroll":

                    scroll_streak += 1

                else:

                    scroll_streak = 0

                if act == "add_to_cart":

                    cart = read_cart_state(self.browser.page)

                    if cart_is_filled(cart):

                        add_to_cart_calls += 1

                        scroll_streak = 0

                        last_step_ok = (
                            "add_to_cart: CART_SENSOR items_present. "
                            "Если USER TASK выполнен — done."
                        )

                self.browser.adopt_new_tab_after_action()

                if act == "click_element" and page_indicates_application_sent(
                    self.browser.page
                ):

                    self._applications_sent += 1

                    self._cover_letter_entered = False

                    last_step_ok = (
                        f"Форма отправлена ({self._applications_sent}"
                        f"{f'/{self._expected_applications}' if self._expected_applications else ''}). "
                        "Проверь USER TASK — done или следующая запись."
                    )

            except Exception as exc:

                last_tool_fingerprint = None

                err = f"{type(exc).__name__}: {exc}"

                if act == "click_element":

                    err += ". См. PAGE_HINTS."

                    if expects_cart:

                        err += " Попробуй add_to_cart с product_name."

                if act == "add_to_cart":

                    err += " dismiss_overlays / уточни product_name / take_screenshot."

                log_tool_result(err, ok=False)

                last_error = err

        log_stopped(f"Достигнут лимит шагов ({MAX_AGENT_STEPS}).")

    def _execute_action(self, action: dict) -> tuple[str | None, str]:

        act = action["action"]

        if act == "navigate_to_url":

            url = action["url"]

            self.actions.open_url(
                url,
                allowed_urls=self._task_urls,
            )

            return None, f"Открыта страница: {url}"

        elif act == "click_element":

            sel = action["selector"]

            self.actions.click(
                sel,
                force=bool(action.get("force")),
            )

            return None, f"Клик по элементу {sel}."

        elif act == "add_to_cart":

            name = (action.get("product_name") or action.get("product") or "").strip()

            if not name:

                name = _guess_product_name_from_task(getattr(self, "_user_task", ""))

            label = self.actions.add_to_cart(name)

            cart = read_cart_state(self.browser.page)

            log_line(
                f"add_to_cart: {label}; CART_SENSOR="
                f"{'items_present' if cart_is_filled(cart) else 'appears_empty'}"
            )

            if not cart_is_filled(cart):

                raise RuntimeError(
                    "add_to_cart выполнен, но CART_SENSOR всё ещё empty."
                )

        elif act == "dismiss_overlays":

            msg = self.actions.dismiss_overlays()

            log_line(f"dismiss_overlays: {msg}")

        elif act == "press_key_page":

            self.actions.press_page_key(action["key"])

        elif act == "type_text":

            text = action.get("text") or ""

            if (
                not text.strip()
                and self._draft_cover_letter
                and self._needs_cover_letter
            ):

                text = self._draft_cover_letter

            self.actions.type(action["selector"], text)

            if self._needs_cover_letter and len(text.strip()) >= 80:

                self._cover_letter_entered = True

                return (
                    "type_text: длинный текст вставлен в поле формы.",
                    f"Введено {len(text)} символов в {action['selector']}.",
                )

            preview = text.strip()[:60]

            suffix = "…" if len(text.strip()) > 60 else ""

            return None, f"Введён текст «{preview}{suffix}» в {action['selector']}."

        elif act == "press_key":

            sel = action["selector"]

            key = action["key"]

            self.actions.press(sel, key)

            return None, f"Нажата клавиша {key!r} в {sel}."

        elif act == "wait":

            if "ms" in action:

                ms = int(action["ms"])

                self.actions.wait_ms(ms)

                return None, f"Пауза {ms} мс."

            seconds = float(action.get("seconds", 1.0))

            self.actions.wait_ms(int(seconds * 1000))

            return None, f"Пауза {seconds} с."

        elif act == "query_dom":

            q = (action.get("query") or "").strip()

            if not q:

                raise ValueError("query_dom: пустой query")

            log_dom_subagent_start(q)

            answer = run_dom_query(self.browser.page, q)

            log_dom_subagent_answer(answer)

            self._session_notes = append_session_note(self._session_notes, q, answer)

            if answer_indicates_resume_content(answer):

                self._profile_context_ready = session_notes_indicate_profile(
                    self._session_notes
                )

            elif query_targets_profile(q):

                self._profile_context_ready = False

            if self._profile_context_ready:

                return (
                    "query_dom: SESSION_NOTES обновлены. PROFILE_CONTEXT: gathered.",
                    "Ответ субагента сохранён в SESSION_NOTES (профиль собран).",
                )

            if query_targets_profile(q) and not answer_indicates_resume_content(answer):

                return (
                    "query_dom: в ответе мало данных профиля — смени страницу или уточни вопрос.",
                    "В ответе мало данных профиля.",
                )

            return (
                "query_dom: ответ добавлен в SESSION_NOTES.",
                "Ответ субагента сохранён в SESSION_NOTES.",
            )

        elif act == "compose_cover_letter":

            if self._needs_profile_flow and not self._profile_context_ready:

                raise RuntimeError(
                    "PROFILE_CONTEXT: missing — сначала query_dom по профилю в SESSION_NOTES."
                )

            title = (action.get("vacancy_title") or action.get("vacancy") or "").strip()

            log_line("Генерация сопроводительного письма…")

            letter = compose_cover_letter_text(
                session_notes=self._session_notes,
                page=self.browser.page,
                vacancy_title=title,
            )

            self._draft_cover_letter = letter

            log_line(f"Письмо: {len(letter)} символов")

            print(letter[:500] + ("…" if len(letter) > 500 else ""))

            print()

            return (
                f"compose_cover_letter: готово ({len(letter)} симв.). "
                "Следующий шаг: fill_cover_letter с selector из ARIA."
            )

        elif act == "fill_cover_letter":

            sel = (action.get("selector") or "").strip()

            if not sel:

                raise ValueError("fill_cover_letter: нужен selector (aria-ref поля письма)")

            if not self._draft_cover_letter:

                raise RuntimeError(
                    "Нет черновика. Сначала compose_cover_letter."
                )

            self.actions.type(sel, self._draft_cover_letter)

            self._cover_letter_entered = True

            return (
                "fill_cover_letter: текст вставлен. Можно отправить форму (ref из ARIA).",
                f"Письмо вставлено в {sel}.",
            )

        elif act == "take_screenshot":

            full_page = bool(action.get("full_page", False))

            path, png = self.actions.take_screenshot(full_page=full_page)

            self._pending_vision_pngs.append(png)

            return None, f"Screenshot saved as {path.name} ({path})"

        elif act == "scroll":

            direction = action.get("direction", "down")

            amount = action.get("amount_px", 800)

            self.actions.scroll(direction=direction, amount_px=amount)

            return None, f"Прокрутка {direction} на {amount} px."

        elif act == "go_back":

            self.actions.go_back()

            return None, "Переход назад в истории браузера."

        else:

            raise ValueError(f"Неизвестное действие: {act}")
