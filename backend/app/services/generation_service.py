from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..core.evidence_grounding import build_grounding_context
from ..core.llm import LLMError
from ..core.paper_reasoning import diagnose_selection, generate_report_section
from ..core.parsing import build_citation_reference, citation_completeness_score
from ..core.profile_rules import (
    anonymized_subject_name,
    privacy_safe_report_title,
    privacy_safe_text,
    validate_section_map,
    validate_title,
)
from .export_service import render_bundle
from .literature_service import ensure_remote_citations
from .workspace_service import (
    create_snapshot,
    current_field_map,
    get_latest_deliverable_bundle,
    get_workspace_bundle,
    get_workspace_row,
    list_evidence_items,
    list_title_candidates,
    load_profile,
    save_deliverable_bundle,
    set_selected_title,
)


def generate_report(workspace_id: str, title_id: str | None = None) -> dict[str, Any]:
    workspace = get_workspace_row(workspace_id)
    bundle = get_workspace_bundle(workspace_id)
    current = bundle["current_fields"]
    profile = load_profile(workspace["school_profile"])
    titles = bundle["title_candidates"]
    if not titles:
        raise ValueError("No title candidates available")
    selected = _select_title(workspace_id, titles, title_id)
    report_title = privacy_safe_report_title(
        selected["title"],
        current.get("company_name", ""),
        current.get("confidentiality_notes", ""),
    )
    title_issues = validate_title(selected["title"], profile)
    if title_issues:
        raise ValueError("所选题目不符合学校规则：" + "；".join(title_issues))
    evidence_items = list_evidence_items(workspace_id)
    grounding = build_grounding_context(current, evidence_items)
    diagnosis = diagnose_selection(current, profile, grounding, evidence_items)
    verified_citations = ensure_remote_citations(
        workspace_id=workspace_id,
        title=selected["title"],
        current=current,
        profile=profile,
        grounding=grounding,
        evidence_items=evidence_items,
        diagnosis=diagnosis,
    )
    evidence_items = list_evidence_items(workspace_id)
    grounding = build_grounding_context(current, evidence_items)
    diagnosis = diagnose_selection(current, profile, grounding, evidence_items)
    _ensure_formal_report_readiness(
        current=current,
        profile=profile,
        grounding=grounding,
        diagnosis=diagnosis,
        citations=verified_citations,
    )
    section_map = _build_section_map(
        current,
        report_title,
        profile,
        verified_citations,
        grounding,
        evidence_items,
        diagnosis,
    )
    section_issues = validate_section_map(section_map, profile)
    if section_issues:
        raise ValueError("开题报告结构校验失败：" + "；".join(section_issues))
    markdown = _compose_markdown(report_title, section_map, verified_citations)
    markdown = privacy_safe_text(
        markdown,
        current.get("company_name", ""),
        current.get("confidentiality_notes", ""),
    )
    output_dir = Path(workspace["workspace_dir"]) / "generated"
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / f"{_safe_title(report_title)}-report.md"
    report_path.write_text(markdown, encoding="utf-8")
    snapshot_path = create_snapshot(
        workspace_id,
        f"{report_title}-report-snapshot",
        {
            "selected_title": {**selected, "title": report_title},
            "current_fields": _privacy_safe_current_fields(current),
            "sections": _privacy_safe_sections(section_map, current),
            "citations": [item["metadata"] for item in verified_citations],
            "grounding": _privacy_safe_grounding(grounding, current),
            "selection_diagnosis": _privacy_safe_mapping(diagnosis, current),
            "profile_guide": profile.get("guide", {}),
        },
    )
    return {
        "title_candidate": selected,
        "report_title": report_title,
        "report_markdown": markdown,
        "report_markdown_path": str(report_path),
        "snapshot_path": snapshot_path,
    }


def freeze_deliverables(workspace_id: str, title_id: str | None = None) -> dict[str, Any]:
    report = generate_report(workspace_id, title_id=title_id)
    workspace = get_workspace_row(workspace_id)
    bundle = get_workspace_bundle(workspace_id)
    profile = load_profile(workspace["school_profile"])
    output_dir = Path(workspace["workspace_dir"]) / "generated"
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts = render_bundle(
        markdown=report["report_markdown"],
        title=report["report_title"],
        deck_outline=profile["deck_outline"],
        output_dir=output_dir,
        basic_info=bundle["current_fields"],
        footer_label=profile["name"],
    )
    saved = save_deliverable_bundle(
        workspace_id=workspace_id,
        snapshot_path=report["snapshot_path"],
        **artifacts,
    )
    return {
        "bundle": saved,
        "report": report,
    }


