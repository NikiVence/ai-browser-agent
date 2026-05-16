import base64
import os

from dotenv import load_dotenv
import httpx
from openai import (
    APIConnectionError,
    AuthenticationError,
    BadRequestError,
    OpenAI,
    PermissionDeniedError,
    RateLimitError,
)

from config import VISION_MAX_IMAGES_PER_STEP

load_dotenv()

_openrouter_client: OpenAI | None = None


def _openrouter_extra_headers() -> dict | None:

    headers = {}

    referer = os.getenv("OPENROUTER_HTTP_REFERER", "").strip()

    title = os.getenv("OPENROUTER_APP_TITLE", "ai-browser-agent").strip()

    if referer:

        headers["HTTP-Referer"] = referer

    if title:

        headers["X-OpenRouter-Title"] = title

    return headers or None


def _openrouter_proxy_url() -> str | None:

    for key in ("OPENROUTER_PROXY", "OPENROUTER_HTTPS_PROXY"):

        value = os.getenv(key, "").strip()

        if value:

            return value

    return None


def _geo_block_hint(model: str, raw: str) -> str | None:

    blob = raw.lower()

    if "unsupported_country" not in blob and "region" not in blob:

        return None

    proxy = _openrouter_proxy_url()

    lines = [
        "OpenRouter вернул geo-block (модель уходит к провайдеру вроде OpenAI, "
        "который не принимает запросы из вашего региона).",
        f"Сейчас модель: {model!r}.",
        "",
        "Что сделать (без глобального VPN на весь ПК):",
        "1) Поставь модели НЕ от OpenAI, например в .env:",
        "   OPENROUTER_MODEL=google/gemini-2.0-flash-001",
        "   OPENROUTER_VISION_MODEL=google/gemini-2.0-flash-001",
        "   (или deepseek/deepseek-chat — без vision; список: https://openrouter.ai/models )",
        "2) Либо прокси только для API агента (браузер локально, API через прокси):",
        "   OPENROUTER_PROXY=http://127.0.0.1:7890",
        "   — локальный VPN-клиент с HTTP-прокси (Clash, v2rayN и т.п.), split-tunnel: "
        "API-домены через прокси, остальной трафик — напрямую.",
        "3) Не включай системный VPN на весь трафик, если локальные сайты перестают открываться.",
    ]

    if proxy:

        lines.insert(3, f"Прокси из .env уже задан: {proxy}")

    else:

        lines.insert(3, "OPENROUTER_PROXY в .env пока не задан.")

    return "\n".join(lines)


def get_openrouter_client() -> OpenAI:

    global _openrouter_client

    if _openrouter_client is None:

        api_key = os.getenv("OPENROUTER_API_KEY", "").strip()

        if not api_key:

            raise RuntimeError(
                "Задай OPENROUTER_API_KEY в .env (ключ: https://openrouter.ai/keys)."
            )

        base_url = os.getenv(
            "OPENROUTER_BASE_URL",
            "https://openrouter.ai/api/v1",
        ).strip()

        if not base_url.endswith("/"):

            base_url = base_url + "/"

        timeout_s = float(os.getenv("OPENROUTER_TIMEOUT", "180"))

        extra = _openrouter_extra_headers()

        kwargs = {
            "api_key": api_key,
            "base_url": base_url,
            "timeout": timeout_s,
        }

        if extra:

            kwargs["default_headers"] = extra

        proxy = _openrouter_proxy_url()

        if proxy:

            kwargs["http_client"] = httpx.Client(proxy=proxy, timeout=timeout_s)

        _openrouter_client = OpenAI(**kwargs)

    return _openrouter_client


def _resolve_model(*, vision: bool) -> str:

    if vision:

        vm = os.getenv("OPENROUTER_VISION_MODEL", "").strip()

        if vm:

            return vm

    return os.getenv("OPENROUTER_MODEL", "google/gemini-2.0-flash-001").strip()


def _png_to_b64(png: bytes) -> str:

    return base64.standard_b64encode(png).decode("ascii")


def _message_text(msg) -> str:

    text = msg.content

    if not text and getattr(msg, "reasoning_content", None):

        text = msg.reasoning_content

    return (text or "").strip()


def _openrouter_chat(
    client: OpenAI,
    *,
    system_prompt: str,
    user_prompt: str,
    model: str,
    temperature: float,
    max_tokens: int,
    png_b64_list: list[str] | None = None,
) -> str:

    if png_b64_list:

        user_content: list = []

        for b64 in png_b64_list:

            user_content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{b64}"},
                }
            )

        user_content.append({"type": "text", "text": user_prompt})

        user_message = {"role": "user", "content": user_content}

    else:

        user_message = {"role": "user", "content": user_prompt}

    try:

        completion = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                user_message,
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )

    except RateLimitError as exc:

        raise RuntimeError(f"OpenRouter: лимит или квота (429): {exc}") from exc

    except AuthenticationError as exc:

        raise RuntimeError(
            "OpenRouter: ключ не принят (401). Проверь OPENROUTER_API_KEY в .env."
        ) from exc

    except PermissionDeniedError as exc:

        hint = _geo_block_hint(model, str(exc))

        if hint:

            raise RuntimeError(hint) from exc

        raise RuntimeError(f"OpenRouter: доступ запрещён (403): {exc}") from exc

    except BadRequestError as exc:

        raise RuntimeError(f"OpenRouter: неверный запрос (400): {exc}") from exc

    except APIConnectionError as exc:

        raise RuntimeError(
            "OpenRouter: нет соединения с API. Проверь сеть и OPENROUTER_BASE_URL."
        ) from exc

    return _message_text(completion.choices[0].message)


def ask_llm(system_prompt, user_prompt, *, vision_png_bytes: list[bytes] | None = None):

    vision_png_bytes = list(vision_png_bytes or [])

    if len(vision_png_bytes) > VISION_MAX_IMAGES_PER_STEP:

        vision_png_bytes = vision_png_bytes[-VISION_MAX_IMAGES_PER_STEP:]

    client = get_openrouter_client()

    has_vision = bool(vision_png_bytes)

    model = _resolve_model(vision=has_vision)

    temperature = float(os.getenv("OPENROUTER_TEMPERATURE", "0.2"))

    max_tokens = int(os.getenv("OPENROUTER_MAX_TOKENS", "2048"))

    png_b64_list = [_png_to_b64(p) for p in vision_png_bytes] if has_vision else None

    return _openrouter_chat(
        client,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        png_b64_list=png_b64_list,
    )
