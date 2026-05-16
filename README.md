# AI Browser Agent

Автономный агент управляет **видимым** браузером (Playwright) и выполняет многошаговые задачи по текстовой инструкции в терминале. На каждом шаге модель видит сжатый снимок страницы (ARIA + текст), выбирает **одно** действие в JSON и выполняет его, пока задача не завершена или не исчерпан лимит шагов.

Принцип: **нет сценариев под конкретные сайты** — только универсальные инструменты, `aria-ref` из текущего ARIA-снимка и рантайм-наблюдения (`PAGE_HINTS`, `CART_SENSOR`, `TASK_RUNTIME`).

## Стек

| Компонент | Технология |
|-----------|------------|
| Браузер | [Playwright](https://playwright.dev/python/) (Chromium / Chrome / Yandex / CDP) |
| LLM | [OpenRouter](https://openrouter.ai/) через OpenAI-совместимый API |
| Язык | Python 3.10+ |

## Быстрый старт

```powershell
cd D:\ai-browser-agent
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium

copy .env.example .env
# Заполните OPENROUTER_API_KEY в .env

cd app
..\venv\Scripts\python.exe main.py
```

После `TASK:` введите цель целиком, например: «Открой lavka.yandex.ru, найди хот-дог и положи в корзину, не оплачивай».

### CDP (рекомендуется для логинов)

1. Закройте Chrome, запустите с отладкой:

```powershell
& "C:\Program Files\Google\Chrome\Application\chrome.exe" `
  --remote-debugging-port=9222 `
  --user-data-dir="D:\chrome-profile"
```

2. Войдите на нужные сайты в этом окне.

3. В `.env`:

```env
PLAYWRIGHT_CDP_URL=http://127.0.0.1:9222
```

4. Запустите `main.py` — агент подключится к уже открытому Chrome (общие куки и сессии).

---

## Архитектура

```
┌─────────────┐     TASK      ┌──────────────┐
│  main.py    │──────────────▶│  AgentLoop   │
│  log_user   │               │  (до 40 шаг) │
└─────────────┘               └──────┬───────┘
                                       │
         ┌─────────────────────────────┼─────────────────────────────┐
         ▼                             ▼                             ▼
  extract_page_context          ask_llm (OpenRouter)          BrowserActions
  overlays → PAGE_HINTS         prompts.py                    Playwright page
  cart → CART_SENSOR            vision PNG (опционально)
         │                             │
         └──────── query_dom ──────────┘
                   dom_subagent.py
```

**Один шаг цикла:**

1. Снять контекст страницы (`extractor.py` + `overlays.py` + `cart_plus.py`).
2. Собрать промпт: `USER TASK`, `CURRENT PAGE`, `SESSION_NOTES`, `TASK_RUNTIME`, `LAST_STEP_OK` / `LAST_TOOL_ERROR`.
3. Запрос к LLM → парсинг JSON (`parser.py`).
4. Проверки рантайма (повторы, корзина, профиль, промо-клики).
5. Выполнение действия → лог `Input` / `Result` (`tool_log.py`).

---

## Инструменты агента

Модель возвращает JSON с полем `"action"`. Поддерживаются алиасы (`click` → `click_element`, `open_url` → `navigate_to_url` и т.д.).

| Action | Параметры | Назначение |
|--------|-----------|------------|
| `navigate_to_url` | `url` | Переход по HTTP(S) |
| `click_element` | `selector`, опц. `force` | Клик по `aria-ref=eN` |
| `type_text` | `selector`, `text` | Ввод в поле; при пустом `text` может подставиться черновик письма |
| `press_key` | `selector`, `key` | Клавиша в элементе (например Enter в поиске) |
| `press_key_page` | `key` | Клавиша на уровне страницы (Escape и т.д.) |
| `scroll` | `direction`, `amount_px` | Прокрутка колёсиком |
| `wait` | `seconds` или `ms` | Пауза |
| `go_back` | — | Назад в истории |
| `take_screenshot` | опц. `full_page` | PNG → vision на **следующем** шаге LLM |
| `dismiss_overlays` | — | Escape + типовые кнопки закрытия модалок |
| `add_to_cart` | опц. `product_name` | Клик по **карточке** товара и зоне «+» в DOM, если в ARIA нет ref |
| `query_dom` | `query` | Вопрос **субагенту** по странице; ответ → `SESSION_NOTES` |
| `compose_cover_letter` | опц. `vacancy_title` | LLM генерирует письмо из `SESSION_NOTES` |
| `fill_cover_letter` | `selector` | Вставка черновика в поле по `aria-ref` |
| `done` | `message` | Завершение задачи |

**Безопасность:** для оплаты, массового удаления и т.п. — `"safety": "destructive"`; в терминале нужно ввести `YES`.

---

## Логи в терминале

Формат вывода (иконки + структура):

```
👤 You:
зайди на лавку и закажи хот-дог…

🤖 Assistant:
Открываю сайт…

🔧 Using tool: navigate_to_url

Input:
{
  "url": "https://lavka.yandex.ru"
}

Result: Открыта страница: https://lavka.yandex.ru

🔍 DOM Sub-agent: Processing query…
…

✅ TASK FINISHED
…
```

| Переменная | Эффект |
|------------|--------|
| `AGENT_LOG_COLOR=0` или `NO_COLOR=1` | Без ANSI-цветов |
| `AGENT_LOG_VERBOSE=1` | Доп. служебные строки + превью длинных текстов |
| `AGENT_DEBUG_LLM=1` | Сырой ответ модели в консоль |

---

## Рантайм (без подсказок «куда жать» в промпте)

| Механизм | Где | Что делает |
|----------|-----|------------|
| `PAGE_HINTS` | `overlays.py` | `BLOCKING_OVERLAY`, `TOP_PROMO_REGIONS`, `ADD_TO_CART_BUTTONS_DETECTED` |
| `CART_SENSOR` | `cart_plus.py` | Пустая / заполненная корзина по тексту и панели |
| `SESSION_NOTES` | `agent_loop.py` | Накопление ответов `query_dom` |
| `TASK_RUNTIME` | `agent_loop.py` | Короткие статусы: `PROFILE_CONTEXT`, `COVER_TEXT`, `DRAFT_COVER_LETTER` |
| Повтор action | `action_fingerprint.py` | Блок повтора того же JSON подряд |
| Промо-клик | `overlays.py` | Блок клика по верхним баннерам (не карточки с ₽) |
| Профиль / отклики | `profile_context.py` | До сбора профиля — блок отправки формы; счётчик откликов для `done` |
| Корзина | `agent_loop.py` | `done` и лимиты, если в задаче есть «корзина/заказ»; анти-scroll без `add_to_cart` |

`add_to_cart`: сначала клик по карточке с ценой, затем по координатам «+»; `product_name` можно не указыать — подставится из фразы «закажи …» в TASK.

---

## Управление контекстом (токены)

| Параметр | По умолчанию | Описание |
|----------|--------------|----------|
| `PAGE_ARIA_DEPTH` | 12 | Глубина ARIA-снимка |
| `MAX_ARIA_SNAPSHOT_CHARS` | 14 000 | Обрезка ARIA |
| `MAX_BODY_FALLBACK_CHARS` | 2 500 | Обрезка `body` innerText |
| `ARIA_SNAPSHOT_TIMEOUT_MS` | 45000 | Таймаут снимка на тяжёлых страницах |
| `VISION_MAX_IMAGES_PER_STEP` | 4 | PNG после `take_screenshot` в одном запросе |

Полная HTML-страница в LLM **не** отправляется.

---

## Переменные окружения

Скопируйте `.env.example` → `.env`.

### OpenRouter

| Переменная | Описание |
|------------|----------|
| `OPENROUTER_API_KEY` | Ключ API (обязательно) |
| `OPENROUTER_MODEL` | Модель для текста (по умолчанию `google/gemini-2.0-flash-001`) |
| `OPENROUTER_VISION_MODEL` | Модель при скриншотах |
| `OPENROUTER_PROXY` | HTTP-прокси только для API (браузер локально) |
| `OPENROUTER_TEMPERATURE` | Температура (по умолчанию 0.2) |
| `OPENROUTER_MAX_TOKENS` | Лимит ответа |
| `OPENROUTER_TIMEOUT` | Таймаут запроса, с |
| `OPENROUTER_BASE_URL` | Базовый URL API |

### Браузер

| Переменная | Описание |
|------------|----------|
| `PLAYWRIGHT_CDP_URL` | Подключение к Chrome, напр. `http://127.0.0.1:9222` |
| `PLAYWRIGHT_FOLLOW_NEWEST_TAB` | `1` — переключение на новую вкладку после клика |
| `PLAYWRIGHT_CHANNEL` | `chrome`, `msedge`, `yandex` |
| `PLAYWRIGHT_EXECUTABLE` | Полный путь к `browser.exe` |
| `PLAYWRIGHT_GOTO_WAIT` | `domcontentloaded` и др. |
| `PLAYWRIGHT_BLINK_AUTOMATION_DISABLED` | `1` — меньше признаков automation |

Профиль Playwright по умолчанию: `D:\ai-browser-agent\.pw-user-data` (см. `config.py`).

### Прочее

| Переменная | Описание |
|------------|----------|
| `AGENT_SCREENSHOT_DIR` | Каталог PNG (по умолчанию `.agent-screenshots/`) |
| `BROWSER_STRICT_ROOT_ONLY_HOSTS` | Список хостов через запятую — навигация только на корень `/` |

---

## Структура репозитория

```
ai-browser-agent/
├── README.md
├── requirements.txt          # python-dotenv, playwright, openai
├── .env.example
├── .gitignore
├── .pw-user-data/            # профиль Playwright (не в git)
├── .agent-screenshots/       # PNG агента (не в git)
└── app/
    ├── main.py               # точка входа, TASK:, log_user
    ├── config.py             # лимиты ARIA, пути, MAX_AGENT_STEPS=40
    │
    ├── agent/
    │   ├── agent_loop.py     # главный цикл, рантайм-гейты, выполнение tools
    │   ├── prompts.py        # SYSTEM_PROMPT + DOM_SUBAGENT_SYSTEM_PROMPT
    │   ├── parser.py         # извлечение и починка JSON из ответа LLM
    │   ├── tool_log.py       # формат логов 👤🤖🔧 Result
    │   ├── dom_subagent.py   # query_dom → отдельный LLM-запрос
    │   ├── cover_letter.py   # compose_cover_letter (генерация текста)
    │   ├── profile_context.py # профиль, отклики, письма (эвристики DOM/URL)
    │   └── action_fingerprint.py # отпечаток action против зацикливания
    │
    ├── browser/
    │   ├── browser.py        # launch persistent / CDP, follow newest tab
    │   ├── actions.py        # обёртки Playwright (click, type, scroll…)
    │   ├── extractor.py      # ARIA snapshot + body fallback
    │   ├── overlays.py       # PAGE_HINTS, dismiss_overlays, блок промо-кликов
    │   ├── cart_plus.py      # add_to_cart, CART_SENSOR
    │   └── url_validate.py   # валидация URL, URL из TASK
    │
    └── llm/
        └── client.py         # OpenRouter client, vision, geo-block подсказки
```

---

## Примеры задач

Формулируйте **цель**, не пошаговый план:

| Задача | Заметки |
|--------|---------|
| Закажи хот-дог на сайте доставки, только в корзину | `add_to_cart`, CDP с уже выбранным адресом |
| Найди 3 вакансии AI-инженера и откликнись, изучив резюме | CDP + логин; `query_dom` → `compose_cover_letter` → `fill_cover_letter` |
| Удали спам в почте за неделю | CDP с открытой почтой |
| Найди тарифы на сайте X и кратко перескажи | `query_dom` / `done` |

---

## Соответствие ТЗ

| Требование | Реализация |
|------------|------------|
| Видимый браузер | `headless=False` |
| Постоянная сессия | `.pw-user-data` или CDP |
| Claude / OpenAI | OpenRouter (`OPENROUTER_MODEL`) |
| Автономность | Цикл до 40 шагов |
| Контекст без целой страницы | ARIA + лимиты + `query_dom` |
| Субагент | `dom_subagent.py` |
| Ошибки | `LAST_TOOL_ERROR`, смена стратегии |
| Безопасность | `safety: destructive` → `YES` |
| Без рецептов сайтов | Промпты только про инструменты; селекторы — `aria-ref` из снимка |
| Без data-qa / жёстких URL | Нет в коде и промптах |

**Не входит:** MCP-сервер, готовые сценарии «сначала /vacancies, потом кнопка Заказать».

---

## Устранение неполадок

| Симптом | Что проверить |
|---------|----------------|
| Geo-block OpenAI на OpenRouter | `OPENROUTER_MODEL` на Gemini/DeepSeek или `OPENROUTER_PROXY` |
| ARIA долго / пустой | `ARIA_SNAPSHOT_TIMEOUT_MS`, `take_screenshot` |
| Не добавляет в корзину | `add_to_cart` с `product_name`; `dismiss_overlays`; `CART_SENSOR` в логе |
| Отклик без письма | `compose_cover_letter` → `fill_cover_letter`; `PROFILE_CONTEXT` в TASK_RUNTIME |
| CDP не подключается | Chrome запущен с `--remote-debugging-port=9222`, одно окно |
| `NameError: log_step` | Обновите `agent_loop.py` до актуальной версии |

---

## Развитие

Идеи: лимит шагов через env, явный запрос данных у пользователя mid-run, оценка успеха шага без эвристик текста кнопок, опциональный headless для CI.

Проект учебный / демонстрационный; используйте на свой риск на реальных аккаунтах и платёжных формах.
