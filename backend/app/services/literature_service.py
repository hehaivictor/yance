from __future__ import annotations

import math
import re
from datetime import datetime
from typing import Any

import requests

from ..config import settings
from ..core.llm import LLMError, complete_json, is_enabled
from ..core.paper_reasoning import build_evidence_pack, format_selection_diagnosis
from ..core.parsing import build_citation_reference, citation_completeness_score
from ..core.search import request_session
from ..db import get_connection
from .workspace_service import add_evidence_item, list_evidence_items


AUTO_CITATION_LABEL = "系统自动检索文献"

TRUSTED_ENGLISH_SOURCES = [
    "Decision Support Systems",
    "International Journal of Retail & Distribution Management",
    "Journal of Retailing",
    "Journal of Retailing and Consumer Services",
    "Information & Management",
    "Decision Sciences",
    "European Journal of Operational Research",
    "Management Science",
    "Omega",
    "Journal of Business Research",
    "Journal of Business Logistics",
    "Journal of Strategic Information Systems",
    "International Journal of Production Economics",
    "Industrial Marketing Management",
    "International Marketing Review",
    "Journal of Product & Brand Management",
    "Asia Pacific Journal of Marketing and Logistics",
    "Marketing Intelligence & Planning",
    "Manufacturing & Service Operations Management",
    "Transportation Research Part E Logistics and Transportation Review",
    "Operations Management Research",
    "Business Strategy and the Environment",
    "Australasian Marketing Journal",
    "Journal of the Operational Research Society",
    "Flexible Services and Manufacturing Journal",
]

TRUSTED_CHINESE_SOURCES = [
    "管理世界",
    "南开管理评论",
    "管理评论",
    "管理学报",
    "科研管理",
    "经济管理",
    "商业经济研究",
    "商业研究",
    "中国流通经济",
    "财贸经济",
    "外国经济与管理",
    "中国工业经济",
    "中国软科学",
    "系统工程理论与实践",
    "预测",
    "调研世界",
    "现代管理科学",
    "企业经济",
    "改革",
    "财经论丛",
    "商业经济与管理",
    "华东经济管理",
]

SUSPICIOUS_SOURCE_MARKERS = [
    "academic frontiers",
    "frontiers publishing group",
    "经济管理前沿",
    "现代经济管理",
    "财经管理",
    "环球经济与管理",
    "经济管理研究",
    "社会企业经济发展",
    "international economy and development",
    "global",
    "modern management",
    "e-commerce letters",
    "科技创新发展",
    "工程施工新技术",
    "机械与电子控制工程",
    "电子通信与计算机科学",
    "智慧教育",
    "zenodo",
    "scholarworks",
    "procedia",
    "ifac-papersonline",
    "全国商情",
    "纺织服装周刊",
    "广告主",
    "新食品",
    "中国农资",
    "信息方略",
    "汽车与配件",
]


def ensure_remote_citations(
    *,
    workspace_id: str,
    title: str,
    current: dict[str, Any],
    profile: dict[str, Any],
    grounding: dict[str, Any],
    evidence_items: list[dict[str, Any]],
    diagnosis: dict[str, Any],
) -> list[dict[str, Any]]:
    min_total, min_foreign = _reference_targets(profile)
    manual_citations = [
        item
        for item in _verified_citations(evidence_items)
        if not bool((item.get("metadata") or {}).get("auto_collected"))
    ]
    if _meets_reference_requirements(manual_citations, min_total=min_total, min_foreign=min_foreign):
        return _ordered_citations(manual_citations)
    if not is_enabled():
        raise ValueError("当前未配置模型，无法自动联网检索真实文献。")

    search_plan = _generate_literature_search_plan(
        title=title,
        current=current,
        profile=profile,
        grounding=grounding,
        evidence_items=evidence_items,
        diagnosis=diagnosis,
    )
    existing_keys = {_citation_identity(item.get("metadata") or {}) for item in manual_citations}
    pool = _collect_remote_records(search_plan, existing_keys)
    if not pool:
        raise ValueError("没有检索到可核验的真实文献，请补充题目边界或资料后重试。")
    pool = _prioritize_records_with_model(
        title=title,
        current=current,
        profile=profile,
        grounding=grounding,
        diagnosis=diagnosis,
        records=pool,
    )

    target_total = max(min_total - len(manual_citations), 0)
    target_foreign = max(min_foreign - _foreign_count(manual_citations), 0)
    selected = _select_records(
        pool,
        desired_total=target_total,
        desired_foreign=target_foreign,
    )
    if len(selected) < target_total or _foreign_count(selected) < target_foreign:
        raise ValueError("自动检索到的真实文献不足以满足武汉大学开题报告要求，请继续补强研究边界后重试。")

    _replace_auto_citations(workspace_id, selected)
    refreshed = _verified_citations(list_evidence_items(workspace_id))
    if not _meets_reference_requirements(refreshed, min_total=min_total, min_foreign=min_foreign):
        raise ValueError("自动检索文献后仍未满足武汉大学开题报告文献要求。")
    return _ordered_citations(refreshed)


