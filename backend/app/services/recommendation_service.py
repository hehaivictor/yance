from __future__ import annotations

import re
import uuid
from typing import Any

from ..core.evidence_grounding import (
    build_grounding_context,
    collect_grounding_reasons,
)
from ..core.legacy_bridge import build_mentor_fit
from ..core.llm import is_enabled
from ..core.paper_reasoning import (
    diagnose_selection,
    generate_candidate_drafts,
    generate_candidate_recommendations,
    generate_candidate_scores,
)
from ..core.profile_rules import (
    anonymized_subject_name,
    candidate_recommendation_copy,
    fallback_title,
    filter_title_candidates,
    has_builtin_guide,
    privacy_safe_text,
)
from .workspace_service import (
    current_field_map,
    get_workspace_row,
    list_evidence_items,
    load_profile,
    replace_title_candidates,
)


TOPIC_PATTERNS = [
    ("AI智能体落地", ["ai", "智能体", "大模型", "落地", "实施"]),
    ("工业软件AI产品化", ["产品化", "平台化", "工业软件", "产品"]),
    ("组织协同机制", ["协同", "组织", "流程", "跨部门"]),
    ("知识管理与交付", ["知识库", "知识管理", "交付", "复用"]),
    ("数据准备与治理", ["数据", "治理", "接口", "可信"]),
    ("价值评估体系", ["价值", "评估", "roi", "效益"]),
]

INDUSTRY_HINTS = ["工业", "制造", "工艺", "软件", "PLM", "MBD"]
COLLAB_HINTS = ["协同", "流程", "交付", "跨部门", "组织"]
VALUE_HINTS = ["价值", "评估", "ROI", "效益", "验收"]
DATA_HINTS = ["数据", "知识", "规则", "知识库", "治理", "接口"]
AI_TITLE_HINTS = ["AI", "智能体", "大模型"]
DATA_TITLE_HINTS = ["数据", "知识库", "知识", "治理", "交付"]
VALUE_TITLE_HINTS = ["价值评估", "价值", "ROI", "效益"]


