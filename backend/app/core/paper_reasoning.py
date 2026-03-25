from __future__ import annotations

import re
from typing import Any

from .llm import LLMError, complete_json, complete_text, is_enabled
from .profile_rules import anonymized_subject_name


TITLE_REASON_STYLE_EXAMPLE = """
认可的高质量表达风格如下，请学习它的“判断方式”和“推荐语气”，不要机械复用原句：

1. K公司AI智能体项目落地机制优化研究
推荐理由：最推荐。围绕从立项、PoC、部署、推广到复盘的全过程，诊断卡点并提出机制优化方案；最符合经管类专题研究常用的“问题诊断-成因分析-方案设计”逻辑。

2. K公司工业软件AI产品化机制研究
推荐理由：聚焦能力如何从定制项目转成可复制产品或平台能力；既贴合工作内容，也能和导师“创新、高质量发展、数字经济”方向形成衔接。

3. K公司AI转型项目组织协同机制优化研究
推荐理由：聚焦研发、售前、交付、客户业务部门之间的协同断点、职责边界与流程衔接问题；现实价值强，访谈和内部资料更容易做深。

你要学习的是：
- 先判断研究对象、场景、问题、资料基础，再出题
- 题目是专题研究类，不是宏大行业报告
- 推荐理由要像导师/选题顾问给判断，直接说“为什么这个题值得做”
- 推荐理由优先说明对象边界、岗位贴合度、导师衔接和资料可做性
""".strip()


REPORT_STYLE_EXAMPLE = """
认可的开题报告写法要求如下：
- 不是空泛套话，也不是罗列模板条目
- 每一章都要先落到真实对象、真实场景、真实问题，再展开研究逻辑
- 文风应像经管类专业硕士开题，不写技术白皮书，不写行业宣传稿
- 可以明确说“当前资料显示”“现有证据表明”，但不能编造事实
- 章节之间要有承接：背景与问题提出 -> 研究动态评述 -> 研究设计 -> 方案与进度
""".strip()


SECTION_GUIDANCE = {
    "选题的背景与问题的提出": "先交代研究对象和场景，再收敛到一个具体管理问题，说明为什么值得研究；不要写成宏观行业综述。",
    "国内外关于该选题的动态": "围绕 2 到 4 个研究主题梳理国内外研究进展，并指出现有研究与本文场景之间的缺口；只能使用已给定的文献编号。",
    "研究设计": "写清研究问题、研究思路、理论工具或方法、资料来源和论文结构，体现专题研究类的“问题诊断-成因分析-方案设计”路径。",
    "研究方案及其进度安排": "写清资料获取安排、阶段任务、时间节奏和预期成果，突出可执行性与可落地性。",
}


def diagnose_selection(
    current: dict[str, Any],
    profile: dict[str, Any],
    grounding: dict[str, Any],
    evidence_items: list[dict[str, Any]],
) -> dict[str, Any]:
    fallback = _fallback_selection_diagnosis(current, grounding, evidence_items)
    if not is_enabled():
        return fallback
    try:
        payload = complete_json(
            "你是经管类专业硕士选题诊断顾问。先做选题收敛判断，再决定题目方向。只能基于给定材料判断，不得脑补。",
            f"""
请先做“选题收敛判断”，不要直接写开题报告。
你需要判断：研究对象、核心问题、最适合的专题研究口径、不能碰的方向、还缺哪些信息。

只返回 JSON：
{{
  "research_object": "...",
  "core_problem": "...",
  "recommended_track": "...",
  "candidate_axes": ["..."],
  "advisor_alignment": "...",
  "job_alignment": "...",
  "data_foundation": "...",
  "selection_logic": "...",
  "avoid_directions": ["..."],
  "missing_information": ["..."]
}}

{TITLE_REASON_STYLE_EXAMPLE}

学校规则：
- 学校：{current.get("school_name") or profile.get("name") or "待确认"}
- 指南摘要：{(profile.get("guide") or {}).get("summary") or "待补充"}
- 选题要求：{"；".join((profile.get("guide") or {}).get("selection_requirements") or [])}

证据包：
{build_evidence_pack(current, profile, grounding, evidence_items)}
""",
            temperature=0.2,
        )
    except LLMError:
        return fallback
    return _merge_selection_diagnosis(fallback, payload)


