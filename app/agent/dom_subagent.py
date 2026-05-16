from agent.prompts import DOM_SUBAGENT_SYSTEM_PROMPT
from browser.extractor import extract_page_context
from llm.client import ask_llm


def run_dom_query(page, query: str) -> str:

    context = extract_page_context(page)

    user = f"""ВОПРОС ПО СТРАНИЦЕ:
{query}

ТЕКУЩЕЕ СОСТОЯНИЕ СТРАНИЦЫ:
{context}
"""

    return ask_llm(
        system_prompt=DOM_SUBAGENT_SYSTEM_PROMPT,
        user_prompt=user,
    )
