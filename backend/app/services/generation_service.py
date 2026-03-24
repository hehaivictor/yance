from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..core.llm import LLMError, complete_text, is_enabled
from ..core.parsing import build_citation_reference, citation_completeness_score
from .export_service import render_bundle
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
    verified_citations = _verified_citations(list_evidence_items(workspace_id))
    section_map = _build_section_map(current, selected["title"], profile, verified_citations)
    markdown = _compose_markdown(selected["title"], section_map, verified_citations)
    if is_enabled():
        try:
            markdown = _polish_markdown(markdown, selected["title"])
        except LLMError:
            pass
    output_dir = Path(workspace["workspace_dir"]) / "generated"
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / f"{_safe_title(selected['title'])}-report.md"
    report_path.write_text(markdown, encoding="utf-8")
    snapshot_path = create_snapshot(
        workspace_id,
        f"{selected['title']}-report-snapshot",
        {
            "selected_title": selected,
            "current_fields": current,
            "sections": section_map,
            "citations": [item["metadata"] for item in verified_citations],
        },
    )
    return {
        "title_candidate": selected,
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
        title=report["title_candidate"]["title"],
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
    return citations[:12]


def _build_section_map(
    current: dict[str, Any],
    title: str,
    profile: dict[str, Any],
    citations: list[dict[str, Any]],
) -> dict[str, str]:
    research_goal = current.get("research_goal") or "围绕真实管理问题完成诊断、解释与方案设计。"
    pain_point = current.get("pain_point") or "当前研究对象在关键流程、组织协同或数据治理上存在待优化问题。"
    work_scope = current.get("work_scope") or "当前工作场景与研究对象边界仍需进一步补充。"
    data_sources = current.get("data_sources") or profile["methodology_rules"]["required_data_statement"]
    confidentiality = current.get("confidentiality_notes") or "涉及内部资料时将按学校要求做匿名化处理。"
    methods = "、".join(profile["methodology_rules"]["preferred_methods"])
    literature = _literature_review(citations)
    references = "\n".join(
        build_citation_reference(item["metadata"], index)
        for index, item in enumerate(citations, start=1)
    ) or "- 当前没有通过核验的文献，请先导入真实文献后再完善本节。"
    return {
        "基本信息": "\n".join(
            [
                f"- 学校：{current.get('school_name') or '待确认'}",
                f"- 项目：{current.get('program_name') or '待确认'}",
                f"- 学生：{current.get('student_name') or '待确认'}",
                f"- 导师：{current.get('mentor_name') or '待确认'} {current.get('mentor_title') or ''}".strip(),
                f"- 论文类型：{current.get('thesis_type') or '专题研究类'}",
                f"- 研究方向：{current.get('research_direction') or '待确认'}",
            ]
        ),
        "开题报告内容摘要": (
            f"本文拟围绕《{title}》展开研究，聚焦{pain_point}。"
            f"研究将以{work_scope}为现实场景，以{research_goal}为主线，"
            "在学校开题规范约束下形成问题诊断、成因分析和优化方案。"
        ),
        "选题背景与问题提出": (
            f"当前研究对象的核心背景可概括为：{work_scope}。"
            f"在这一背景下，最突出的问题并非概念层面的技术讨论，而是{pain_point}。"
            "因此，本研究不追求泛行业判断，而聚焦单一对象、单一问题和单一改进路径。"
        ),
        "研究目的": (
            f"本研究的直接目标是：{research_goal}。"
            "具体而言，将识别关键问题的外在表现、梳理深层成因，并提出具备组织可执行性和资料可验证性的改进方案。"
        ),
        "国内外研究现状及评述": literature,
        "研究内容、拟解决的关键问题及理论工具": (
            "研究内容将围绕现状诊断、关键问题识别、成因分析、方案设计和实施保障展开。"
            f"理论工具优先考虑：{methods}。"
            "重点不在于泛化描述，而在于把研究对象的管理问题拆解为可以被证据支持的分析单元。"
        ),
        "研究方法、资料来源与技术路线": (
            f"本研究拟采用{methods}。"
            f"资料来源包括：{data_sources}。"
            f"{confidentiality}"
            "技术路线遵循“问题识别 - 文献梳理 - 证据验证 - 方案设计 - 形成建议”的顺序推进。"
        ),
        "研究重点、难点、可能创新点与不足": (
            "研究重点在于界定问题边界并把改进方案落实到真实流程。"
            "研究难点主要来自内部资料获取、访谈对象可达性以及保密边界控制。"
            "可能的创新点在于将导师偏好、学校要求和企业真实场景三者放在同一套证据链中统一分析。"
        ),
        "研究计划与进度安排": (
            "近期先完成开题报告和题目冻结，随后完成访谈与资料补充，"
            "中期完成问题诊断和方案设计，后期形成论文正文和答辩材料。"
        ),
        "主要参考文献": references,
    }


def _literature_review(citations: list[dict[str, Any]]) -> str:
    if not citations:
        return "当前尚未形成经过核验的文献池，因此本节仅保留结构，不输出未经证据支持的文献综述。"
    topic_lines = []
    for index, citation in enumerate(citations[:4], start=1):
        title = citation["metadata"].get("title", "")
        source = citation["metadata"].get("source", "")
        year = citation["metadata"].get("year", "")
        topic_lines.append(f"{title}（{source}，{year}）[{index}]")
    return (
        "现有文献主要围绕以下几个方向展开："
        + "；".join(topic_lines)
        + "。在此基础上，本文将结合研究对象的具体管理问题，提炼可直接服务于开题设计的分析框架。"
    )


def _compose_markdown(title: str, sections: dict[str, str], citations: list[dict[str, Any]]) -> str:
    lines = [f"# 《{title}》开题报告", ""]
    for section_name, content in sections.items():
        lines.extend([f"## {section_name}", "", content, ""])
    return "\n".join(lines).strip() + "\n"


def _polish_markdown(markdown: str, title: str) -> str:
    prompt = f"""
请把下面这份开题报告改写成更自然、更像真实研究者写出来的中文学术表达。
要求：
1. 保留所有一级、二级标题
2. 保留所有已有的方括号引用编号，不得新增编号
3. 不得新增事实、文献、数据或导师偏好
4. 避免空话、套话、AI 腔
5. 输出仍然是 Markdown

题目：{title}

原文：
{markdown}
"""
    return complete_text("你是擅长经管类开题写作的学术编辑。", prompt, temperature=0.4)


def _safe_title(title: str) -> str:
    return re.sub(r"[/:]", "-", title).strip()