def recommend_titles(workspace_id: str) -> list[dict[str, Any]]:
    _ensure_external_grounding(workspace_id)
    current = current_field_map(workspace_id)
    evidence_items = list_evidence_items(workspace_id)
    workspace = get_workspace_row(workspace_id)
    profile = load_profile(workspace["school_profile"])
    grounding = build_grounding_context(current, evidence_items)
    diagnosis = diagnose_selection(current, profile, grounding, evidence_items)
    candidates = _generate_candidates(current, profile, grounding, evidence_items, diagnosis)
    titles = [item["title"] for item in candidates]
    mentor_scores = _mentor_fit_scores(current, evidence_items, titles, grounding)
    grounding_reasons = collect_grounding_reasons(grounding)
    context_penalty, context_reasons, context_tag = _context_sufficiency(current, evidence_items)
    company_name = str(current.get("company_name") or "")
    confidentiality = str(current.get("confidentiality_notes") or "")
    ranked = []
    model_scores = generate_candidate_scores(
        current,
        profile,
        grounding,
        evidence_items,
        diagnosis,
        candidates,
    )
    if is_enabled() and not model_scores:
        raise RuntimeError("模型评分失败，未返回候选题评分结果。")
    for candidate in candidates:
        title = candidate["title"]
        school_fit, school_reasons = _school_fit(title, profile)
        mentor_fit, mentor_reasons = mentor_scores.get(title, (58.0, ["缺少明确导师方向证据，按中性值处理。"]))
        role_fit, role_reasons = _role_fit(title, current, grounding)
        evidence_fit, evidence_reasons = _evidence_fit(evidence_items, profile, grounding)
        confidentiality_fit, confidentiality_reasons = _confidentiality_fit(title, current)
        audit_reasons = _audit_reasons(profile, grounding, diagnosis)
        fallback_total = round(
            school_fit * 0.22
            + mentor_fit * 0.22
            + role_fit * 0.24
            + evidence_fit * 0.2
            + confidentiality_fit * 0.12
            - context_penalty,
            1,
        )
        scored = model_scores.get(title) or model_scores.get(candidate.get("title") or "")
        if is_enabled() and not scored:
            raise RuntimeError(f"模型未返回候选题《{title}》的评分结果。")
        total = float(scored["score"]) if scored else fallback_total
        caution = "需要补强资料和冲突字段后再正式写作。"
        if diagnosis.get("missing_information"):
            caution = "当前仍需补充 " + "、".join(str(item) for item in diagnosis.get("missing_information")[:3]) + "。"
        risk_tags = []
        if total >= 82:
            pass
        elif total >= 70:
            risk_tags.append("需收敛")
        else:
            caution = "当前更像概念题而不是可落地开题题，暂不建议直接进入正文。"
            risk_tags.append("不建议直接采用")
        if confidentiality_fit < 65:
            risk_tags.append("保密风险")
        if evidence_fit < 65:
            risk_tags.append("资料不足")
        if context_tag:
            risk_tags.append(context_tag)
        display_title = privacy_safe_text(title, company_name, confidentiality)
        display_reasons = _sanitize_reasons(
            ([str(scored.get("short_comment") or "").strip()] if scored and str(scored.get("short_comment") or "").strip() else [])
            + context_reasons
            + role_reasons
            + mentor_reasons
            + grounding_reasons
            + evidence_reasons
            + confidentiality_reasons
            + audit_reasons
            + _distinct_school_reasons(school_reasons),
            company_name,
            confidentiality,
        )
        ranked.append(
            {
                "id": str(uuid.uuid4()),
                "title": display_title,
                "raw_title": title,
                "angle": candidate.get("angle", ""),
                "school_fit": school_fit,
                "mentor_fit": mentor_fit,
                "role_fit": role_fit,
                "evidence_fit": evidence_fit,
                "confidentiality_fit": confidentiality_fit,
                "total_score": total,
                "recommendation": "",
                "caution": privacy_safe_text(caution, company_name, confidentiality),
                "reasons": display_reasons,
                "risk_tags": risk_tags,
            }
        )
    ranked.sort(key=lambda item: item["total_score"], reverse=True)
    generated_recommendations = generate_candidate_recommendations(
        current,
        profile,
        grounding,
        evidence_items,
        diagnosis,
        ranked,
    )
    if is_enabled():
        missing_titles = [
            item["title"]
            for item in ranked
            if not (
                generated_recommendations.get(item["title"])
                or generated_recommendations.get(item.get("raw_title") or "")
            )
        ]
        if missing_titles:
            raise RuntimeError("模型未返回完整的候选题推荐理由。")
    for index, item in enumerate(ranked):
        fallback_recommendation = candidate_recommendation_copy(
            item.get("raw_title") or item["title"],
            current,
            grounding,
            is_top=index == 0,
        )
        item["recommendation"] = privacy_safe_text(
            generated_recommendations.get(item["title"])
            or generated_recommendations.get(item.get("raw_title") or "")
            or ("" if is_enabled() else fallback_recommendation),
            company_name,
            confidentiality,
        )
    return replace_title_candidates(workspace_id, ranked, selected_title_id=None)


def _ensure_external_grounding(workspace_id: str) -> None:
    current = current_field_map(workspace_id)
    has_mentor_grounding = any(
        [
            str(current.get("mentor_research_fields") or "").strip(),
            str(current.get("mentor_expertise") or "").strip(),
        ]
    )
    has_company_grounding = any(
        [
            str(current.get("company_business") or "").strip(),
            str(current.get("company_keywords") or "").strip(),
        ]
    )
    should_enrich = False
    if str(current.get("mentor_name") or "").strip() and not has_mentor_grounding:
        should_enrich = True
    if str(current.get("company_name") or "").strip() and not has_company_grounding:
        should_enrich = True
    if not should_enrich:
        return
    try:
        from .enrichment_service import enrich_public_sources

        enrich_public_sources(workspace_id)
    except Exception:
        return