def generate_candidate_drafts(
    current: dict[str, Any],
    profile: dict[str, Any],
    grounding: dict[str, Any],
    evidence_items: list[dict[str, Any]],
    diagnosis: dict[str, Any],
) -> list[dict[str, str]]:
    if not is_enabled():
        return []
    subject = _subject_alias(current)
    try:
        payload = complete_json(
            "你是经管类专业硕士开题选题专家。只输出 JSON，不要解释。",
            f"""
请基于“选题收敛判断”生成 3 到 5 个候选题。

要求：
1. 研究对象默认写成“{subject}”
2. 题目必须符合学校指南，控制在 {int((profile.get('title_style_rules') or {}).get('max_length', 25))} 字以内
3. 必须是专题研究类口径，聚焦单一对象、单一问题、单一改进路径
4. 只有当“单位业务 + 岗位/职责 + 资料证据”至少两处明确支持时，才能在题目里出现 AI、智能体、数据治理等强概念
5. 不要生成宏大行业题、纯技术题、纯影响因素题
6. 题目之间要有明显区分，不能只是换词

只返回 JSON：
{{
  "candidates": [
    {{
      "title": "...",
      "angle": "一句话说明这个题关注什么"
    }}
  ]
}}

{TITLE_REASON_STYLE_EXAMPLE}

学校规则：
- 选题要求：{"；".join((profile.get("guide") or {}).get("selection_requirements") or [])}
- 推荐后缀：{"、".join((profile.get("title_style_rules") or {}).get("preferred_suffixes") or [])}
- 禁用表达：{"、".join((profile.get("title_style_rules") or {}).get("forbidden_patterns") or [])}

选题收敛判断：
{format_selection_diagnosis(diagnosis)}

证据包：
{build_evidence_pack(current, profile, grounding, evidence_items, diagnosis=diagnosis)}
""",
            temperature=0.35,
        )
    except LLMError:
        return []
    candidates = []
    for item in payload.get("candidates", []) if isinstance(payload, dict) else []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        angle = str(item.get("angle") or "").strip()
        if title:
            candidates.append({"title": title, "angle": angle})
    return candidates


def generate_candidate_recommendations(
    current: dict[str, Any],
    profile: dict[str, Any],
    grounding: dict[str, Any],
    evidence_items: list[dict[str, Any]],
    diagnosis: dict[str, Any],
    ranked_candidates: list[dict[str, Any]],
) -> dict[str, str]:
    if not is_enabled() or not ranked_candidates:
        return {}
    candidate_lines = []
    for index, item in enumerate(ranked_candidates, start=1):
        candidate_lines.append(
            f"{index}. {item['title']}（推荐度 {item['total_score']}；"
            f"学校 {item['school_fit']:.1f} / 导师 {item['mentor_fit']:.1f} / 岗位 {item['role_fit']:.1f} / 资料 {item['evidence_fit']:.1f}）"
        )
    try:
        payload = complete_json(
            "你是经管类专业硕士选题顾问。只输出 JSON，不要解释。",
            f"""
请为下面每个候选题写一句到两句“推荐理由”。

要求：
1. 不要写模板化条目，不要复述“25 字以内”“符合学校口径”这种机械结论
2. 要直接说清为什么推荐：优先说明对象边界、岗位贴合度、导师衔接、资料可做性
3. 语气像导师或选题顾问给判断，不像系统提示
4. 首选题可以写“优先推荐。”，其他题写“可作为备选。”或直接进入判断
5. 每条控制在 45 到 110 字，避免空话和套话

只返回 JSON：
{{
  "items": [
    {{
      "title": "...",
      "recommendation": "..."
    }}
  ]
}}

{TITLE_REASON_STYLE_EXAMPLE}

选题收敛判断：
{format_selection_diagnosis(diagnosis)}

候选题：
{chr(10).join(candidate_lines)}

证据包：
{build_evidence_pack(current, profile, grounding, evidence_items, diagnosis=diagnosis)}
""",
            temperature=0.45,
        )
    except LLMError:
        return {}
    recommendations: dict[str, str] = {}
    for item in payload.get("items", []) if isinstance(payload, dict) else []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        recommendation = str(item.get("recommendation") or "").strip()
        if title and recommendation:
            recommendations[title] = recommendation
    return recommendations