def _select_title(workspace_id: str, titles: list[dict[str, Any]], title_id: str | None) -> dict[str, Any]:
    if title_id:
        set_selected_title(workspace_id, title_id)
        for item in titles:
            if item["id"] == title_id:
                return item
    for item in titles:
        if item["selected"]:
            return item
    set_selected_title(workspace_id, titles[0]["id"])
    return titles[0]


def _verified_citations(evidence_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    citations = []
    for item in evidence_items:
        if item["evidence_type"] != "citation":
            continue
        is_complete, _ = citation_completeness_score(item["metadata"])
        if item["status"] == "verified" and is_complete:
            citations.append(item)
    return citations


def _ensure_formal_report_readiness(
    *,
    current: dict[str, Any],
    profile: dict[str, Any],
    grounding: dict[str, Any],
    diagnosis: dict[str, Any],
    citations: list[dict[str, Any]],
) -> None:
    issues: list[str] = []
    required_fields = [
        ("school_name", "学校名称"),
        ("mentor_name", "导师姓名"),
        ("student_name", "学生姓名"),
        ("student_id", "学号"),
        ("company_name", "工作单位"),
        ("role_title", "工作职位"),
        ("work_scope", "负责内容描述"),
    ]
    missing_fields = [label for key, label in required_fields if not str(current.get(key) or "").strip()]
    if missing_fields:
        issues.append("基础信息未补齐：" + "、".join(missing_fields))
    if not str(grounding.get("company_business") or "").strip():
        issues.append("单位主营业务尚未锁定，不能支撑正式开题报告")
    if len(grounding.get("problem_statements") or []) < 1 and not str(current.get("pain_point") or "").strip():
        issues.append("真实管理问题尚未锁定，不能进入正式写作")
    if len(grounding.get("usable_data_sources") or []) < 2:
        issues.append("可核验的一手资料接口不足，未达到专题研究写作要求")
    if not (grounding.get("mentor_research_fields") or grounding.get("mentor_expertise")):
        issues.append("导师研究方向与学术擅长尚未形成有效依据")

    critical_missing = _critical_missing_information(diagnosis)
    if critical_missing:
        issues.append("选题基础仍未锁死：" + "；".join(critical_missing))

    guide = profile.get("guide") or {}
    reference_requirements = guide.get("reference_requirements") or {}
    min_refs = int(reference_requirements.get("opening_report_min_items", 30))
    foreign_ratio_min = float(reference_requirements.get("opening_report_foreign_ratio_min", 0.3333))
    if len(citations) < min_refs:
        issues.append(f"真实核验文献仅 {len(citations)} 篇，未达到武汉大学开题要求的至少 {min_refs} 篇")
    required_foreign = max(1, round(min_refs * foreign_ratio_min))
    foreign_count = sum(1 for item in citations if _is_foreign_citation(item.get("metadata") or {}))
    if foreign_count < required_foreign:
        issues.append(f"外文文献仅 {foreign_count} 篇，未达到至少 {required_foreign} 篇的要求")

    if issues:
        numbered = "\n".join(f"{index}. {issue}" for index, issue in enumerate(issues, start=1))
        raise ValueError("当前不满足武汉大学正式开题报告生成条件：\n" + numbered)


def _critical_missing_information(diagnosis: dict[str, Any]) -> list[str]:
    critical_keywords = (
        "主营业务",
        "组织类型",
        "具体项目",
        "主问题",
        "样本",
        "量化",
        "项目类型",
    )
    missing = []
    for item in diagnosis.get("missing_information") or []:
        text = str(item or "").strip()
        if text and any(keyword in text for keyword in critical_keywords):
            missing.append(text)
    return missing[:4]


def _is_foreign_citation(metadata: dict[str, Any]) -> bool:
    language = str(metadata.get("language") or "").lower().strip()
    if language:
        if language.startswith("zh"):
            return False
        if language.startswith("en"):
            return True
    sample = " ".join(
        str(metadata.get(key) or "")
        for key in ["author", "title", "source", "abstract"]
    ).strip()
    if not sample:
        return False
    has_latin = bool(re.search(r"[A-Za-z]", sample))
    has_cjk = bool(re.search(r"[\u4e00-\u9fff]", sample))
    return has_latin and not has_cjk


def _build_section_map(
    current: dict[str, Any],
    title: str,
    profile: dict[str, Any],
    citations: list[dict[str, Any]],
    grounding: dict[str, Any],
    evidence_items: list[dict[str, Any]],
    diagnosis: dict[str, Any],
) -> dict[str, str]:
    section_map: dict[str, str] = {
        "基本信息": _basic_info_section(current, profile, grounding, diagnosis),
    }
    for section_name in profile.get("section_order") or profile.get("required_sections") or []:
        if section_name in {"基本信息", "主要参考文献目录"}:
            continue
        try:
            content = generate_report_section(
                section_name=section_name,
                current=current,
                profile=profile,
                grounding=grounding,
                evidence_items=evidence_items,
                diagnosis=diagnosis,
                title=title,
                citations=citations,
            )
        except LLMError as exc:
            raise ValueError(f"模型未能稳定生成“{section_name}”，请补强资料后重试") from exc
        cleaned = _clean_section_text(content)
        if len(cleaned) < 120:
            raise ValueError(f"“{section_name}”内容不足，当前证据还不能支撑正式开题报告")
        section_map[section_name] = cleaned
    section_map["主要参考文献目录"] = _reference_section(citations)
    return section_map


def _basic_info_section(
    current: dict[str, Any],
    profile: dict[str, Any],
    grounding: dict[str, Any],
    diagnosis: dict[str, Any],
) -> str:
    company_name = str(current.get("company_name") or "")
    confidentiality = str(current.get("confidentiality_notes") or "")
    guide_title = (profile.get("guide") or {}).get("title") or profile.get("name") or "待确认"
    mentor_fields = _grounding_list_text(
        grounding.get("mentor_research_fields"),
        company_name,
        confidentiality,
        fallback=str(current.get("research_direction") or "待确认"),
    )
    mentor_expertise = _grounding_list_text(
        grounding.get("mentor_expertise"),
        company_name,
        confidentiality,
        fallback="待确认",
    )
    research_direction = privacy_safe_text(
        str(current.get("research_direction") or diagnosis.get("recommended_track") or "待确认"),
        company_name,
        confidentiality,
    )
    company_business = privacy_safe_text(
        str(grounding.get("company_business") or "待确认"),
        company_name,
        confidentiality,
    )
    lines = [
        f"- 学校：{current.get('school_name') or '待确认'}",
        f"- 项目：{current.get('program_name') or '待确认'}",
        f"- 学生：{current.get('student_name') or '待确认'}",
        f"- 学号：{current.get('student_id') or '待确认'}",
        f"- 导师：{current.get('mentor_name') or '待确认'} {current.get('mentor_title') or ''}".strip(),
        f"- 单位：{anonymized_subject_name(company_name, confidentiality) if company_name else '待确认'}",
        f"- 单位主营业务：{company_business}",
        f"- 岗位：{current.get('role_title') or '待确认'}",
        f"- 论文类型：{current.get('thesis_type') or '专题研究类'}",
        f"- 拟研究方向：{research_direction}",
        f"- 导师研究方向：{mentor_fields}",
        f"- 导师学术擅长：{mentor_expertise}",
        f"- 写作指南：{guide_title}",
    ]
    return "\n".join(lines)


def _reference_section(citations: list[dict[str, Any]]) -> str:
    chinese = [item for item in citations if not _is_foreign_citation(item.get("metadata") or {})]
    foreign = [item for item in citations if _is_foreign_citation(item.get("metadata") or {})]
    blocks: list[str] = []
    if chinese:
        blocks.append("### 中文文献")
        blocks.append("")
        for index, item in enumerate(chinese, start=1):
            blocks.append(build_citation_reference(item["metadata"], index))
        blocks.append("")
    if foreign:
        blocks.append("### 外文文献")
        blocks.append("")
        start = len(chinese) + 1
        for offset, item in enumerate(foreign, start=start):
            blocks.append(build_citation_reference(item["metadata"], offset))
        blocks.append("")
    return "\n".join(blocks).strip()


def _compose_markdown(title: str, sections: dict[str, str], citations: list[dict[str, Any]]) -> str:
    lines = [f"# 《{title}》开题报告", ""]
    for section_name, content in sections.items():
        lines.extend([f"## {section_name}", "", content, ""])
    return "\n".join(lines).strip() + "\n"


def _safe_title(title: str) -> str:
    return re.sub(r"[/:]", "-", title).strip()


def _privacy_safe_current_fields(current: dict[str, Any]) -> dict[str, Any]:
    company_name = str(current.get("company_name") or "")
    confidentiality = str(current.get("confidentiality_notes") or "")
    safe_fields: dict[str, Any] = {}
    for key, value in current.items():
        if isinstance(value, str):
            if key == "company_name":
                safe_fields[key] = anonymized_subject_name(company_name, confidentiality) if company_name else value
            else:
                safe_fields[key] = privacy_safe_text(value, company_name, confidentiality)
        else:
            safe_fields[key] = value
    return safe_fields


def _privacy_safe_grounding(grounding: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    company_name = str(current.get("company_name") or "")
    confidentiality = str(current.get("confidentiality_notes") or "")
    return _privacy_safe_mapping(grounding, current, company_name=company_name, confidentiality=confidentiality)


def _privacy_safe_mapping(
    payload: dict[str, Any],
    current: dict[str, Any],
    *,
    company_name: str | None = None,
    confidentiality: str | None = None,
) -> dict[str, Any]:
    company_name = str(company_name if company_name is not None else current.get("company_name") or "")
    confidentiality = str(confidentiality if confidentiality is not None else current.get("confidentiality_notes") or "")
    safe_payload: dict[str, Any] = {}
    for key, value in payload.items():
        if isinstance(value, str):
            safe_payload[key] = privacy_safe_text(value, company_name, confidentiality)
        elif isinstance(value, list):
            safe_payload[key] = [
                {
                    sub_key: privacy_safe_text(str(sub_value), company_name, confidentiality)
                    for sub_key, sub_value in item.items()
                }
                if isinstance(item, dict)
                else privacy_safe_text(str(item), company_name, confidentiality)
                for item in value
            ]
        else:
            safe_payload[key] = value
    return safe_payload


def _privacy_safe_sections(sections: dict[str, str], current: dict[str, Any]) -> dict[str, str]:
    company_name = str(current.get("company_name") or "")
    confidentiality = str(current.get("confidentiality_notes") or "")
    return {
        section_name: privacy_safe_text(content, company_name, confidentiality)
        for section_name, content in sections.items()
    }


def _grounding_list_text(
    values: Any,
    company_name: str,
    confidentiality: str,
    fallback: str = "待补充",
) -> str:
    if isinstance(values, list):
        cleaned = [privacy_safe_text(str(item), company_name, confidentiality) for item in values if str(item).strip()]
        return "、".join(cleaned) if cleaned else fallback
    if str(values or "").strip():
        return privacy_safe_text(str(values), company_name, confidentiality)
    return fallback


def _supporting_snippets_text(grounding: dict[str, Any], company_name: str, confidentiality: str) -> str:
    snippets = grounding.get("supporting_snippets") or []
    if not snippets:
        return "当前尚未形成可直接引用的资料片段，后续需继续补充。"
    parts = []
    for item in snippets[:3]:
        parts.append(
            privacy_safe_text(
                f"{item.get('title', '资料')}中提到“{item.get('snippet', '')}”",
                company_name,
                confidentiality,
            )
        )
    return "；".join(parts)


def _selection_basis_text(
    current: dict[str, Any],
    grounding: dict[str, Any],
    company_name: str,
    confidentiality: str,
    fallback_direction: str,
    fallback_problem: str,
) -> str:
    mentor_anchor = _grounding_list_text(
        grounding.get("mentor_research_fields"),
        company_name,
        confidentiality,
        fallback=fallback_direction,
    )
    mentor_expertise = _grounding_list_text(
        grounding.get("mentor_expertise"),
        company_name,
        confidentiality,
        fallback="待进一步补充",
    )
    company_anchor = privacy_safe_text(
        str(grounding.get("company_business") or "研究对象业务边界待补充"),
        company_name,
        confidentiality,
    )
    role_anchor = privacy_safe_text(
        str(grounding.get("role_focus") or current.get("work_scope") or current.get("role_title") or "岗位职责待补充"),
        company_name,
        confidentiality,
    )
    problem_anchor = _grounding_list_text(
        grounding.get("problem_statements"),
        company_name,
        confidentiality,
        fallback=fallback_problem,
    )
    evidence_anchor = _grounding_list_text(
        grounding.get("usable_data_sources"),
        company_name,
        confidentiality,
        fallback="访谈、内部资料、公开网页资料",
    )
    return (
        f"导师研究方向与学术擅长集中在 {mentor_anchor} / {mentor_expertise}；"
        f"学生所在单位的真实业务场景为 {company_anchor}；"
        f"学生当前岗位与职责聚焦 {role_anchor}；"
        f"当前可验证的问题线索主要包括 {problem_anchor}；"
        f"后续论证将主要使用 {evidence_anchor} 作为资料接口"
    )


def _clean_section_text(content: str) -> str:
    normalized = str(content or "").strip()
    if normalized.startswith("```"):
        normalized = normalized.strip("`").strip()
        if normalized.startswith("markdown"):
            normalized = normalized[8:].strip()
    return normalized.strip()