def _generate_candidates(
    current: dict[str, Any],
    profile: dict[str, Any],
    grounding: dict[str, Any],
    evidence_items: list[dict[str, Any]],
    diagnosis: dict[str, Any],
) -> list[dict[str, str]]:
    subject = _subject_name(current)
    context_penalty, _, _ = _context_sufficiency(current, evidence_items)
    heuristic_titles = _generic_titles(subject) if context_penalty > 0 else _heuristic_titles(current, grounding)
    heuristic_candidates = [{"title": title, "angle": "启发式兜底题目"} for title in heuristic_titles]
    model_candidates = generate_candidate_drafts(current, profile, grounding, evidence_items, diagnosis)
    combined = model_candidates if is_enabled() else model_candidates + heuristic_candidates
    if is_enabled() and not model_candidates:
        raise RuntimeError("模型未返回候选题，请先补全联网依据或资料后重试。")
    if not combined:
        combined = [{"title": fallback_title(subject, profile), "angle": "兜底题目"}]
    supported_titles = _filter_titles_by_scene_support([item["title"] for item in combined], current, grounding)
    allowed_titles = set(filter_title_candidates(supported_titles, profile))
    deduped: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in combined:
        title = str(item.get("title") or "").strip().replace("《", "").replace("》", "")
        if not title or title in seen or title not in allowed_titles:
            continue
        deduped.append({"title": title, "angle": str(item.get("angle") or "").strip()})
        seen.add(title)
    if is_enabled() and not deduped:
        raise RuntimeError("模型生成的候选题未通过学校规则校验，请调整资料后重试。")
    if not deduped:
        deduped = [{"title": fallback_title(subject, profile), "angle": "兜底题目"}]
    return deduped[:5]


def _heuristic_titles(current: dict[str, Any], grounding: dict[str, Any]) -> list[str]:
    subject = _subject_name(current)
    base_text = " ".join(
        str(current.get(key, ""))
        for key in ["research_direction", "work_scope", "pain_point", "research_goal", "role_title"]
    )
    base_text = " ".join(
        [
            base_text,
            str(grounding.get("company_business") or ""),
            " ".join(str(item) for item in grounding.get("company_keywords") or []),
        ]
    ).lower()
    topics = [label for label, keywords in TOPIC_PATTERNS if any(keyword in base_text for keyword in keywords)]
    titles = _preferred_titles_from_strategy(subject, base_text)
    if not topics and not titles:
        return _generic_titles(subject)
    suffixes = ["机制优化研究", "路径研究", "体系构建研究", "机制研究", "优化研究"]
    for topic in topics[:2]:
        for suffix in suffixes:
            phrase = topic.replace("体系", "")
            title = f"{subject}{phrase}{suffix}"
            title = re.sub(r"机制机制研究$", "机制研究", title)
            titles.append(title)
    if grounding.get("company_keywords"):
        keyword = str((grounding.get("company_keywords") or [""])[0]).strip()
        if keyword:
            titles.append(f"{subject}{keyword}场景优化研究")
    titles.append(f"{subject}管理问题诊断与优化研究")
    return titles


def _generic_titles(subject: str) -> list[str]:
    return [
        f"{subject}管理机制优化研究",
        f"{subject}组织协同优化研究",
        f"{subject}管理问题诊断与优化研究",
    ]


def _subject_name(current: dict[str, Any]) -> str:
    company_name = str(current.get("company_name") or "").strip()
    confidentiality = str(current.get("confidentiality_notes") or "")
    if company_name:
        return anonymized_subject_name(company_name, confidentiality)
    return "研究对象"