def generate_candidate_scores(
    current: dict[str, Any],
    profile: dict[str, Any],
    grounding: dict[str, Any],
    evidence_items: list[dict[str, Any]],
    diagnosis: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    if not is_enabled() or not candidates:
        return {}
    candidate_lines = []
    for index, item in enumerate(candidates, start=1):
        angle = str(item.get("angle") or "").strip()
        line = f"{index}. {item['title']}"
        if angle:
            line += f"｜切入点：{angle}"
        candidate_lines.append(line)
    try:
        payload = complete_json(
            "你是经管类专业硕士选题评审专家。只输出 JSON，不要解释。",
            f"""
请基于学校写作指南、导师方向、单位主营业务、岗位职责、问题线索和资料基础，对候选题做客观评分。

要求：
1. 分数范围 0-100，可以有 1 位小数
2. 分数不是机械平均，而是综合考虑“学校适配度、导师衔接度、岗位贴合度、资料可做性、题目边界清晰度”
3. 如果导师方向或单位主营业务缺失，要在理由里明确指出，而不是假装信息充分
4. 评分要拉开差距，不能所有题都几乎一样
5. 推荐理由不要在这里输出，这里只做评分与一句短评

只返回 JSON：
{{
  "items": [
    {{
      "title": "...",
      "score": 78.6,
      "short_comment": "..."
    }}
  ]
}}

学校规则：
- 选题要求：{"；".join((profile.get("guide") or {}).get("selection_requirements") or [])}
- 推荐后缀：{"、".join((profile.get("title_style_rules") or {}).get("preferred_suffixes") or [])}
- 禁用表达：{"、".join((profile.get("title_style_rules") or {}).get("forbidden_patterns") or [])}

选题收敛判断：
{format_selection_diagnosis(diagnosis)}

候选题：
{chr(10).join(candidate_lines)}

证据包：
{build_evidence_pack(current, profile, grounding, evidence_items, diagnosis=diagnosis)}
""",
            temperature=0.2,
        )
    except LLMError:
        return {}
    scores: dict[str, dict[str, Any]] = {}
    for item in payload.get("items", []) if isinstance(payload, dict) else []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        try:
            score = round(float(item.get("score")), 1)
        except Exception:
            continue
        short_comment = str(item.get("short_comment") or "").strip()
        scores[title] = {
            "score": max(0.0, min(score, 100.0)),
            "short_comment": short_comment,
        }
    return scores


def generate_report_section(
    section_name: str,
    current: dict[str, Any],
    profile: dict[str, Any],
    grounding: dict[str, Any],
    evidence_items: list[dict[str, Any]],
    diagnosis: dict[str, Any],
    title: str,
    citations: list[dict[str, Any]],
) -> str:
    if not is_enabled():
        raise LLMError("OPENAI_API_KEY is not configured")
    section_instruction = SECTION_GUIDANCE.get(section_name)
    if not section_instruction:
        raise LLMError(f"Unsupported section: {section_name}")
    citation_block = _citation_block(
        citations,
        detailed=section_name == "国内外关于该选题的动态",
    )
    try:
        return complete_text(
            "你是经管类专业硕士开题写作专家。请只根据证据写作，不得补造事实。",
            f"""
请写“{section_name}”这一章的正文，不要输出章节标题，只输出这一章的内容。

写作要求：
1. {section_instruction}
2. 文风要像真实开题报告，不要空泛套话，不要写成行业宣传稿
3. 只能使用给定事实、资料和文献；信息不足处要明说“当前资料显示”或“现有证据表明”
4. 不要直接照抄提示词里的句子
5. 如涉及文献评述，只能使用下面给出的文献编号

{REPORT_STYLE_EXAMPLE}

当前题目：{title}

选题收敛判断：
{format_selection_diagnosis(diagnosis)}

证据包：
{build_evidence_pack(current, profile, grounding, evidence_items, citations=citations, selected_title=title, diagnosis=diagnosis)}

文献摘要：
{citation_block}
""",
            temperature=0.4,
        ).strip()
    except LLMError:
        raise


def build_evidence_pack(
    current: dict[str, Any],
    profile: dict[str, Any],
    grounding: dict[str, Any],
    evidence_items: list[dict[str, Any]],
    *,
    citations: list[dict[str, Any]] | None = None,
    selected_title: str | None = None,
    diagnosis: dict[str, Any] | None = None,
) -> str:
    guide = profile.get("guide") or {}
    lines = [
        f"学校：{current.get('school_name') or profile.get('name') or '待确认'}",
        f"写作指南：{guide.get('title') or profile.get('name') or '待确认'}",
        f"指南摘要：{guide.get('summary') or '待补充'}",
        f"研究对象化名：{_subject_alias(current)}",
        f"导师：{current.get('mentor_name') or '待补充'}",
        f"学生岗位：{current.get('role_title') or '待补充'}",
        f"负责内容：{current.get('work_scope') or '待补充'}",
        f"拟研究方向：{current.get('research_direction') or '待补充'}",
        f"真实问题：{current.get('pain_point') or '待补充'}",
        f"研究目标：{current.get('research_goal') or '待补充'}",
        f"导师研究方向：{_list_text(grounding.get('mentor_research_fields'), fallback='待补充')}",
        f"导师学术擅长：{_list_text(grounding.get('mentor_expertise'), fallback='待补充')}",
        f"单位主营业务：{grounding.get('company_business') or '待补充'}",
        f"业务关键词：{_list_text(grounding.get('company_keywords'), fallback='待补充')}",
        f"岗位场景聚焦：{grounding.get('role_focus') or current.get('work_scope') or current.get('role_title') or '待补充'}",
        f"问题线索：{_list_text(grounding.get('problem_statements'), fallback='待补充')}",
        f"可用资料接口：{_list_text(grounding.get('usable_data_sources'), fallback='访谈、内部资料、公开网页资料')}",
    ]
    if selected_title:
        lines.append(f"已选题目：{selected_title}")
    if diagnosis:
        lines.append("选题收敛判断：" + format_selection_diagnosis(diagnosis))
    snippets = grounding.get("supporting_snippets") or []
    if snippets:
        lines.append("关键证据片段：")
        for item in snippets[:6]:
            lines.append(f"- [{item.get('kind')}] {item.get('title')}: {_short(item.get('snippet'), 90)}")
    if evidence_items:
        lines.append("资料与网页来源：")
        for item in evidence_items[:6]:
            title = str(item.get("title") or item.get("source_label") or item.get("id") or "资料")
            lines.append(f"- {_evidence_label(item)} {title}: {_short(_evidence_text(item), 90)}")
    if citations:
        lines.append("已核验文献：")
        for index, item in enumerate(citations[:6], start=1):
            meta = item.get("metadata") or {}
            lines.append(
                f"- [{index}] {meta.get('author', '佚名')}：《{meta.get('title', '题名待补充')}》，{meta.get('source', '来源待补充')}，{meta.get('year', '年份待补充')}"
            )
    return "\n".join(lines)[:9000]


def format_selection_diagnosis(diagnosis: dict[str, Any]) -> str:
    if not diagnosis:
        return "待补充"
    parts = [
        f"研究对象：{diagnosis.get('research_object') or '待补充'}",
        f"核心问题：{diagnosis.get('core_problem') or '待补充'}",
        f"推荐口径：{diagnosis.get('recommended_track') or '待补充'}",
        f"导师衔接：{diagnosis.get('advisor_alignment') or '待补充'}",
        f"岗位衔接：{diagnosis.get('job_alignment') or '待补充'}",
        f"资料基础：{diagnosis.get('data_foundation') or '待补充'}",
        f"收敛判断：{diagnosis.get('selection_logic') or '待补充'}",
    ]
    axes = _list_text(diagnosis.get("candidate_axes"), fallback="")
    if axes:
        parts.append(f"候选题切入角度：{axes}")
    avoid = _list_text(diagnosis.get("avoid_directions"), fallback="")
    if avoid:
        parts.append(f"应避免方向：{avoid}")
    missing = _list_text(diagnosis.get("missing_information"), fallback="")
    if missing:
        parts.append(f"仍缺信息：{missing}")
    return "；".join(parts)


def _fallback_selection_diagnosis(
    current: dict[str, Any],
    grounding: dict[str, Any],
    evidence_items: list[dict[str, Any]],
) -> dict[str, Any]:
    company_alias = _subject_alias(current)
    mentor_anchor = _list_text(grounding.get("mentor_research_fields"), fallback=str(current.get("research_direction") or "待补充"))
    company_business = str(grounding.get("company_business") or "主营业务待补充")
    role_focus = str(grounding.get("role_focus") or current.get("work_scope") or current.get("role_title") or "待补充")
    problem_focus = _list_text(grounding.get("problem_statements"), fallback=str(current.get("pain_point") or "待补充"))
    data_foundation = _list_text(grounding.get("usable_data_sources"), fallback="访谈、内部资料、公开网页资料")
    missing_information: list[str] = []
    if not str(current.get("mentor_name") or "").strip():
        missing_information.append("导师姓名")
    if not str(current.get("role_title") or "").strip():
        missing_information.append("岗位名称")
    if not str(current.get("work_scope") or "").strip():
        missing_information.append("负责内容")
    if not str(current.get("pain_point") or "").strip():
        missing_information.append("真实问题")
    if not evidence_items:
        missing_information.append("资料或公开链接")

    scene_text = " ".join(
        [
            str(current.get("role_title") or ""),
            str(current.get("work_scope") or ""),
            str(current.get("pain_point") or ""),
            str(current.get("research_goal") or ""),
            str(current.get("research_direction") or ""),
            str(grounding.get("company_business") or ""),
            " ".join(str(item) for item in grounding.get("company_keywords") or []),
        ]
    ).lower()
    if any(keyword in scene_text for keyword in ["协同", "流程", "跨部门", "组织"]):
        candidate_axes = ["组织协同优化", "管理机制优化", "问题诊断与优化"]
        recommended_track = "围绕组织协同、流程衔接和执行机制展开的专题研究"
    elif any(keyword in scene_text for keyword in ["数据", "知识", "治理", "接口"]):
        candidate_axes = ["数据准备机制", "知识沉淀与交付", "管理机制优化"]
        recommended_track = "围绕资料沉淀、数据准备与管理机制展开的专题研究"
    else:
        candidate_axes = ["管理机制优化", "组织协同优化", "管理问题诊断与优化"]
        recommended_track = "围绕单一对象的真实管理问题做诊断、解释与方案设计"

    return {
        "research_object": company_alias,
        "core_problem": problem_focus,
        "recommended_track": recommended_track,
        "candidate_axes": candidate_axes,
        "advisor_alignment": f"可优先对接导师的“{mentor_anchor}”方向",
        "job_alignment": f"当前工作场景集中在“{role_focus}”",
        "data_foundation": data_foundation,
        "selection_logic": (
            f"先把研究对象收敛到 {company_alias}，再从“{role_focus}”这一岗位场景中锁定"
            f"“{problem_focus}”这一真实管理问题，并与导师“{mentor_anchor}”方向形成对话。"
        ),
        "avoid_directions": [
            "宏大行业趋势分析",
            "纯技术算法效果比较",
            "脱离真实资料基础的泛化题目",
        ],
        "missing_information": missing_information,
    }


def _merge_selection_diagnosis(fallback: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return fallback
    merged = dict(fallback)
    for key in [
        "research_object",
        "core_problem",
        "recommended_track",
        "advisor_alignment",
        "job_alignment",
        "data_foundation",
        "selection_logic",
    ]:
        value = str(payload.get(key) or "").strip()
        if value:
            merged[key] = value
    for key in ["candidate_axes", "avoid_directions", "missing_information"]:
        value = payload.get(key)
        if isinstance(value, list):
            merged[key] = [str(item).strip() for item in value if str(item).strip()][:5] or merged.get(key, [])
    return merged


def _citation_block(citations: list[dict[str, Any]], *, detailed: bool = False) -> str:
    if not citations:
        return "当前没有通过核验的真实文献，不能编造文献观点。"
    chinese = [item for item in citations if not _is_foreign_citation(item.get("metadata") or {})]
    foreign = [item for item in citations if _is_foreign_citation(item.get("metadata") or {})]
    lines = []
    limit = 12 if detailed else 8
    if chinese:
        lines.append("中文文献：")
        for index, item in enumerate(chinese[: limit // 2 if detailed else limit], start=1):
            lines.extend(_citation_lines(index, item, detailed=detailed))
    if foreign:
        lines.append("外文文献：")
        start = len(chinese[: limit // 2 if detailed else limit]) + 1
        for offset, item in enumerate(foreign[: limit // 2 if detailed else limit], start=start):
            lines.extend(_citation_lines(offset, item, detailed=detailed))
    return "\n".join(lines)


def _citation_lines(index: int, item: dict[str, Any], *, detailed: bool) -> list[str]:
    metadata = item.get("metadata") or {}
    base = (
        f"[{index}] {metadata.get('author', '佚名')}：《{metadata.get('title', '题名待补充')}》，"
        f"{metadata.get('source', '来源待补充')}，{metadata.get('year', '年份待补充')}"
    )
    if not detailed:
        return [base]
    abstract = _short(metadata.get("abstract") or item.get("content", {}).get("excerpt") or "", 160)
    if not abstract:
        return [base]
    return [base, f"摘要要点：{abstract}"]


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
    has_latin = bool(re.search(r"[A-Za-z]", sample))
    has_cjk = bool(re.search(r"[\u4e00-\u9fff]", sample))
    return has_latin and not has_cjk


def _subject_alias(current: dict[str, Any]) -> str:
    return anonymized_subject_name(
        str(current.get("company_name") or "").strip(),
        str(current.get("confidentiality_notes") or ""),
    )


def _list_text(values: Any, fallback: str = "待补充") -> str:
    if isinstance(values, list):
        cleaned = [str(item).strip() for item in values if str(item).strip()]
        return "、".join(cleaned[:5]) if cleaned else fallback
    value = str(values or "").strip()
    return value or fallback


def _evidence_text(item: dict[str, Any]) -> str:
    content = item.get("content") or {}
    return str(content.get("excerpt") or content.get("text") or item.get("summary") or "").strip()


def _evidence_label(item: dict[str, Any]) -> str:
    evidence_type = str(item.get("evidence_type") or "")
    category = str((item.get("metadata") or {}).get("category") or "")
    if evidence_type == "local_file":
        return "[本地资料]"
    if category == "user_link" or evidence_type == "web_page":
        return "[参考链接]"
    if evidence_type == "citation":
        return "[文献]"
    if category == "mentor_profile":
        return "[导师网页]"
    if category == "company_profile":
        return "[单位网页]"
    return "[资料]"


def _short(text: Any, limit: int = 120) -> str:
    normalized = str(text or "").strip().replace("\n", " ")
    if len(normalized) <= limit:
        return normalized
    return normalized[:limit].rstrip("，；。、 ") + "..."