def _generate_literature_search_plan(
    *,
    title: str,
    current: dict[str, Any],
    profile: dict[str, Any],
    grounding: dict[str, Any],
    evidence_items: list[dict[str, Any]],
    diagnosis: dict[str, Any],
) -> dict[str, Any]:
    seed_plan = _seed_search_plan(title, current, grounding, diagnosis)
    summary = _literature_context_summary(title, current, profile, grounding, diagnosis)
    try:
        payload = complete_json(
            "你是经管类专业硕士文献检索专家。你只负责设计检索式，不输出任何虚构文献。",
            f"""
请围绕当前已选题目，设计一组“真实可检索”的文献检索式，用于从互联网学术数据库中检索开题报告文献。

要求：
1. 只输出 JSON
2. 不要把企业化名（如 A公司/K公司/Y公司）直接放进查询词
3. 中文检索式聚焦真实管理问题、行业场景、导师研究方向
4. 英文检索式聚焦对应的管理学、营销学、组织协同、决策支持等主题
5. 至少给 5 条中文检索式和 5 条英文检索式
6. 额外给出 6 到 10 个核心主题词，供后续做相关性过滤
7. 检索目标是为武汉大学专业硕士开题报告补齐真实文献，不是泛行业新闻

返回格式：
{{
  "chinese_queries": ["..."],
  "english_queries": ["..."],
  "topic_terms": ["..."],
  "search_focus": "..."
}}

当前研究概要：
{summary}
""",
            temperature=0.2,
        )
    except LLMError as exc:
        return _fallback_search_plan(title, current, grounding, diagnosis)
    chinese_queries = _clean_query_list(payload.get("chinese_queries", []))
    english_queries = _clean_query_list(payload.get("english_queries", []))
    topic_terms = _clean_topic_terms(payload.get("topic_terms", []))
    title_terms = _title_focus_terms(title)
    topic_terms = _dedupe_preserve(seed_plan["topic_terms"] + title_terms + topic_terms)[:10]
    chinese_queries = _dedupe_preserve(seed_plan["chinese_queries"] + chinese_queries)[:8]
    english_queries = _dedupe_preserve(seed_plan["english_queries"] + english_queries)[:8]
    if len(chinese_queries) < 3 or len(english_queries) < 3 or len(topic_terms) < 4:
        return _fallback_search_plan(title, current, grounding, diagnosis)
    return {
        "chinese_queries": chinese_queries[:8],
        "english_queries": english_queries[:8],
        "topic_terms": topic_terms[:10],
        "search_focus": str(payload.get("search_focus") or "").strip(),
    }


def _collect_remote_records(plan: dict[str, Any], existing_keys: set[str]) -> list[dict[str, Any]]:
    topic_terms = _expand_topic_terms([str(item).strip() for item in plan.get("topic_terms", []) if str(item).strip()])
    records: list[dict[str, Any]] = []
    seen_keys = set(existing_keys)
    chinese_queries = list(plan.get("chinese_queries", []))
    english_queries = list(plan.get("english_queries", []))
    queries = chinese_queries + english_queries
    for query in queries:
        try:
            results = _search_openalex(query)
        except Exception:
            continue
        for item in results:
            key = _citation_identity(item)
            if not key or key in seen_keys:
                continue
            if not _passes_record_quality(item, topic_terms):
                continue
            item["relevance_score"] = _literature_relevance_score(item, topic_terms)
            item["query"] = query
            item["provider"] = "openalex"
            seen_keys.add(key)
            records.append(item)
    crossref_queries = list(chinese_queries)
    if len(records) < 24:
        crossref_queries.extend(english_queries[:3])
    for query in crossref_queries:
        try:
            results = _search_crossref(query)
        except Exception:
            continue
        for item in results:
            if not _passes_record_quality(item, topic_terms):
                continue
            key = _citation_identity(item)
            if not key or key in seen_keys:
                continue
            item["relevance_score"] = _literature_relevance_score(item, topic_terms)
            item["query"] = query
            item["provider"] = "crossref"
            seen_keys.add(key)
            records.append(item)
    records.sort(key=lambda item: item.get("relevance_score", 0.0), reverse=True)
    return records[:120]


def _literature_context_summary(
    title: str,
    current: dict[str, Any],
    profile: dict[str, Any],
    grounding: dict[str, Any],
    diagnosis: dict[str, Any],
) -> str:
    guide = profile.get("guide") or {}
    parts = [
        f"题目：{title}",
        f"题目核心问题：{_join_text(_title_focus_terms(title))}",
        f"学校：{current.get('school_name') or profile.get('name') or '待确认'}",
        f"指南：{guide.get('summary') or '待补充'}",
        f"导师：{current.get('mentor_name') or '待补充'}",
        f"导师方向：{_join_text(grounding.get('mentor_research_fields'))}",
        f"导师擅长：{_join_text(grounding.get('mentor_expertise'))}",
        f"单位主营业务：{grounding.get('company_business') or current.get('company_name') or '待补充'}",
        f"业务关键词：{_join_text(grounding.get('company_keywords'))}",
        f"岗位：{current.get('role_title') or '待补充'}",
        f"负责内容：{current.get('work_scope') or '待补充'}",
        f"核心问题：{diagnosis.get('core_problem') or '待补充'}",
        f"候选切口：{_join_text(diagnosis.get('candidate_axes'))}",
        f"研究口径：{diagnosis.get('recommended_track') or '待补充'}",
    ]
    return "\n".join(parts)


def _search_openalex(query: str, per_page: int = 20) -> list[dict[str, Any]]:
    session = request_session()
    response = session.get(
        "https://api.openalex.org/works",
        params={
            "search": query,
            "per-page": per_page,
            "filter": "type:article,from_publication_date:2012-01-01",
        },
        timeout=max(settings.search_timeout_seconds, 20),
    )
    response.raise_for_status()
    results: list[dict[str, Any]] = []
    for item in response.json().get("results", []) or []:
        normalized = _normalize_openalex(item)
        if normalized:
            results.append(normalized)
    return results


