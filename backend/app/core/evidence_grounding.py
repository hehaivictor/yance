from __future__ import annotations

import re
from typing import Any

from .llm import LLMError, complete_json, is_enabled


MENTOR_PATTERNS = [
    r"(?:研究方向|主要研究方向|研究领域|学术擅长领域|学术专长|擅长领域)[：: ]?([^\n。；]{6,80})",
    r"(?:长期从事|主要从事|聚焦于)([^\n。；]{6,80})",
]

COMPANY_PATTERNS = [
    r"(?:主营业务|主要业务|业务领域|公司主营|核心业务|经营范围)[：: ]?([^\n。；]{6,160})",
    r"(?:专注于|致力于|从事|提供)([^\n。；]{6,120})",
]

TITLE_KEYWORDS = [
    "AI",
    "智能体",
    "产品",
    "平台",
    "数据",
    "治理",
    "协同",
    "组织",
    "知识",
    "交付",
    "流程",
    "价值",
    "评估",
    "客户",
    "服务",
]

NOISE_HINTS = [
    "主要成就",
    "学术成果",
    "人物经历",
    "播报",
    "编辑",
    "获奖记录",
    "社会任职",
    "人物作品",
    "出版图书",
    "科研成就",
]

MENTOR_STOP_MARKERS = [
    "获奖与荣誉",
    "期刊论文",
    "代表性论文",
    "科研项目",
    "教育经历",
    "工作经历",
    "主讲课程",
    "教学课程",
    "Email",
    "邮箱",
    "电话",
]

COMPANY_STOP_MARKERS = [
    "登记状态",
    "注册资本",
    "成立日期",
    "统一社会信用代码",
    "法定代表人",
    "负责人",
    "电话",
    "邮箱",
    "地址",
    "股东信息",
    "监控",
    "报告",
    "复制",
]

COMPANY_NOISE_HINTS = [
    "分公司",
    "门店",
    "咸宁店",
    "富阳区",
    "存续",
    "注销",
    "开业",
    "小微企业",
    "同电话企业",
    "统一社会信用代码",
    "负责人",
    "法定代表人",
    "注册资本",
    "成立日期",
]


def evidence_text(item: dict[str, Any]) -> str:
    content = item.get("content") or {}
    metadata = item.get("metadata") or {}
    snippet = str(metadata.get("search_snippet") or "").strip()
    text = str(content.get("text") or content.get("excerpt") or item.get("summary") or "").strip()
    if snippet and snippet not in text[: max(len(snippet) + 20, 120)]:
        return f"{snippet}\n{text}".strip()
    return text


def build_grounding_context(
    current: dict[str, Any],
    evidence_items: list[dict[str, Any]],
    allow_llm: bool = True,
) -> dict[str, Any]:
    heuristic = _heuristic_grounding(current, evidence_items)
    if not allow_llm or not is_enabled():
        return heuristic
    dossier = _build_dossier(current, heuristic)
    if not dossier:
        return heuristic
    try:
        model_payload = _llm_grounding(current, dossier)
    except LLMError:
        return heuristic
    return _merge_grounding(heuristic, model_payload)


def format_grounding_for_prompt(grounding: dict[str, Any]) -> str:
    lines = [
        f"导师研究方向：{_format_list(grounding.get('mentor_research_fields'))}",
        f"导师学术擅长：{_format_list(grounding.get('mentor_expertise'))}",
        f"公司主营业务：{grounding.get('company_business') or '待补充'}",
        f"公司业务关键词：{_format_list(grounding.get('company_keywords'))}",
        f"角色与场景聚焦：{grounding.get('role_focus') or '待补充'}",
        f"真实问题线索：{_format_list(grounding.get('problem_statements'))}",
        f"可用资料基础：{_format_list(grounding.get('usable_data_sources'))}",
    ]
    snippets = grounding.get("supporting_snippets") or []
    if snippets:
        lines.append("关键依据片段：")
        for item in snippets[:8]:
            lines.append(f"- [{item['kind']}] {item['title']}：{item['snippet']}")
    return "\n".join(lines)


