from browser.extractor import extract_page_context
from llm.client import ask_llm

COVER_LETTER_SYSTEM_PROMPT = """
Ты составляешь сопроводительное письмо на русском языке для отклика на вакансию.

Правила:
- Используй только факты из блока «Резюме / SESSION_NOTES». Не выдумывай опыт, компании и технологии.
- Если в резюме мало данных — пиши обобщённо, без конкретных цифр и названий, которых нет в тексте.
- Объём: примерно 120–220 слов, деловой тон, от первого лица.
- Упомяни релевантность к вакансии из блока «Вакансия».
- Без markdown, без заголовков, без JSON — только текст письма, готовый для вставки в форму.
"""


def compose_cover_letter_text(
    *,
    session_notes: str,
    page,
    vacancy_title: str = "",
) -> str:

    page_ctx = extract_page_context(page)

    notes = (session_notes or "").strip() or "(данные резюме ещё не собраны — пиши осторожно)"

    title = (vacancy_title or "").strip()

    user = f"""Резюме / SESSION_NOTES:
{notes}

Вакансия (если указана): {title or "—"}

Текущая страница (фрагмент):
{page_ctx}
"""

    return ask_llm(
        system_prompt=COVER_LETTER_SYSTEM_PROMPT,
        user_prompt=user,
    ).strip()
