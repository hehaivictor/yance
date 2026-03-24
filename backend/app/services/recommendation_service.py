from __future__ import annotations

import re
import uuid
from typing import Any

from ..core.legacy_bridge import build_mentor_fit
from ..core.llm import LLMError, complete_json, is_enabled
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


def recommend_titles(workspace_id: str) -> list[dict[str, Any]]:
    current = current_field_map(workspace_id)
    evidence_items = list_evidence_items(workspace_id)
    workspace = get_workspace_row(workspace_id)
    profile = load_profile(workspace["school_profile"])
    titles = _generate_candidates(current, profile)
    mentor_scores = _mentor_fit_scores(current, evidence_items, titles)
    ranked = []
    for title in titles:
        school_fit, school_reasons = _school_fit(title, profile)
        mentor_fit, mentor_reasons = mentor_scores.get(title, (58.0, ["缺少明确导师方向证据，按中性值处理。"]))
        role_fit, role_reasons = _role_fit(title, current)
        evidence_fit, evidence_reasons = _evidence_fit(evidence_items)
        confidentiality_fit, confidentiality_reasons = _confidentiality_fit(title, current)
        total = round(
            school_fit * 0.22
            + mentor_fit * 0.22
            + role_fit * 0.24
            + evidence_fit * 0.2
            + confidentiality_fit * 0.12,
            1,
        )
        recommendation = "资料和题目口径相对稳，适合优先进入正文。"
        caution = "需要补强资料和冲突字段后再正式写作。"
        risk_tags = []
        if total >= 82:
            recommendation = "推荐优先采用，学校口径、导师方向和资料可得性较平衡。"
        elif total >= 70:
            recommendation = "可作为备选，需要在方法或资料边界上再收紧。"
            risk_tags.append("需收敛")
        else:
            caution = "当前更像概念题而不是可落地开题题，暂不建议直接进入正文。"
            risk_tags.append("不建议直接采用")
        if confidentiality_fit < 65:
            risk_tags.append("保密风险")
        if evidence_fit < 65:
            risk_tags.append("资料不足")
        ranked.append(
            {
                "id": str(uuid.uuid4()),
                "title": title,
                "school_fit": school_fit,
                "mentor_fit": mentor_fit,
                "role_fit": role_fit,
                "evidence_fit": evidence_fit,
                "confidentiality_fit": confidentiality_fit,
                "total_score": total,
                "recommendation": recommendation,
                "caution": caution,
                "reasons": school_reasons + mentor_reasons + role_reasons + evidence_reasons + confidentiality_reasons,
                "risk_tags": risk_tags,
            }
        )
    ranked.sort(key=lambda item: item["total_score"], reverse=True)
    selected_title_id = ranked[0]["id"] if ranked else None
    return replace_title_candidates(workspace_id, ranked, selected_title_id=selected_title_id)


def _generate_candidates(current: dict[str, Any], profile: dict[str, Any]) -> list[str]:
    subject = _subject_name(current)
    heuristics = _heuristic_titles(current)
    if is_enabled():
        try:
            ai_titles = _ai_titles(current, profile)
            heuristics = ai_titles + heuristics
        except LLMError:
            pass
    deduped: list[str] = []
    for title in heuristics:
        title = title.strip().replace("《", "").replace("》", "")
        if title and title not in deduped:
            deduped.append(title)
    if not deduped:
        deduped = [f"{subject}AI智能体落地机制优化研究"]
    return deduped[:5]


def _ai_titles(current: dict[str, Any], profile: dict[str, Any]) -> list[str]:
    subject = _subject_name(current)
    prompt = f"""
你要为 EMBA 开题生成 5 个题目，要求：
1. 研究对象默认写成“{subject}”
2. 题目控制在 {profile['title_style_rules']['max_length']} 字以内
3. 只允许使用“优化研究 / 机制研究 / 路径研究 / 体系构建研究”这一类结尾
4. 必须贴合岗位与痛点，不能写成宏大行业报告
5. 返回 JSON：{{"titles":["..."]}}

岗位职责：{current.get('role_title', '')}
工作范围：{current.get('work_scope', '')}
真实痛点：{current.get('pain_point', '')}
研究目标：{current.get('research_goal', '')}
导师偏好：{current.get('mentor_preference_notes', '')}
"""
    payload = complete_json(
        "你是经管类开题选题专家，只输出 JSON，不要解释。",
        prompt,
        temperature=0.3,
    )
    return [item for item in payload.get("titles", []) if isinstance(item, str)]


def _heuristic_titles(current: dict[str, Any]) -> list[str]:
    subject = _subject_name(current)
    base_text = " ".join(
        str(current.get(key, ""))
        for key in ["pain_point", "work_scope", "research_goal", "mentor_preference_notes"]
    ).lower()
    topics = [label for label, keywords in TOPIC_PATTERNS if any(keyword in base_text for keyword in keywords)]
    if not topics:
        topics = ["AI智能体落地", "组织协同机制", "价值评估体系"]
    titles = []
    suffixes = ["机制优化研究", "路径研究", "体系构建研究", "机制研究", "优化研究"]
    for topic in topics[:2]:
        for suffix in suffixes:
            phrase = topic.replace("体系", "")
            title = f"{subject}{phrase}{suffix}"
            title = re.sub(r"机制机制研究$", "机制研究", title)
            titles.append(title)
    titles.append(f"{subject}管理问题诊断与优化研究")
    return titles


def _subject_name(current: dict[str, Any]) -> str:
    company_name = str(current.get("company_name") or "").strip()
    confidentiality = str(current.get("confidentiality_notes") or "")
    if any(keyword in confidentiality for keyword in ["匿名", "保密", "不便披露", "化名"]):
        return "K公司"
    return company_name or "研究对象"


def _mentor_fit_scores(current: dict[str, Any], evidence_items: list[dict[str, Any]], titles: list[str]) -> dict[str, tuple[float, list[str]]]:
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
        "mentor_keywords": current.get("mentor_preference_notes", ""),
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
        reasons.append("题目长度符合学校偏好。")
    else:
        score -= 12
        reasons.append("题目偏长，容易写大写空。")
    if any(title.endswith(suffix) for suffix in profile["title_style_rules"]["preferred_suffixes"]):
        score += 10
        reasons.append("题目后缀符合经管类开题常用口径。")
    if any(pattern in title for pattern in profile["title_style_rules"].get("forbidden_patterns", [])):
        score -= 20
        reasons.append("题目触发了学校不偏好的写法。")
    return max(0.0, min(score, 100.0)), reasons


def _role_fit(title: str, current: dict[str, Any]) -> tuple[float, list[str]]:
    base = 58.0
    reasons = []
    text = " ".join(str(current.get(key, "")) for key in ["work_scope", "pain_point", "research_goal"])
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
    return max(0.0, min(base, 100.0)), reasons


def _evidence_fit(evidence_items: list[dict[str, Any]]) -> tuple[float, list[str]]:
    verified = [item for item in evidence_items if item["grade"] in {"A", "B"}]
    citations = [item for item in evidence_items if item["evidence_type"] == "citation" and item["status"] == "verified"]
    score = min(100.0, 48.0 + len(verified) * 5 + len(citations) * 4)
    reasons = [
        f"当前 A/B 级证据 {len(verified)} 条。",
        f"当前已核验文献 {len(citations)} 条。",
    ]
    if len(citations) < 3:
        reasons.append("文献数量偏少，文献综述会偏薄。")
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
