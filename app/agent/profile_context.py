import re


def task_needs_cover_letter(user_task: str) -> bool:

    t = user_task.lower()

    if any(x in t for x in ("сопровод", "письм", "cover letter")):

        return True

    return task_needs_profile_before_submit(user_task)


def task_needs_profile_before_submit(user_task: str) -> bool:

    t = user_task.lower()

    needs_text = any(
        x in t
        for x in (
            "резюме",
            "resume",
            "сопровод",
            "cover letter",
            "письм",
            "профил",
            "profile",
            "изуч",
        )
    )

    needs_submit = any(
        x in t
        for x in (
            "отклик",
            "ваканс",
            "apply",
            "заявк",
            "отправ",
        )
    )

    return needs_text and needs_submit


def expected_application_count(user_task: str) -> int | None:

    t = user_task.lower()

    m = re.search(r"(\d+)\s*(?:подходящ|ваканс|отклик|заявк)", t)

    if m:

        return max(1, int(m.group(1)))

    if re.search(r"\b(?:две|два)\b", t) and any(
        x in t for x in ("ваканс", "отклик")
    ):

        return 2

    return None


def query_targets_profile(query: str) -> bool:

    q = query.lower()

    return any(
        x in q
        for x in (
            "резюме",
            "resume",
            "профил",
            "profile",
            "опыт",
            "навык",
            "стек",
            "cv",
            "биограф",
        )
    )


def answer_looks_like_vacancy_list_only(text: str) -> bool:

    low = (text or "").lower()

    if "ваканс" not in low and "vacancy" not in low:

        return False

    resume_markers = (
        "опыт работ",
        "навык",
        "обязанност",
        "стек",
        "python",
        "django",
        "fastapi",
        "postgresql",
        "образован",
        "работал в",
        "месяц",
        "год",
    )

    return sum(1 for m in resume_markers if m in low) < 2


def answer_indicates_resume_content(answer: str) -> bool:

    if len((answer or "").strip()) < 120:

        return False

    if answer_looks_like_vacancy_list_only(answer):

        return False

    low = answer.lower()

    markers = (
        "опыт",
        "навык",
        "skill",
        "python",
        "backend",
        "работал",
        "стек",
        "должност",
        "компани",
        "проект",
        "образован",
        "обязанност",
    )

    return sum(1 for m in markers if m in low) >= 2


def session_notes_indicate_profile(notes: str) -> bool:

    if len(notes.strip()) < 180:

        return False

    if answer_looks_like_vacancy_list_only(notes):

        return False

    low = notes.lower()

    markers = (
        "опыт",
        "навык",
        "skill",
        "python",
        "backend",
        "работал",
        "стек",
        "должност",
        "компани",
        "проект",
        "образован",
    )

    return sum(1 for m in markers if m in low) >= 2


def is_resume_list_page(url: str) -> bool:

    u = (url or "").lower()

    if "hh.ru" not in u and "hh.kz" not in u:

        return False

    if "/resume/" in u and "/applicant/resumes" not in u:

        return False

    return "/applicant/resumes" in u or u.rstrip("/").endswith("/resumes")


def is_resume_detail_page(url: str) -> bool:

    u = (url or "").lower()

    return bool(re.search(r"hh\.(ru|kz)/resume/[0-9a-z-]+", u))


def page_has_apply_modal(page) -> bool:

    try:

        body = (page.locator("body").inner_text(timeout=3000) or "").lower()

    except Exception:

        return False

    return "отклик на вакансию" in body and "сопроводительное письмо" in body


def profile_navigation_hint(url: str, notes: str) -> str:

    if is_resume_list_page(url) and not session_notes_indicate_profile(notes):

        return (
            "PROFILE_CONTEXT: на странице, похоже, только список без полного текста профиля."
        )

    if is_resume_detail_page(url) and not session_notes_indicate_profile(notes):

        return "PROFILE_CONTEXT: детальная страница профиля — данных в SESSION_NOTES пока мало."

    return ""


def append_session_note(notes: str, query: str, answer: str, *, max_chars: int = 12_000) -> str:

    block = f"""--- query_dom ---
Q: {query.strip()}
A: {answer.strip()}
"""

    combined = (notes + "\n" + block).strip()

    if len(combined) <= max_chars:

        return combined

    return combined[-max_chars:]


def click_targets_apply_submission(page, selector: str) -> bool:

    s = (selector or "").strip()

    if not s:

        return False

    if s.startswith("aria-ref="):

        loc = page.locator(s).first

    elif len(s) > 1 and s[0] == "e" and s[1:].isdigit():

        loc = page.locator(f"aria-ref={s}").first

    else:

        loc = page.locator(s).first

    try:

        text = (loc.inner_text(timeout=2500) or "").lower()

        label = (loc.get_attribute("aria-label") or "").lower()

        combined = f"{text} {label}"

    except Exception:

        return False

    if any(x in combined for x in ("отправлен", "уже отклик", "откликнулись")):

        return False

    apply_markers = (
        "откликнуться",
        "отправить отклик",
        "отправить",
        "apply now",
        " apply",
    )

    return any(m in combined for m in apply_markers)


def click_targets_final_submit(page, selector: str) -> bool:

    s = (selector or "").strip()

    if not s:

        return False

    if s.startswith("aria-ref="):

        loc = page.locator(s).first

    elif len(s) > 1 and s[0] == "e" and s[1:].isdigit():

        loc = page.locator(f"aria-ref={s}").first

    else:

        loc = page.locator(s).first

    try:

        combined = (
            (loc.inner_text(timeout=2500) or "")
            + " "
            + (loc.get_attribute("aria-label") or "")
        ).lower()

    except Exception:

        return False

    return any(
        x in combined
        for x in (
            "отправить отклик",
            "отправить",
            "submit",
            "подтвердить",
        )
    ) and "откликнуться" not in combined


def page_indicates_application_sent(page) -> bool:

    try:

        body = (page.locator("body").inner_text(timeout=4000) or "").lower()

    except Exception:

        return False

    return any(
        x in body
        for x in (
            "отклик отправлен",
            "вы откликнулись",
            "откликнулись на вакансию",
            "response sent",
        )
    )