def _mentor_fit_scores(
    current: dict[str, Any],
    evidence_items: list[dict[str, Any]],
    titles: list[str],
    grounding: dict[str, Any],
) -> dict[str, tuple[float, list[str]]]:
    intake = []
    for evidence in evidence_items:
        excerpt = evidence.get("content", {}).get("text") or evidence.get("summary", "")
        intake.append(
            {
                "path": evidence.get("source_uri") or evidence["id"],
                "excerpt": excerpt,
                "urls": [evidence["source_uri"]] if evidence.get("source_uri", "").startswith("http") else [],
            }
        )
    project = {
        "mentor": current.get("mentor_name", ""),
        "research_direction": current.get("research_direction", ""),
        "mentor_keywords": " ".join(
            str(current.get(key, ""))
            for key in ["research_direction", "work_scope", "pain_point"]
        ).strip()
        + " "
        + " ".join(str(item) for item in grounding.get("mentor_research_fields") or [])
        + " "
        + " ".join(str(item) for item in grounding.get("mentor_expertise") or []),
        "web_sources": [item["source_uri"] for item in evidence_items if item.get("source_uri", "").startswith("http")][:6],
        "candidate_titles": titles,
    }
    try:
        fit = build_mentor_fit(project, intake)
    except Exception:
        fit = {"scores": []}
    mapping = {}
    for item in fit.get("scores", []):
        mapping[item["title"]] = (float(item["score"]), item.get("reasons", []) or [f"导师方向风险：{item.get('risk', '中')}"])
    return mapping


def _school_fit(title: str, profile: dict[str, Any]) -> tuple[float, list[str]]:
    score = 70.0
    reasons = []
    max_length = profile["title_style_rules"]["max_length"]
    if len(title) <= max_length:
        score += 12
        reasons.append(f"题目长度符合武汉大学指南“{max_length} 字以内”的要求。")
    else:
        score -= 12
        reasons.append("题目偏长，违反武汉大学对题目简洁聚焦的要求。")
    if any(title.endswith(suffix) for suffix in profile["title_style_rules"]["preferred_suffixes"]):
        score += 10
        reasons.append("题目表述接近武汉大学经管类专业硕士常用口径。")
    if any(pattern in title for pattern in profile["title_style_rules"].get("forbidden_patterns", [])):
        score -= 20
        reasons.append("题目触发了武汉大学指南不建议采用的写法。")
    return max(0.0, min(score, 100.0)), reasons


def _role_fit(title: str, current: dict[str, Any], grounding: dict[str, Any]) -> tuple[float, list[str]]:
    base = 58.0
    reasons = []
    text = " ".join(
        str(current.get(key, ""))
        for key in ["role_title", "work_scope", "research_direction", "pain_point", "research_goal"]
    ) + " " + " ".join(str(item) for item in grounding.get("company_keywords") or []) + " " + str(grounding.get("company_business") or "")
    hits = 0
    for keyword in ["AI", "智能体", "产品", "交付", "协同", "知识", "数据", "价值", "治理"]:
        if keyword in text and keyword in title:
            hits += 1
    if hits:
        base += min(30, hits * 6)
        reasons.append("题目与岗位和痛点关键词有直接重合。")
    else:
        reasons.append("题目与当前岗位场景的显性重合度一般。")
    if current.get("company_name"):
        base += 6
        reasons.append("研究对象口径已锚定到单位。")
    if any(str(current.get(key) or "").strip() for key in ["work_scope", "pain_point", "research_goal"]):
        base += 4
        reasons.append("已结合负责内容或真实问题补足研究场景。")
    elif grounding.get("role_focus"):
        base += 2
        reasons.append("已结合职位信息做初步场景收敛。")
    if grounding.get("company_business"):
        base += 4
        reasons.append("已结合单位主营业务收紧题目边界。")
    return max(0.0, min(base, 100.0)), reasons