def _search_crossref(query: str, rows: int = 14) -> list[dict[str, Any]]:
    session = request_session()
    response = session.get(
        "https://api.crossref.org/works",
        params={
            "query.bibliographic": query,
            "rows": rows,
            "filter": "type:journal-article,from-pub-date:2012-01-01",
        },
        timeout=max(settings.search_timeout_seconds, 20),
    )
    response.raise_for_status()
    results: list[dict[str, Any]] = []
    for item in response.json().get("message", {}).get("items", []) or []:
        normalized = _normalize_crossref(item)
        if normalized:
            results.append(normalized)
    return results


def _normalize_openalex(item: dict[str, Any]) -> dict[str, Any] | None:
    title = str(item.get("display_name") or "").strip()
    year = item.get("publication_year")
    if not title or not year:
        return None
    primary_location = item.get("primary_location") or {}
    source = (primary_location.get("source") or {}).get("display_name") or ""
    doi = str(item.get("doi") or "").strip()
    landing_page = str(primary_location.get("landing_page_url") or item.get("id") or "").strip()
    if not source:
        return None
    authors = []
    for authorship in item.get("authorships", []) or []:
        author = (authorship.get("author") or {}).get("display_name")
        if author:
            authors.append(str(author).strip())
    abstract = _abstract_from_inverted_index(item.get("abstract_inverted_index") or {})
    metadata = {
        "author": "; ".join(authors),
        "title": title,
        "year": str(year),
        "source": source,
        "doi": doi,
        "url": landing_page,
        "language": str(item.get("language") or "").strip(),
        "abstract": abstract,
        "provider": "openalex",
        "cited_by_count": int(item.get("cited_by_count") or 0),
        "work_id": str(item.get("id") or "").strip(),
        "type": str(item.get("type_crossref") or item.get("type") or "").strip(),
        "source_type": str((primary_location.get("source") or {}).get("type") or "").strip(),
        "source_is_core": bool((primary_location.get("source") or {}).get("is_core")),
        "source_host": str((primary_location.get("source") or {}).get("host_organization_name") or "").strip(),
    }
    is_complete, _ = citation_completeness_score(metadata)
    return metadata if is_complete else None


def _normalize_crossref(item: dict[str, Any]) -> dict[str, Any] | None:
    title = str((item.get("title") or [""])[0] or "").strip()
    if not title:
        return None
    year = ""
    for key in ["published-print", "published-online", "issued"]:
        parts = (item.get(key) or {}).get("date-parts") or []
        if parts and parts[0]:
            year = str(parts[0][0])
            break
    authors = []
    for author in item.get("author", []) or []:
        name = " ".join(part for part in [author.get("given", ""), author.get("family", "")] if part).strip()
        if name:
            authors.append(name)
    metadata = {
        "author": "; ".join(authors),
        "title": title,
        "year": year,
        "source": str((item.get("container-title") or [""])[0] or "").strip(),
        "doi": str(item.get("DOI") or "").strip(),
        "url": str(item.get("URL") or "").strip(),
        "language": "",
        "abstract": _clean_crossref_abstract(str(item.get("abstract") or "").strip()),
        "provider": "crossref",
        "cited_by_count": int(item.get("is-referenced-by-count") or 0),
        "work_id": str(item.get("DOI") or item.get("URL") or "").strip(),
        "type": str(item.get("type") or "").strip(),
    }
    is_complete, _ = citation_completeness_score(metadata)
    return metadata if is_complete else None


def _select_records(records: list[dict[str, Any]], *, desired_total: int, desired_foreign: int) -> list[dict[str, Any]]:
    if desired_total <= 0:
        return []
    foreign = [item for item in records if _is_foreign_record(item)]
    ranked = list(records)

    selected: list[dict[str, Any]] = []
    used = set()

    for item in foreign:
        if len(selected) >= desired_foreign:
            break
        key = _citation_identity(item)
        if key and key not in used:
            used.add(key)
            selected.append(item)

    for item in ranked:
        if len(selected) >= desired_total:
            break
        key = _citation_identity(item)
        if key and key not in used:
            used.add(key)
            selected.append(item)
    return selected


def _fallback_search_plan(
    title: str,
    current: dict[str, Any],
    grounding: dict[str, Any],
    diagnosis: dict[str, Any],
) -> dict[str, Any]:
    seed_plan = _seed_search_plan(title, current, grounding, diagnosis)
    topic_terms = _dedupe_preserve(seed_plan["topic_terms"] + _fallback_topic_terms(title, current, grounding, diagnosis))
    chinese_queries = _dedupe_preserve(seed_plan["chinese_queries"] + _fallback_chinese_queries(topic_terms))
    english_queries = _dedupe_preserve(seed_plan["english_queries"] + _fallback_english_queries(topic_terms))
    return {
        "chinese_queries": chinese_queries[:8],
        "english_queries": english_queries[:8],
        "topic_terms": topic_terms[:10],
        "search_focus": "围绕研究对象场景、核心管理问题、导师方向和行业背景自动组合检索式",
    }