def collect_grounding_reasons(grounding: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if grounding.get("mentor_research_fields"):
        reasons.append(f"已提取导师研究方向：{_format_list(grounding['mentor_research_fields'])}。")
    if grounding.get("mentor_expertise"):
        reasons.append(f"已提取导师学术擅长：{_format_list(grounding['mentor_expertise'])}。")
    if grounding.get("company_business"):
        reasons.append(f"已提取单位主营业务：{grounding['company_business']}。")
    if grounding.get("company_keywords"):
        reasons.append(f"已提取单位业务关键词：{_format_list(grounding['company_keywords'])}。")
    snippets = grounding.get("supporting_snippets") or []
    if snippets:
        reasons.append(f"当前候选题已参考 {len(snippets)} 条资料/网页关键片段。")
    return reasons


def _heuristic_grounding(current: dict[str, Any], evidence_items: list[dict[str, Any]]) -> dict[str, Any]:
    mentor_name = str(current.get("mentor_name") or "").strip()
    company_name = str(current.get("company_name") or "").strip()
    mentor_lines: list[str] = []
    company_lines: list[str] = []
    snippets: list[dict[str, Any]] = []
    role_focus = "；".join(
        item.strip()
        for item in [str(current.get("role_title") or ""), str(current.get("work_scope") or "")]
        if item.strip()
    )
    for evidence in evidence_items:
        text = evidence_text(evidence)
        title = str(evidence.get("title") or evidence.get("source_label") or evidence.get("id") or "资料").strip()
        if not text:
            continue
        lines = _split_lines(text)
        kind = _evidence_kind(evidence)
        if mentor_name and (mentor_name in text or mentor_name in title or kind == "mentor"):
            mentor_lines.extend(lines[:24])
        if company_name and (company_name in text or company_name in title or kind == "company"):
            company_lines.extend(lines[:24])
        score = _snippet_score(lines, current, kind)
        if score > 0:
            top_lines = _best_grounding_lines(lines, current, kind)
            if top_lines:
                snippets.append(
                    {
                        "score": score,
                        "kind": kind,
                        "title": title[:48],
                        "snippet": "；".join(top_lines)[:180],
                    }
                )

    seeded_mentor_fields = _split_seeded_values(current.get("mentor_research_fields"))
    seeded_mentor_expertise = _split_seeded_values(current.get("mentor_expertise"))
    seeded_company_keywords = _split_seeded_values(current.get("company_keywords"))
    extracted_mentor_fields = _extract_matches(mentor_lines, MENTOR_PATTERNS, stop_markers=MENTOR_STOP_MARKERS)
    extracted_mentor_expertise = _extract_course_topics(mentor_lines)
    extracted_company_business = _extract_first(company_lines, COMPANY_PATTERNS, stop_markers=COMPANY_STOP_MARKERS)
    mentor_research_fields = _dedupe_list(seeded_mentor_fields + extracted_mentor_fields)[:5]
    mentor_expertise = _dedupe_list(seeded_mentor_expertise + mentor_research_fields + extracted_mentor_expertise)[:5]
    company_business = str(current.get("company_business") or "").strip() or extracted_company_business
    company_keywords = _dedupe_list(seeded_company_keywords + _business_keywords(company_business, company_lines))[:6]
    problem_statements = _best_problem_lines(current, evidence_items)
    usable_data_sources = _data_source_labels(evidence_items)
    ordered_snippets = [
        {key: value for key, value in item.items() if key != "score"}
        for item in sorted(snippets, key=lambda payload: int(payload.get("score", 0)), reverse=True)[:10]
    ]

    return {
        "mentor_research_fields": mentor_research_fields,
        "mentor_expertise": mentor_expertise,
        "company_business": company_business,
        "company_keywords": company_keywords,
        "role_focus": role_focus,
        "problem_statements": problem_statements,
        "usable_data_sources": usable_data_sources,
        "supporting_snippets": ordered_snippets,
    }


def _llm_grounding(current: dict[str, Any], dossier: str) -> dict[str, Any]:
    payload = complete_json(
        "你是经管类开题资料分析助手。只能根据给定证据抽取，不得脑补。",
        f"""
请根据下面的证据，为候选题与开题报告生成结构化依据。
要求：
1. 只从证据里提取，不要补写不存在的信息
2. 字段尽量短句化，适合直接进入后续题目生成与报告生成
3. 返回 JSON，字段如下：
{{
  "mentor_research_fields": ["..."],
  "mentor_expertise": ["..."],
  "company_business": "...",
  "company_keywords": ["..."],
  "role_focus": "...",
  "problem_statements": ["..."],
  "usable_data_sources": ["..."]
}}

当前表单：
- 学校：{current.get("school_name", "")}
- 导师：{current.get("mentor_name", "")}
- 单位：{current.get("company_name", "")}
- 职位：{current.get("role_title", "")}
- 负责内容：{current.get("work_scope", "")}
- 拟研究方向：{current.get("research_direction", "")}
- 真实问题：{current.get("pain_point", "")}

证据：
{dossier}
""",
        temperature=0.1,
    )
    return payload if isinstance(payload, dict) else {}


def _build_dossier(current: dict[str, Any], grounding: dict[str, Any]) -> str:
    blocks = []
    if grounding.get("mentor_research_fields"):
        blocks.append(f"导师研究方向：{_format_list(grounding.get('mentor_research_fields'))}")
    if grounding.get("mentor_expertise"):
        blocks.append(f"导师学术擅长：{_format_list(grounding.get('mentor_expertise'))}")
    if grounding.get("company_business"):
        blocks.append(f"单位主营业务：{grounding.get('company_business')}")
    if grounding.get("role_focus"):
        blocks.append(f"岗位与职责：{grounding.get('role_focus')}")
    if grounding.get("problem_statements"):
        blocks.append(f"问题线索：{_format_list(grounding.get('problem_statements'))}")
    for item in grounding.get("supporting_snippets") or []:
        blocks.append(f"[{item['kind']}] {item['title']}：{item['snippet']}")
    joined = "\n".join(blocks[:10])
    return joined[:6000]


def _merge_grounding(heuristic: dict[str, Any], model_payload: dict[str, Any]) -> dict[str, Any]:
    merged = dict(heuristic)
    for key in [
        "mentor_research_fields",
        "mentor_expertise",
        "company_keywords",
        "problem_statements",
        "usable_data_sources",
    ]:
        values = model_payload.get(key) or heuristic.get(key) or []
        if isinstance(values, list):
            merged[key] = _dedupe_list([str(item).strip() for item in values if str(item).strip()])[:5]
    for key in ["company_business", "role_focus"]:
        merged[key] = str(model_payload.get(key) or heuristic.get(key) or "").strip()
    return merged


def _split_lines(text: str) -> list[str]:
    raw = re.split(r"[\n。！？；]", str(text or ""))
    lines: list[str] = []
    for item in raw:
        cleaned = re.sub(r"\s+", " ", item).strip(" -:：")
        if not cleaned or _is_noise_text(cleaned):
            continue
        lines.append(cleaned)
    return lines


def _extract_matches(lines: list[str], patterns: list[str], stop_markers: list[str] | None = None) -> list[str]:
    hits: list[str] = []
    for line in lines:
        for pattern in patterns:
            match = re.search(pattern, line)
            if match:
                value = _clip_stop_markers(match.group(1), stop_markers or [])
                hits.extend(_split_phrase(value))
    return _dedupe_list(hits)[:5]


def _extract_first(lines: list[str], patterns: list[str], stop_markers: list[str] | None = None) -> str:
    for line in lines:
        for pattern in patterns:
            match = re.search(pattern, line)
            if not match:
                continue
            value = re.sub(r"\s+", " ", _clip_stop_markers(match.group(1), stop_markers or [])).strip(" ：:;；，,")
            if value and not _is_noise_text(value):
                return value[:160]
    values = _extract_matches(lines, patterns, stop_markers=stop_markers)
    if values:
        return "；".join(values[:2])
    business_line = next((line for line in lines if any(word in line for word in ["业务", "产品", "解决方案", "服务", "平台"])), "")
    return business_line[:120]


def _extract_keywords(lines: list[str], keywords: list[str]) -> list[str]:
    hits: list[str] = []
    for line in lines:
        for keyword in keywords:
            if keyword and keyword.lower() in line.lower():
                hits.append(keyword)
    return _dedupe_list(hits)[:6]


def _best_problem_lines(current: dict[str, Any], evidence_items: list[dict[str, Any]]) -> list[str]:
    seeded = [str(current.get("pain_point") or "").strip(), str(current.get("work_scope") or "").strip()]
    if any(seeded):
        direct = [item for item in seeded if item]
        if direct:
            return direct[:4]
    keywords = [
        str(current.get("pain_point") or ""),
        str(current.get("research_direction") or ""),
        str(current.get("role_title") or ""),
        "问题",
        "痛点",
        "瓶颈",
        "低效",
        "协同",
        "交付",
        "数据",
        "治理",
    ]
    ranked: list[tuple[int, str]] = []
    for evidence in evidence_items:
        if _evidence_kind(evidence) == "mentor":
            continue
        for line in _split_lines(evidence_text(evidence)):
            score = sum(1 for keyword in keywords if keyword and keyword.lower() in line.lower())
            if score:
                ranked.append((score, line))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return _dedupe_list([item[1] for item in ranked])[:4]


def _data_source_labels(evidence_items: list[dict[str, Any]]) -> list[str]:
    labels: list[str] = []
    if any(item.get("metadata", {}).get("kind") == "mentor" for item in evidence_items):
        labels.append("导师主页")
    if any(item.get("metadata", {}).get("kind") == "company" for item in evidence_items):
        labels.append("公司官网")
    if any(item.get("evidence_type") == "local_file" for item in evidence_items):
        labels.append("本地资料")
    if any(item.get("metadata", {}).get("category") == "internal_material" for item in evidence_items):
        labels.append("内部材料")
    if any(item.get("evidence_type") in {"web_page", "public_web"} for item in evidence_items):
        labels.append("公开网页")
    if any(item.get("evidence_type") == "citation" and item.get("status") == "verified" for item in evidence_items):
        labels.append("核验文献")
    return labels


def _snippet_score(lines: list[str], current: dict[str, Any], kind: str) -> int:
    keywords = [
        str(current.get("mentor_name") or ""),
        str(current.get("company_name") or ""),
        str(current.get("role_title") or ""),
        str(current.get("research_direction") or ""),
        str(current.get("work_scope") or ""),
        str(current.get("pain_point") or ""),
    ]
    score = 0
    joined = " ".join(lines[:8]).lower()
    for keyword in keywords:
        if keyword and keyword.lower() in joined:
            score += 3
    if kind in {"mentor", "company"}:
        score += 2
    if kind in {"local_file", "web_link"}:
        score += 1
    return score


def _best_lines(lines: list[str], current: dict[str, Any], limit: int) -> list[str]:
    keywords = [
        str(current.get("role_title") or ""),
        str(current.get("work_scope") or ""),
        str(current.get("research_direction") or ""),
        str(current.get("pain_point") or ""),
        "研究方向",
        "业务",
        "产品",
        "问题",
        "场景",
        "数据",
    ]
    ranked: list[tuple[int, str]] = []
    for line in lines:
        score = sum(1 for keyword in keywords if keyword and keyword.lower() in line.lower())
        if score:
            ranked.append((score, line))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [item[1] for item in ranked[:limit]]


def _best_grounding_lines(lines: list[str], current: dict[str, Any], kind: str) -> list[str]:
    if kind == "mentor":
        hints = ["研究方向", "研究领域", "学术专长", "擅长领域", "教学课程", "本科：", "MBA：", "EMBA："]
    elif kind == "company":
        hints = ["主营业务", "经营范围", "公司简介", "品牌介绍", "产品", "服务", "零售", "设计", "制造"]
    else:
        return _best_lines(lines, current, 2)
    ranked: list[tuple[int, str]] = []
    for line in lines:
        score = sum(2 for hint in hints if hint and hint in line)
        if kind == "company" and any(hint in line for hint in COMPANY_NOISE_HINTS):
            score -= 4
        if kind == "mentor" and any(marker in line for marker in MENTOR_STOP_MARKERS):
            score -= 2
        if score > 0:
            ranked.append((score, line))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [item[1] for item in ranked[:2]]


def _split_phrase(value: str) -> list[str]:
    results: list[str] = []
    for item in re.split(r"[，,、；;/]", value):
        cleaned = item.strip(" ，,、；;")
        if not cleaned or _is_noise_text(cleaned):
            continue
        if any(noise in cleaned for noise in COMPANY_NOISE_HINTS):
            continue
        if len(cleaned) > 26 and not any(keyword in cleaned for keyword in ["研究", "创新", "数字", "数据", "服务", "产品", "业务"]):
            continue
        results.append(cleaned)
    return results


def _extract_course_topics(lines: list[str]) -> list[str]:
    joined = " ".join(lines[:12])
    topics: list[str] = []
    for match in re.finditer(
        r"(?:本科|MBA|EMBA)\s*[:：]\s*(.+?)(?=(?:本科|MBA|EMBA|研究\s*领域|研究\s*方向|获奖与荣誉|$))",
        joined,
    ):
        topics.extend(_split_phrase(match.group(1)))
    return _dedupe_list(topics)[:5]


def _business_keywords(company_business: str, lines: list[str]) -> list[str]:
    phrases: list[str] = []
    for item in re.split(r"[，,、；;/\s]+", company_business):
        cleaned = item.strip("，,、；;/ ")
        if cleaned.startswith("销售") and len(cleaned) > 2:
            cleaned = cleaned[2:]
        if (
            cleaned
            and 2 <= len(cleaned) <= 12
            and not _is_noise_text(cleaned)
            and not any(noise in cleaned for noise in COMPANY_NOISE_HINTS)
        ):
            phrases.append(cleaned)
    industry_hints = [
        "服装零售",
        "服装服饰零售",
        "服装",
        "鞋帽",
        "箱包",
        "针织品",
        "家居用品",
        "床上用品",
        "日用百货",
        "品牌",
        "零售",
    ]
    phrases.extend(_extract_keywords(lines, industry_hints))
    return _dedupe_list(phrases)[:6]


def _clip_stop_markers(value: str, stop_markers: list[str]) -> str:
    clipped = str(value or "").strip()
    for marker in stop_markers:
        index = clipped.find(marker)
        if index > 0:
            clipped = clipped[:index].strip(" ：:;；，,")
    return clipped


def _evidence_kind(item: dict[str, Any]) -> str:
    kind = str(item.get("metadata", {}).get("kind") or item.get("metadata", {}).get("category") or "")
    if kind == "mentor":
        return "mentor"
    if kind == "company":
        return "company"
    if item.get("evidence_type") == "local_file":
        return "local_file"
    if item.get("evidence_type") in {"web_page", "public_web"}:
        return "web_link"
    return str(item.get("evidence_type") or "evidence")


def _dedupe_list(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output


def _is_noise_text(text: str) -> bool:
    normalized = str(text or "").strip()
    if not normalized:
        return True
    if any(hint in normalized for hint in NOISE_HINTS):
        return True
    if re.search(r"[0-9]{2,}", normalized) and not any(keyword in normalized for keyword in ["202", "20"]):
        return True
    if len(normalized) <= 1:
        return True
    return False


def _format_list(values: Any) -> str:
    if isinstance(values, list):
        cleaned = [str(item).strip() for item in values if str(item).strip()]
        return "、".join(cleaned) if cleaned else "待补充"
    return str(values or "待补充")


def _split_seeded_values(values: Any) -> list[str]:
    if isinstance(values, list):
        raw_values = values
    else:
        raw_values = re.split(r"[、；;，,\n]+", str(values or ""))
    return _dedupe_list([str(item).strip() for item in raw_values if str(item).strip()])