def _evidence_fit(
    evidence_items: list[dict[str, Any]],
    profile: dict[str, Any],
    grounding: dict[str, Any],
) -> tuple[float, list[str]]:
    verified = [item for item in evidence_items if item["grade"] in {"A", "B"}]
    builtin_guide_loaded = has_builtin_guide(profile)
    internal_materials = [
        item
        for item in evidence_items
        if item["metadata"].get("category") == "internal_material"
    ]
    citations = [item for item in evidence_items if item["evidence_type"] == "citation" and item["status"] == "verified"]
    score = min(
        100.0,
        52.0
        + len(verified) * 5
        + (8 if builtin_guide_loaded else 0)
        + len(internal_materials) * 6
        + len(citations) * 2
        + (4 if grounding.get("mentor_research_fields") else 0)
        + (4 if grounding.get("company_business") else 0)
        + min(8, len(grounding.get("supporting_snippets") or []) * 2),
    )
    reasons = [
        f"当前 A/B 级证据 {len(verified)} 条。",
        "学校写作规则已作为系统内建规则加载。" if builtin_guide_loaded else "当前未加载学校写作规则。",
    ]
    if internal_materials:
        reasons.append(f"当前内部材料 {len(internal_materials)} 份，题目更容易贴住真实场景。")
    else:
        reasons.append("当前内部材料偏少，题目更依赖用户填写的工作场景。")
    if citations:
        reasons.append(f"当前已核验文献 {len(citations)} 条，可为后续综述提供支撑。")
    if grounding.get("supporting_snippets"):
        reasons.append(f"当前已从资料与网页中命中 {len(grounding.get('supporting_snippets') or [])} 条关键证据片段。")
    return score, reasons


def _confidentiality_fit(title: str, current: dict[str, Any]) -> tuple[float, list[str]]:
    company_name = str(current.get("company_name") or "")
    confidentiality = str(current.get("confidentiality_notes") or "")
    score = 82.0
    reasons = []
    if any(keyword in confidentiality for keyword in ["匿名", "保密", "不便披露", "化名"]):
        reasons.append("当前项目存在保密要求。")
        if company_name and company_name in title:
            score -= 35
            reasons.append("题目直接暴露单位名称，保密风险高。")
        else:
            reasons.append("题目已采用化名或泛化表述。")
    else:
        reasons.append("当前未发现明显保密限制。")
    return max(0.0, min(score, 100.0)), reasons


def _audit_reasons(profile: dict[str, Any], grounding: dict[str, Any], diagnosis: dict[str, Any]) -> list[str]:
    guide = profile.get("guide") or {}
    reasons: list[str] = []
    selection_rules = guide.get("selection_requirements") or []
    if selection_rules:
        reasons.append("学校规则依据：" + "；".join(selection_rules[:2]) + "。")
    if diagnosis.get("selection_logic"):
        reasons.append("选题收敛判断：" + str(diagnosis.get("selection_logic")).strip("。") + "。")
    if diagnosis.get("avoid_directions"):
        reasons.append("避免方向：" + "；".join(str(item) for item in diagnosis.get("avoid_directions")[:2]) + "。")
    if diagnosis.get("missing_information"):
        reasons.append("仍需补充：" + "、".join(str(item) for item in diagnosis.get("missing_information")[:3]) + "。")
    usable_data_sources = grounding.get("usable_data_sources") or []
    if usable_data_sources:
        reasons.append("默认资料接口：" + _join_list(usable_data_sources) + "。")
    mentor_snippets = [item for item in grounding.get("supporting_snippets") or [] if item.get("kind") == "mentor"]
    if mentor_snippets:
        evidence = mentor_snippets[0]
        reasons.append(f"导师证据依据：{evidence['title']} 提到“{evidence['snippet']}”。")
    elif grounding.get("mentor_research_fields"):
        reasons.append(f"导师证据依据：归纳出研究方向 { _join_list(grounding.get('mentor_research_fields')) }。")
    if grounding.get("company_business"):
        reasons.append(f"单位证据依据：归纳出主营业务“{grounding['company_business']}”。")
    material_snippets = [
        item
        for item in grounding.get("supporting_snippets") or []
        if item.get("kind") in {"company", "local_file", "web_link"}
    ]
    if material_snippets:
        refs = "；".join(f"{item['title']}：{item['snippet']}" for item in material_snippets[:2])
        reasons.append(f"资料证据依据：{refs}。")
    return reasons