def _replace_auto_citations(workspace_id: str, records: list[dict[str, Any]]) -> None:
    _delete_auto_citations(workspace_id)
    for index, record in enumerate(_ordered_citations_from_metadata(records), start=1):
        reference = build_citation_reference(record, index)
        add_evidence_item(
            workspace_id=workspace_id,
            evidence_type="citation",
            title=record.get("title") or f"文献 {index}",
            summary=reference,
            grade="A" if record.get("abstract") else "B",
            status="verified",
            source_label=AUTO_CITATION_LABEL,
            source_uri=record.get("doi") or record.get("url") or record.get("work_id"),
            source_date=record.get("year", ""),
            metadata={
                **record,
                "auto_collected": True,
            },
            content={
                "reference": reference,
                "text": str(record.get("abstract") or ""),
                "excerpt": str(record.get("abstract") or "")[:4000],
            },
        )


def _delete_auto_citations(workspace_id: str) -> None:
    auto_ids = [
        item["id"]
        for item in list_evidence_items(workspace_id)
        if item.get("evidence_type") == "citation" and bool((item.get("metadata") or {}).get("auto_collected"))
    ]
    if not auto_ids:
        return
    with get_connection() as connection:
        connection.executemany("DELETE FROM evidence_items WHERE id = ?", [(item_id,) for item_id in auto_ids])


