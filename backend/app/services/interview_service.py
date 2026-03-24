from __future__ import annotations

from .workspace_service import (
    add_field_value,
    build_risks,
    current_field_map,
    get_latest_interview_session,
    save_interview_session,
    update_interview_answers,
)


QUESTION_BANK = {
    "work_scope": "如果只保留一个最适合写进论文的案例或流程场景，你会选哪一个？",
    "confidentiality_notes": "这个案例里哪些信息必须匿名，匿名要控制到什么粒度？",
    "mentor_preference_notes": "导师更看重哪一类内容，案例扎实、机制设计、方法应用还是行业问题？",
    "research_goal": "除了把论文写出来，你最终想形成什么可执行的改进结果或管理方案？",
}


def generate_interview(workspace_id: str) -> dict:
    current = current_field_map(workspace_id)
    risks = build_risks(workspace_id)
    triggers = []
    questions = []
    if not current.get("work_scope"):
        triggers.append("缺少代表性研究场景")
        questions.append(_question_item("work_scope"))
    if not current.get("confidentiality_notes"):
        triggers.append("保密边界不清")
        questions.append(_question_item("confidentiality_notes"))
    if not current.get("mentor_preference_notes"):
        triggers.append("导师偏好未确认")
        questions.append(_question_item("mentor_preference_notes"))
    if not current.get("research_goal"):
        triggers.append("研究目标过泛")
        questions.append(_question_item("research_goal"))

    conflict_risks = [risk for risk in risks if risk["id"].startswith("conflict:")]
    for risk in conflict_risks:
        field_key = risk["id"].split(":", 1)[1]
        if field_key in QUESTION_BANK and not any(question["key"] == field_key for question in questions):
            questions.append(_question_item(field_key, suffix="目前多个来源冲突，请你给出最终口径。"))

    questions = questions[:8]
    needs_interview = bool(questions)
    return save_interview_session(
        workspace_id=workspace_id,
        needs_interview=needs_interview,
        trigger_reasons=triggers or ["当前信息足够，可跳过访谈。"],
        questions=questions,
        status="open" if needs_interview else "skipped",
    )


def submit_interview_answers(workspace_id: str, answers: dict[str, str]) -> dict:
    session = get_latest_interview_session(workspace_id)
    if session is None:
        session = generate_interview(workspace_id)
    updated = update_interview_answers(workspace_id, answers)
    for key, value in answers.items():
        if not str(value).strip():
            continue
        add_field_value(
            workspace_id=workspace_id,
            field_key=key,
            value=value,
            source_label="访谈回答",
            source_kind="interview",
            source_uri="interview",
            source_grade="C",
            confidence=0.76,
            confirmed=True,
        )
    return updated


def _question_item(key: str, suffix: str = "") -> dict[str, str]:
    question = QUESTION_BANK[key]
    if suffix:
        question = f"{question} {suffix}"
    return {
        "key": key,
        "question": question,
        "placeholder": "请尽量给出具体对象、具体案例和可验证材料。",
    }