def _context_sufficiency(
    current: dict[str, Any],
    evidence_items: list[dict[str, Any]],
) -> tuple[float, list[str], str | None]:
    role_title = str(current.get("role_title") or "").strip()
    work_scope = str(current.get("work_scope") or "").strip()
    pain_point = str(current.get("pain_point") or "").strip()
    research_goal = str(current.get("research_goal") or "").strip()
    research_direction = str(current.get("research_direction") or "").strip()
    has_substantive_scene = any([work_scope, pain_point, research_goal])
    has_role_and_direction = bool(role_title and research_direction)
    has_user_material = any(
        item["evidence_type"] == "local_file" or item.get("metadata", {}).get("category") == "user_link"
        for item in evidence_items
    )
    if has_substantive_scene or has_role_and_direction or has_user_material:
        return 0.0, [], None
    return (
        8.0,
        ["当前只拿到导师/单位公开信息，或仅有职位名称，缺少职责、真实问题或资料，题目方向仅作初步收敛参考。"],
        "信息不足",
    )


def _distinct_school_reasons(reasons: list[str]) -> list[str]:
    distinct = []
    for reason in reasons:
        if any(keyword in reason for keyword in ["偏长", "触发", "违反"]):
            distinct.append(reason)
    return distinct


def _sanitize_reasons(reasons: list[str], company_name: str, confidentiality: str) -> list[str]:
    ordered: list[str] = []
    for reason in reasons:
        text = privacy_safe_text(str(reason or "").strip(), company_name, confidentiality)
        if text and text not in ordered:
            ordered.append(text)
    return ordered

def _join_list(values: Any) -> str:
    if isinstance(values, list):
        cleaned = [str(item).strip() for item in values if str(item).strip()]
        return "、".join(cleaned)
    return str(values or "")


def _preferred_titles_from_strategy(subject: str, base_text: str) -> list[str]:
    titles = []
    lowered_hints = [item.lower() for item in INDUSTRY_HINTS]
    lowered_collab = [item.lower() for item in COLLAB_HINTS]
    lowered_data = [item.lower() for item in DATA_HINTS]
    lowered_value = [item.lower() for item in VALUE_HINTS]
    if any(keyword in base_text for keyword in ["ai", "智能体", "大模型"]):
        titles.append(f"{subject}AI智能体项目落地机制优化研究")
    if any(keyword in base_text for keyword in lowered_hints):
        titles.append(f"{subject}工业软件AI产品化机制研究")
    if any(keyword in base_text for keyword in lowered_collab):
        titles.append(f"{subject}AI转型项目组织协同机制优化研究")
    if any(keyword in base_text for keyword in lowered_data):
        titles.append(f"{subject}知识库驱动的AI交付机制优化研究")
        titles.append(f"{subject}工业场景数据准备机制优化研究")
    if any(keyword in base_text for keyword in lowered_value):
        titles.append(f"{subject}AI应用价值评估体系构建研究")
    return titles


def _filter_titles_by_scene_support(
    titles: list[str],
    current: dict[str, Any],
    grounding: dict[str, Any],
) -> list[str]:
    scene_text = " ".join(
        [
            str(current.get("role_title") or ""),
            str(current.get("work_scope") or ""),
            str(current.get("pain_point") or ""),
            str(current.get("research_goal") or ""),
            str(current.get("research_direction") or ""),
            str(grounding.get("company_business") or ""),
            " ".join(str(item) for item in grounding.get("company_keywords") or []),
            " ".join(
                str(item.get("snippet") or "")
                for item in grounding.get("supporting_snippets") or []
                if item.get("kind") in {"company", "local_file", "web_link"}
            ),
        ]
    ).lower()
    supports_ai = any(keyword.lower() in scene_text for keyword in ["ai", "智能体", "大模型"])
    supports_data = any(keyword.lower() in scene_text for keyword in ["数据", "知识", "知识库", "治理", "交付"])
    supports_value = any(keyword.lower() in scene_text for keyword in ["价值", "评估", "roi", "效益"])
    filtered: list[str] = []
    for title in titles:
        if any(keyword in title for keyword in AI_TITLE_HINTS) and not supports_ai:
            continue
        if any(keyword in title for keyword in DATA_TITLE_HINTS) and not supports_data:
            continue
        if any(keyword in title for keyword in VALUE_TITLE_HINTS) and not supports_value:
            continue
        filtered.append(title)
    return filtered
