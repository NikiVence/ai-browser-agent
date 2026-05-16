import json
import os
import sys
from typing import Any, Mapping


def _use_color() -> bool:

    if os.getenv("AGENT_LOG_COLOR", "").strip().lower() in ("0", "false", "no"):

        return False

    if os.getenv("NO_COLOR", "").strip():

        return False

    return sys.stdout.isatty()


def _c(code: str, text: str) -> str:

    if not _use_color():

        return text

    return f"\033[{code}m{text}\033[0m"


def _dim(text: str) -> str:

    return _c("2", text)


def _bold(text: str) -> str:

    return _c("1", text)


def _cyan(text: str) -> str:

    return _c("36", text)


def _green(text: str) -> str:

    return _c("32", text)


def _yellow(text: str) -> str:

    return _c("33", text)


def _red(text: str) -> str:

    return _c("31", text)


def _print_block() -> None:

    print(flush=True)


def split_assistant_preamble(raw: str) -> tuple[str, str]:

    text = (raw or "").strip()

    idx = text.find("{")

    if idx == -1:

        return "", text

    return text[:idx].strip(), text[idx:]


def payload_for_log(action: Mapping[str, Any]) -> dict:

    return {
        k: v
        for k, v in action.items()
        if k != "action"
    }


def log_user(message: str) -> None:

    text = (message or "").strip()

    if not text:

        return

    _print_block()

    print(f"👤 {_bold('You:')}", flush=True)

    print(text, flush=True)

    _print_block()


def log_assistant(message: str) -> None:

    text = (message or "").strip()

    if not text:

        return

    _print_block()

    print(f"🤖 {_bold('Assistant:')}", flush=True)

    print(text, flush=True)

    _print_block()


def log_step(step: int, total: int, *, phase: str = "") -> None:

    label = f"── Step {step}/{total} ──"

    if phase:

        label += f"  {_dim(phase)}"

    _print_block()

    print(_dim(label), flush=True)


def log_thinking(message: str) -> None:

    print(_dim(f"  … {message}"), flush=True)


def log_using_tool(name: str, payload: dict | None = None) -> None:

    _print_block()

    print(f"🔧 {_bold('Using tool:')} {_cyan(name)}", flush=True)

    _print_block()

    print(_bold("Input:"), flush=True)

    body = payload if payload else {}

    print(
        json.dumps(body, ensure_ascii=False, indent=2),
        flush=True,
    )


def log_tool_result(message: str, *, ok: bool = True) -> None:

    text = (message or "").strip()

    if not text:

        text = "OK"

    _print_block()

    prefix = _green("Result:") if ok else _red("Result:")

    print(f"{prefix} {text}", flush=True)

    _print_block()


def log_tool_skipped(reason: str) -> None:

    log_tool_result(reason, ok=False)


def log_dom_subagent_start(query: str = "") -> None:

    _print_block()

    print(f"🔍 {_bold('DOM Sub-agent:')} Processing query…", flush=True)

    if query.strip():

        print(_dim(query.strip()), flush=True)


def log_dom_subagent_answer(answer: str) -> None:

    text = (answer or "").strip()

    _print_block()

    print(f"🔍 {_bold('DOM Sub-agent:')}", flush=True)

    if text:

        print(text, flush=True)

    _print_block()


def log_task_finished(message: str) -> None:

    _print_block()

    print(f"✅ {_bold('TASK FINISHED')}", flush=True)

    if (message or "").strip():

        print(message.strip(), flush=True)

    _print_block()


def log_stopped(message: str) -> None:

    _print_block()

    print(f"⏹ {_yellow(message)}", flush=True)

    _print_block()


def log_line(message: str) -> None:

    """Внутренние сообщения рантайма (редко)."""

    if os.getenv("AGENT_LOG_VERBOSE", "").strip().lower() in ("1", "true", "yes"):

        print(_dim(message), flush=True)


def format_action_result(
    action: str,
    *,
    detail: str = "",
    error: str = "",
) -> tuple[str, bool]:

    if error:

        return error, False

    defaults = {
        "navigate_to_url": "Страница открыта.",
        "click_element": "Клик выполнен.",
        "type_text": "Текст введён.",
        "press_key": "Клавиша нажата.",
        "press_key_page": "Клавиша нажата на странице.",
        "wait": "Пауза завершена.",
        "scroll": "Прокрутка выполнена.",
        "go_back": "Назад в истории.",
        "dismiss_overlays": "Обработка оверлеев завершена.",
        "take_screenshot": "Скриншот сохранён.",
        "add_to_cart": "Добавление в корзину выполнено.",
        "query_dom": "Ответ субагента получен.",
        "compose_cover_letter": "Письмо сгенерировано.",
        "fill_cover_letter": "Письмо вставлено в поле.",
        "done": "Задача завершена.",
    }

    msg = (detail or defaults.get(action, "OK")).strip()

    return msg, True