def _verified_citations(evidence_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items = []
    for item in evidence_items:
        if item.get("evidence_type") != "citation":
            continue
        is_complete, _ = citation_completeness_score(item.get("metadata") or {})
        if item.get("status") == "verified" and is_complete:
            items.append(item)
    return _ordered_citations(items)


def _ordered_citations(citations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        citations,
        key=lambda item: _citation_sort_key(item.get("metadata") or {}),
    )


def _ordered_citations_from_metadata(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(records, key=_citation_sort_key)


def _citation_sort_key(metadata: dict[str, Any]) -> tuple[int, int, str]:
    year = int(str(metadata.get("year") or "0")[:4] or 0)
    return (1 if _is_foreign_record(metadata) else 0, -year, str(metadata.get("title") or ""))


def _meets_reference_requirements(citations: list[dict[str, Any]], *, min_total: int, min_foreign: int) -> bool:
    return len(citations) >= min_total and _foreign_count(citations) >= min_foreign


def _reference_targets(profile: dict[str, Any]) -> tuple[int, int]:
    guide = profile.get("guide") or {}
    requirements = guide.get("reference_requirements") or {}
    min_total = int(requirements.get("opening_report_min_items", 30))
    min_foreign = max(1, round(min_total * float(requirements.get("opening_report_foreign_ratio_min", 0.3333))))
    return min_total, min_foreign


def _foreign_count(citations: list[dict[str, Any]]) -> int:
    return sum(1 for item in citations if _is_foreign_record(item.get("metadata") if isinstance(item, dict) and "metadata" in item else item))


def _is_foreign_record(metadata: dict[str, Any]) -> bool:
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


def _literature_relevance_score(item: dict[str, Any], topic_terms: list[str]) -> float:
    overlap = _topic_overlap_count(item, topic_terms)
    anchor_groups = _matched_anchor_groups(item, topic_terms)
    year = 0
    try:
        year = int(str(item.get("year") or "0")[:4] or 0)
    except Exception:
        year = 0
    current_year = datetime.now().year
    recency = 0.0
    if year >= current_year - 5:
        recency = 4.0
    elif year >= current_year - 10:
        recency = 2.5
    elif year >= current_year - 15:
        recency = 1.0
    citation_impact = min(math.log1p(float(item.get("cited_by_count") or 0)), 5.0)
    abstract_bonus = 2.5 if str(item.get("abstract") or "").strip() else 0.0
    journal_bonus = 2.0 if str(item.get("source") or "").strip() else 0.0
    source_bonus = _source_quality_score(item)
    management_bonus = 2.0 if _has_management_anchor(item) else 0.0
    mismatch_penalty = 8.0 if _is_domain_mismatch(item, topic_terms) else 0.0
    return overlap * 10.0 + anchor_groups * 12.0 + recency + citation_impact * 0.6 + abstract_bonus + journal_bonus + source_bonus + management_bonus - mismatch_penalty


def _citation_identity(metadata: dict[str, Any]) -> str:
    doi = str(metadata.get("doi") or "").strip().lower()
    if doi:
        return f"doi:{doi}"
    url = str(metadata.get("url") or metadata.get("work_id") or "").strip().lower()
    if url:
        return f"url:{url}"
    title = re.sub(r"\s+", "", str(metadata.get("title") or "").strip().lower())
    year = str(metadata.get("year") or "").strip()
    return f"title:{title}|year:{year}" if title else ""


def _abstract_from_inverted_index(payload: dict[str, list[int]]) -> str:
    if not payload:
        return ""
    pairs: list[tuple[int, str]] = []
    for word, positions in payload.items():
        for position in positions:
            pairs.append((int(position), str(word)))
    pairs.sort(key=lambda item: item[0])
    return " ".join(word for _, word in pairs).strip()


def _clean_crossref_abstract(text: str) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"<[^>]+>", " ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:2000]


def _fallback_topic_terms(
    title: str,
    current: dict[str, Any],
    grounding: dict[str, Any],
    diagnosis: dict[str, Any],
) -> list[str]:
    text_blobs = [
        str(title or ""),
        str(diagnosis.get("core_problem") or ""),
        str(diagnosis.get("recommended_track") or ""),
        str(current.get("role_title") or ""),
        str(current.get("work_scope") or ""),
        str(grounding.get("company_business") or ""),
    ]
    for key in ["candidate_axes", "mentor_research_fields", "mentor_expertise", "company_keywords", "problem_statements"]:
        value = grounding.get(key) if key in grounding else diagnosis.get(key)
        if isinstance(value, list):
            text_blobs.extend(str(item) for item in value)
        elif value:
            text_blobs.append(str(value))
    phrase_bank = [
        "总部门店协同",
        "总部-门店协同",
        "门店经营",
        "经营决策支持",
        "决策支持",
        "战略执行",
        "执行跟进",
        "跨部门协同",
        "组织协同",
        "流程衔接",
        "信息反馈",
        "文件流转",
        "会议决策",
        "会议组织",
        "行政协调",
        "战略规划",
        "营销战略",
        "商业模式",
        "品牌战略",
        "零售",
        "服装",
        "鞋帽",
        "箱包",
        "门店",
        "总部",
        "品牌经营",
        "总经理助理",
    ]
    terms: list[str] = []
    seen: set[str] = set()
    for blob in text_blobs:
        text = str(blob or "")
        for phrase in phrase_bank:
            if phrase in text and phrase not in seen:
                seen.add(phrase)
                terms.append(phrase)
        for token in re.split(r"[，,；;。/、\s]+", text):
            token = token.strip("（）()·- ")
            if len(token) < 2 or len(token) > 12:
                continue
            if token in {"有限公司", "公司", "企业", "研究", "优化", "机制", "问题", "管理", "负责", "当前资料显示"}:
                continue
            if re.search(r"[A-Za-z]", token) and len(token) > 20:
                continue
            if token not in seen:
                seen.add(token)
                terms.append(token)
    title_terms = _title_focus_terms(title)
    return _dedupe_preserve(title_terms + terms)[:10] or ["组织协同", "决策支持", "营销战略", "商业模式", "零售", "门店经营"]


def _fallback_chinese_queries(topic_terms: list[str]) -> list[str]:
    industry = next((item for item in topic_terms if item in {"零售", "服装", "门店经营", "品牌经营", "门店"}), topic_terms[0])
    problem = next((item for item in topic_terms if item in {"总部门店协同", "总部-门店协同", "经营决策支持", "跨部门协同", "组织协同", "信息反馈", "会议决策", "战略执行"}), topic_terms[1] if len(topic_terms) > 1 else topic_terms[0])
    mentor = next((item for item in topic_terms if item in {"营销战略", "商业模式", "品牌战略"}), topic_terms[2] if len(topic_terms) > 2 else problem)
    return [
        f"{industry} {problem} 机制",
        f"{industry} {problem} 优化",
        f"{industry} {mentor} {problem}",
        f"{industry} {problem} 文献",
        f"{mentor} {problem} 研究",
        f"{problem} 管理 研究",
        f"{industry} 组织协同 管理",
    ]


def _fallback_english_queries(topic_terms: list[str]) -> list[str]:
    mapped = [_translate_topic(term) for term in topic_terms]
    mapped = [item for item in mapped if item]
    base = " ".join(mapped[:4]).strip() or "management mechanism optimization"
    industry = next((item for item in mapped if item in {"retail", "apparel", "store operations", "store"}), "retail")
    problem = next((item for item in mapped if item in {"headquarters store coordination", "decision support", "cross-functional coordination", "organization coordination", "information feedback", "strategy execution"}), "coordination")
    mentor = next((item for item in mapped if item in {"marketing strategy", "business model", "brand strategy"}), "management")
    return [
        f"{industry} {problem}",
        f"{industry} {problem} management",
        f"{industry} {problem} mechanism",
        f"{industry} {mentor} {problem}",
        f"{base} journal article",
        f"{industry} operations management",
        f"{problem} organizational study",
    ]


def _translate_topic(term: str) -> str:
    mapping = {
        "总部门店协同": "headquarters store coordination",
        "总部-门店协同": "headquarters store coordination",
        "总部": "headquarters",
        "门店": "store",
        "协同": "coordination",
        "跨部门": "cross-functional",
        "跨部门协同": "cross-functional coordination",
        "组织协同": "organization coordination",
        "决策支持": "decision support",
        "战略执行": "strategy execution",
        "执行跟进": "execution tracking",
        "经营": "operations",
        "反馈": "feedback",
        "营销": "marketing",
        "营销战略": "marketing strategy",
        "商业模式": "business model",
        "品牌战略": "brand strategy",
        "品牌": "brand",
        "零售": "retail",
        "服装": "apparel",
        "组织": "organization",
        "流程": "process",
        "总经理助理": "executive assistant",
        "门店经营": "store operations",
        "经营决策支持": "managerial decision support",
        "信息反馈": "information feedback",
        "战略规划": "strategic planning",
    }
    for key, value in mapping.items():
        if key in term:
            return value
    if re.search(r"[A-Za-z]", term):
        return term.lower()
    return ""


def _join_text(values: Any) -> str:
    if isinstance(values, list):
        cleaned = [str(item).strip() for item in values if str(item).strip()]
        return "、".join(cleaned[:6]) if cleaned else "待补充"
    return str(values or "").strip() or "待补充"


def _is_suspicious_source(item: dict[str, Any]) -> bool:
    source = str(item.get("source") or "").lower()
    source_type = str(item.get("source_type") or "").lower().strip()
    host = str(item.get("source_host") or "").lower()
    if source_type and source_type != "journal":
        return True
    haystack = " ".join([source, host])
    return any(marker in haystack for marker in [marker.lower() for marker in SUSPICIOUS_SOURCE_MARKERS])


def _passes_record_quality(item: dict[str, Any], topic_terms: list[str]) -> bool:
    title = str(item.get("title") or "").strip()
    source = str(item.get("source") or "").strip()
    year = str(item.get("year") or "").strip()
    if not title or not source or not year:
        return False
    if _is_suspicious_source(item):
        return False
    if len(title) < 6:
        return False
    haystack = " ".join(
        str(item.get(key) or "")
        for key in ["title", "source", "abstract"]
    ).lower()
    overlap = _topic_overlap_count(item, topic_terms)
    if overlap < 1:
        return False
    groups = _topic_anchor_groups(topic_terms)
    anchor_groups = _matched_anchor_groups(item, topic_terms)
    source_score = _source_quality_score(item)
    industry_terms = groups.get("industry") or []
    advisor_terms = groups.get("advisor") or []
    problem_terms = groups.get("problem") or []
    industry_match = any(term in haystack for term in industry_terms)
    advisor_match = any(term in haystack for term in advisor_terms)
    problem_match = any(term in haystack for term in problem_terms)
    if _is_foreign_record(item):
        if source_score < 4.5:
            return False
        if industry_terms and not industry_match:
            return False
        if anchor_groups < 2 and not (source_score >= 10 and overlap >= 2):
            return False
    else:
        if not _is_preferred_domestic_source(item):
            return False
        if anchor_groups < 1:
            return False
        if overlap < 2 and source_score < 8:
            return False
    if _is_domain_mismatch(item, topic_terms):
        return False
    if source_score <= 0:
        return False
    return True


def _is_preferred_domestic_source(item: dict[str, Any]) -> bool:
    source = str(item.get("source") or "").strip()
    return any(marker in source for marker in TRUSTED_CHINESE_SOURCES)


def _source_quality_score(item: dict[str, Any]) -> float:
    source = str(item.get("source") or "").strip()
    lowered = source.lower()
    title = str(item.get("title") or "").strip().lower()
    source_type = str(item.get("source_type") or "").lower().strip()
    score = 0.0
    if source_type == "journal":
        score += 3.0
    if item.get("source_is_core"):
        score += 4.0
    if any(marker.lower() in lowered for marker in TRUSTED_ENGLISH_SOURCES):
        score += 6.0
    if any(marker in source for marker in TRUSTED_CHINESE_SOURCES):
        score += 6.0
    if "journal" in lowered or "review" in lowered:
        score += 1.5
    if re.search(r"(store|retail|marketing|brand|strategy|operation|coordination|decision)", title):
        score += 1.5
    if re.search(r"(零售|门店|营销|品牌|战略|协同|决策|运营)", title):
        score += 1.5
    if any(marker in lowered for marker in [marker.lower() for marker in SUSPICIOUS_SOURCE_MARKERS]):
        score -= 10.0
    return score


def _topic_overlap_count(item: dict[str, Any], topic_terms: list[str]) -> int:
    haystack = " ".join(
        str(item.get(key) or "")
        for key in ["title", "source", "abstract"]
    ).lower()
    overlap = 0
    for term in topic_terms:
        normalized = str(term or "").strip().lower()
        if normalized and normalized in haystack:
            overlap += 1
    return overlap


def _expand_topic_terms(topic_terms: list[str]) -> list[str]:
    expanded = list(topic_terms)
    for term in list(topic_terms):
        translated = _translate_topic(term)
        if translated:
            expanded.extend(part for part in re.split(r"\s+", translated) if part)
            expanded.append(translated)
    return _dedupe_preserve([item for item in expanded if item])


def _matched_anchor_groups(item: dict[str, Any], topic_terms: list[str]) -> int:
    haystack = " ".join(
        str(item.get(key) or "")
        for key in ["title", "source", "abstract"]
    ).lower()
    groups = _topic_anchor_groups(topic_terms)
    matched = 0
    for terms in groups.values():
        if any(term in haystack for term in terms):
            matched += 1
    return matched


def _topic_anchor_groups(topic_terms: list[str]) -> dict[str, list[str]]:
    problem_terms: list[str] = []
    industry_terms: list[str] = []
    advisor_terms: list[str] = []
    for term in topic_terms:
        text = str(term or "").lower().strip()
        if not text:
            continue
        if any(marker in text for marker in ["决策", "support", "协同", "coordination", "流程", "process", "执行", "execution", "机制", "mechanism"]):
            problem_terms.append(text)
        if any(marker in text for marker in ["零售", "retail", "门店", "store", "服装", "apparel", "品牌", "brand", "鞋服"]):
            industry_terms.append(text)
        if any(marker in text for marker in ["营销", "marketing", "商业模式", "business model", "品牌战略", "brand strategy", "strategy"]):
            advisor_terms.append(text)
    return {
        "problem": _dedupe_preserve(problem_terms),
        "industry": _dedupe_preserve(industry_terms),
        "advisor": _dedupe_preserve(advisor_terms),
    }


def _has_management_anchor(item: dict[str, Any]) -> bool:
    haystack = " ".join(
        str(item.get(key) or "")
        for key in ["title", "source", "abstract"]
    ).lower()
    anchors = [
        "management",
        "strategy",
        "marketing",
        "retail",
        "brand",
        "organization",
        "coordination",
        "operations",
        "decision",
        "管理",
        "战略",
        "营销",
        "零售",
        "品牌",
        "组织",
        "协同",
        "运营",
        "决策",
    ]
    return any(anchor in haystack for anchor in anchors)


def _is_domain_mismatch(item: dict[str, Any], topic_terms: list[str]) -> bool:
    haystack = " ".join(
        str(item.get(key) or "")
        for key in ["title", "source", "abstract"]
    ).lower()
    industry_anchors = ["retail", "store", "apparel", "fashion", "brand", "marketing", "零售", "门店", "服装", "品牌", "营销"]
    if any(anchor in haystack for anchor in industry_anchors):
        return False
    mismatch_markers = [
        "healthcare",
        "medical",
        "hospital",
        "epidemic",
        "greenhouse",
        "agriculture",
        "bridge",
        "tunnel",
        "dam",
        "construction",
        "chemical",
        "power system",
        "water resource",
        "education",
        "railway",
        "metro",
        "医院",
        "医疗",
        "疫情",
        "农田",
        "农业",
        "桥梁",
        "隧道",
        "大坝",
        "施工",
        "化工",
        "水利",
        "电力",
        "教育",
        "轨道交通",
        "水电",
    ]
    if any(marker in haystack for marker in mismatch_markers):
        groups = _topic_anchor_groups(topic_terms)
        industry_terms = groups.get("industry") or []
        advisor_terms = groups.get("advisor") or []
        problem_terms = groups.get("problem") or []
        industry_match = any(term in haystack for term in industry_terms)
        advisor_match = any(term in haystack for term in advisor_terms)
        problem_match_count = sum(1 for term in problem_terms if term in haystack)
        if industry_terms and not industry_match:
            return True
        if advisor_terms and not advisor_match and problem_match_count < 2:
            return True
        needed = [term for term in topic_terms if term.lower() in haystack]
        return len(needed) < 4
    return False


def _title_focus_terms(title: str) -> list[str]:
    cleaned = str(title or "").strip()
    cleaned = re.sub(r"^[A-ZＡ-Ｚ][公司企业单位集团组织]+", "", cleaned)
    cleaned = re.sub(r"^[A-ZＡ-Ｚ]公司", "", cleaned)
    cleaned = re.sub(r"(机制优化研究|优化研究|机制研究|改进研究|路径研究|体系构建研究|研究)$", "", cleaned)
    cleaned = cleaned.strip("：:（）()《》“”\"' ")
    if not cleaned:
        return []
    parts = re.split(r"[—\-－、，,/\s]+", cleaned)
    terms: list[str] = []
    for part in parts:
        token = part.strip()
        if len(token) < 2 or len(token) > 12:
            continue
        terms.append(token)
    if cleaned and cleaned not in terms and len(cleaned) <= 16:
        terms.insert(0, cleaned)
    return _dedupe_preserve(terms)[:4]


def _clean_query_list(values: Any) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in values if isinstance(values, list) else []:
        query = re.sub(r"\s+", " ", str(raw or "").strip())
        if not query:
            continue
        words = [word for word in re.split(r"\s+", query) if word]
        deduped: list[str] = []
        for word in words:
            if not deduped or deduped[-1] != word:
                deduped.append(word)
        query = " ".join(deduped).strip()
        if query and query not in seen:
            seen.add(query)
            cleaned.append(query)
    return cleaned


def _clean_topic_terms(values: Any) -> list[str]:
    return _dedupe_preserve(
        [
            str(item).strip()
            for item in values if isinstance(values, list)
            for item in [item]
            if str(item).strip() and 1 < len(str(item).strip()) <= 16
        ]
    )


def _dedupe_preserve(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        output.append(text)
    return output


def _is_generic_title_term(term: str) -> bool:
    text = str(term or "").strip()
    return text in {
        "决策支持",
        "经营决策支持",
        "管理决策",
        "组织协同",
        "跨部门协同",
        "流程衔接",
        "战略执行",
        "执行跟进",
        "品牌经营",
        "门店经营",
    }


def _seed_search_plan(
    title: str,
    current: dict[str, Any],
    grounding: dict[str, Any],
    diagnosis: dict[str, Any],
) -> dict[str, list[str]]:
    title_terms = _title_focus_terms(title)
    retail_markers = ["零售", "门店", "服装", "鞋帽", "箱包", "品牌", "retail", "store", "apparel", "brand"]
    all_text = " ".join(
        [
            title,
            str(current.get("role_title") or ""),
            str(current.get("work_scope") or ""),
            str(grounding.get("company_business") or ""),
            " ".join(str(item) for item in grounding.get("company_keywords") or []),
            " ".join(str(item) for item in grounding.get("mentor_research_fields") or []),
            " ".join(str(item) for item in grounding.get("mentor_expertise") or []),
            str(diagnosis.get("recommended_track") or ""),
        ]
    )
    has_retail_context = any(marker in all_text for marker in retail_markers)
    chinese_queries: list[str] = []
    english_queries: list[str] = []
    topic_terms: list[str] = []

    if any(marker in all_text for marker in ["决策支持", "经营决策", "决策"]):
        topic_terms.extend(["经营决策支持", "管理决策", "决策支持系统", "管理信息报送"])
        if has_retail_context:
            chinese_queries.extend(
                [
                    "零售企业 经营决策支持",
                    "品牌零售 经营分析 决策支持",
                    "门店经营 决策支持 管理",
                    "连锁零售 管理决策支持",
                ]
            )
            english_queries.extend(
                [
                    "managerial decision support retail operations",
                    "business intelligence retail management",
                    "executive decision support retail",
                    "marketing analytics retail decision making",
                ]
            )
        else:
            chinese_queries.extend(
                [
                    "经营决策支持 管理",
                    "管理决策支持 系统 企业",
                    "管理会计 决策支持 企业",
                    "经营分析 决策支持 机制",
                ]
            )
            english_queries.extend(
                [
                    "managerial decision support management",
                    "business intelligence management",
                    "management accounting decision support",
                    "decision support systems management",
                ]
            )

    if any(marker in all_text for marker in ["总部", "门店", "零售", "服装", "鞋帽", "箱包", "品牌"]):
        topic_terms.extend(["零售", "门店经营", "总部-门店协同", "品牌经营"])
        chinese_queries.extend(
            [
                "零售企业 门店运营 管理",
                "连锁零售 总部门店 协同",
                "品牌零售 运营 管理",
                "服装零售 门店经营 管理",
            ]
        )
        english_queries.extend(
            [
                "retail store operations",
                "headquarters store coordination retail",
                "chain retail management",
                "apparel retail management",
            ]
        )

    if any(marker in all_text for marker in ["协同", "职责界面", "流程", "跨部门"]):
        topic_terms.extend(["跨部门协同", "组织协同", "流程衔接"])
        chinese_queries.extend(
            [
                "跨部门协同 管理",
                "组织协同 机制",
                "流程衔接 管理",
                "部门协同 机制 企业",
            ]
        )
        english_queries.extend(
            [
                "cross-functional integration management",
                "interdepartmental coordination organization",
                "process integration organization",
                "organizational coordination management",
            ]
        )

    if any(marker in all_text for marker in ["战略", "执行", "落地", "跟进"]):
        topic_terms.extend(["战略执行", "执行跟进", "管理控制"])
        chinese_queries.extend(
            [
                "战略执行 管理",
                "战略实施 管理控制",
                "战略落地 机制",
                "执行跟踪 管理 企业",
            ]
        )
        english_queries.extend(
            [
                "strategy execution management",
                "strategy implementation management control",
                "execution tracking management",
                "management control strategy implementation",
            ]
        )

    if any(marker in all_text for marker in ["营销战略", "商业模式", "品牌战略", "品牌"]):
        topic_terms.extend(["营销战略", "商业模式", "品牌战略"])
        chinese_queries.extend(
            [
                "营销战略 零售企业",
                "品牌战略 零售 管理",
                "商业模式 零售企业",
            ]
        )
        english_queries.extend(
            [
                "marketing strategy retail",
                "brand strategy management",
                "business model retail management",
            ]
        )

    if title_terms:
        topic_terms = _dedupe_preserve(title_terms + topic_terms)
        chinese_queries = _dedupe_preserve(
            [f"{term} 管理" for term in title_terms if not _is_generic_title_term(term)] + chinese_queries
        )
        english_queries = _dedupe_preserve(
            [
                f"{translated} management"
                for term in title_terms
                if not _is_generic_title_term(term)
                if (translated := _translate_topic(term))
            ]
            + english_queries
        )

    return {
        "chinese_queries": chinese_queries[:8],
        "english_queries": english_queries[:8],
        "topic_terms": topic_terms[:10],
    }


def _prioritize_records_with_model(
    *,
    title: str,
    current: dict[str, Any],
    profile: dict[str, Any],
    grounding: dict[str, Any],
    diagnosis: dict[str, Any],
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not records or not is_enabled():
        return records
    candidate_records = records[:60]
    summary = _literature_context_summary(title, current, profile, grounding, diagnosis)
    candidate_lines = []
    for index, item in enumerate(candidate_records, start=1):
        abstract = str(item.get("abstract") or "").strip()
        abstract = re.sub(r"\s+", " ", abstract)[:260]
        candidate_lines.append(
            {
                "id": index,
                "title": item.get("title"),
                "year": item.get("year"),
                "source": item.get("source"),
                "language": item.get("language"),
                "provider": item.get("provider"),
                "query": item.get("query"),
                "relevance_score": round(float(item.get("relevance_score") or 0.0), 2),
                "abstract": abstract,
            }
        )
    try:
        payload = complete_json(
            "你是经管类专业硕士开题文献筛选专家。你只能从给定的真实候选记录中挑选，不能虚构任何文献。",
            f"""
请从下面这批真实候选记录中，按“最适合当前开题报告”的标准做优先级排序。

筛选要求：
1. 必须优先保留管理学、营销、零售运营、组织协同、决策支持、战略执行相关文献
2. 排除医学、农业、土木、水利、化工、教育等错领域文献
3. 优先保留更贴近当前题目、导师方向、公司主营业务、岗位场景的文献
4. 优先保留更像学术期刊而非杂志、案例短文、行业资讯的来源
5. 输出最多 40 条记录 id，按优先级从高到低排列
6. 只输出 JSON

当前研究概要：
{summary}

真实候选记录：
{candidate_lines}

返回格式：
{{
  "selected_ids": [1, 2, 3],
  "notes": "一句话概括筛选原则"
}}
""",
            temperature=0.1,
        )
        selected_ids = payload.get("selected_ids") if isinstance(payload, dict) else None
        if not isinstance(selected_ids, list):
            return records
        id_set = []
        seen: set[int] = set()
        for raw in selected_ids:
            try:
                value = int(raw)
            except Exception:
                continue
            if 1 <= value <= len(candidate_records) and value not in seen:
                seen.add(value)
                id_set.append(value)
        if not id_set:
            return records
        prioritized: list[dict[str, Any]] = []
        used_keys: set[str] = set()
        for value in id_set:
            item = candidate_records[value - 1]
            key = _citation_identity(item)
            if key and key not in used_keys:
                used_keys.add(key)
                prioritized.append(item)
        for item in records:
            key = _citation_identity(item)
            if key and key not in used_keys:
                used_keys.add(key)
                prioritized.append(item)
        return prioritized
    except LLMError:
        return records
