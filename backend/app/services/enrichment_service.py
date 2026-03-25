from __future__ import annotations

import re
from typing import Any

from ..core.evidence_grounding import build_grounding_context
from ..core.parsing import domain_from_url, evidence_summary_from_text, extract_metadata
from ..core.search import fetch_page, rank_search_results, school_domain_hints, search_web
from .workspace_service import (
    add_evidence_item,
    add_field_value,
    current_field_map,
    list_evidence_items,
)


def enrich_public_sources(workspace_id: str) -> dict[str, Any]:
    current = current_field_map(workspace_id)
    school_name = str(current.get("school_name") or "武汉大学")
    mentor_name = str(current.get("mentor_name") or "")
    company_name = str(current.get("company_name") or "")
    company_domain = str(current.get("company_domain") or "")

    created_sources: list[dict[str, Any]] = []
    created_fields: list[dict[str, Any]] = []
    existing_urls = {
        item.get("source_uri")
        for item in list_evidence_items(workspace_id)
        if item.get("source_uri")
    }
    existing_evidence = list_evidence_items(workspace_id)
    created_fields.extend(_backfill_existing_grounding_fields(workspace_id, current, existing_evidence))

    search_plan = [
        {
            "kind": "school",
            "queries": [
                f"{school_name} EMBA 开题 报告 写作 指南",
                f"{school_name} 专业硕士 开题 写作 指南",
            ],
            "official_domains": school_domain_hints(school_name),
            "keywords": [school_name, "开题", "EMBA", "写作", "专业硕士"],
            "entity_keywords": [school_name],
        }
    ]
    if mentor_name:
        search_plan.append(
            {
                "kind": "mentor",
                "queries": [
                    f"{mentor_name} {school_name} 导师 研究方向",
                    f"{mentor_name} {school_name} 经济与管理学院",
                    f"{mentor_name} {school_name} 教授 研究领域",
                ],
                "official_domains": school_domain_hints(school_name),
                "keywords": [mentor_name, "教授", "研究方向", school_name],
                "entity_keywords": [mentor_name, school_name],
            }
        )
    if company_name:
        official_domains = [company_domain] if company_domain else []
        company_aliases = _company_query_aliases(company_name)
        company_queries: list[str] = []
        for alias in company_aliases:
            company_queries.extend(
                [
                    f"{alias} 官网 关于我们",
                    f"{alias} 公司简介 主营业务",
                    f"{alias} 产品 服务 介绍",
                ]
            )
        search_plan.append(
            {
                "kind": "company",
                "queries": company_queries,
                "official_domains": official_domains,
                "keywords": company_aliases + ["官网", "关于我们", "主营业务", "产品", "服务"],
                "entity_keywords": company_aliases,
            }
        )

    for item in search_plan:
        aggregated_results: list[dict[str, Any]] = []
        for query in item["queries"]:
            try:
                aggregated_results.extend(search_web(query, max_results=4))
            except Exception:  # pragma: no cover - network instability
                continue
        deduped_results = _dedupe_results(aggregated_results)
        ranked_results = rank_search_results(deduped_results, item["official_domains"], item["keywords"])
        for result in ranked_results[:6]:
            if result["url"] in existing_urls:
                continue
            page = fetch_page(result["url"])
            page_text = str(page.get("text", "") or "").strip()
            combined_text = _merge_search_content(result.get("snippet", ""), page_text)
            if not combined_text:
                continue
            if not _is_relevant_result(
                source_kind=item["kind"],
                result=result,
                combined_text=combined_text,
                official_domains=item["official_domains"],
                entity_keywords=item.get("entity_keywords") or [],
            ):
                continue
            grade = _infer_grade(item["kind"], result["url"], item["official_domains"])
            status = "verified" if page.get("status") == "verified" else "pending_confirmation"
            evidence = add_evidence_item(
                workspace_id=workspace_id,
                evidence_type="public_web",
                title=page.get("title") or result["title"],
                summary=evidence_summary_from_text(combined_text),
                grade=grade,
                status=status,
                source_label=item["kind"],
                source_uri=result["url"],
                source_date=page.get("published_date", ""),
                metadata={
                    "kind": item["kind"],
                    "queries": item["queries"],
                    "domain": domain_from_url(result["url"]),
                    "search_title": result["title"],
                    "search_snippet": result["snippet"],
                },
                content={"text": combined_text},
            )
            existing_urls.add(result["url"])
            created_sources.append(evidence)
            created_fields.extend(
                _extract_grounding_field_proposals(
                    workspace_id=workspace_id,
                    source_kind=item["kind"],
                    source_label=evidence["title"],
                    source_uri=result["url"],
                    grade=grade,
                    current=current,
                    evidence=evidence,
                )
            )
            created_fields.extend(
                _extract_field_proposals(
                    workspace_id=workspace_id,
                    source_kind=item["kind"],
                    source_label=evidence["title"],
                    source_uri=result["url"],
                    grade=grade,
                    text=combined_text,
                )
            )
    return {"sources": created_sources, "fields": created_fields}


def _dedupe_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for item in results:
        url = str(item.get("url") or "").strip()
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        deduped.append(item)
    return deduped


def _merge_search_content(snippet: str, page_text: str) -> str:
    snippet_text = str(snippet or "").strip()
    page_value = str(page_text or "").strip()
    if snippet_text and page_value:
        return f"{snippet_text}\n{page_value}"
    return snippet_text or page_value


def _company_query_aliases(company_name: str) -> list[str]:
    value = str(company_name or "").strip()
    if not value:
        return []
    aliases = [value]
    stripped = re.sub(r"(股份有限公司|有限责任公司|有限公司|集团有限公司|集团|控股集团|控股)$", "", value).strip()
    if stripped and stripped not in aliases:
        aliases.append(stripped)
    location_prefixes = [
        "北京",
        "上海",
        "深圳",
        "广州",
        "武汉",
        "杭州",
        "南京",
        "苏州",
        "成都",
        "重庆",
        "天津",
        "西安",
        "长沙",
        "宁波",
        "青岛",
        "厦门",
        "郑州",
        "济南",
        "合肥",
        "福州",
        "南昌",
        "东莞",
        "佛山",
        "无锡",
        "常州",
        "昆山",
        "沈阳",
        "大连",
        "哈尔滨",
        "长春",
        "太原",
        "石家庄",
        "南宁",
        "海口",
        "贵阳",
        "昆明",
        "兰州",
        "呼和浩特",
    ]
    for prefix in location_prefixes:
        if stripped.startswith(prefix) and len(stripped) > len(prefix) + 2:
            alias = stripped[len(prefix) :].strip()
            if alias and alias not in aliases:
                aliases.append(alias)
            break
    if stripped:
        compact = re.sub(r"(科技|信息技术|信息|软件|服饰|服装|建筑设计|建筑|咨询|管理|商贸|电子商务|电子)$", "", stripped).strip()
        if compact and len(compact) >= 2 and compact not in aliases:
            aliases.append(compact)
    return aliases[:3]


def _is_relevant_result(
    source_kind: str,
    result: dict[str, Any],
    combined_text: str,
    official_domains: list[str],
    entity_keywords: list[str],
) -> bool:
    domain = domain_from_url(str(result.get("url") or ""))
    blob = " ".join(
        [
            str(result.get("title") or ""),
            str(result.get("snippet") or ""),
            str(combined_text or ""),
            domain,
        ]
    )
    if source_kind == "mentor":
        mentor_name = str(entity_keywords[0] or "") if entity_keywords else ""
        school_name = str(entity_keywords[1] or "") if len(entity_keywords) > 1 else ""
        if mentor_name and mentor_name not in blob:
            return False
        if any(domain.endswith(expected) for expected in official_domains if expected):
            return True
        return not school_name or school_name in blob
    if source_kind == "company":
        if not any(keyword and keyword in blob for keyword in entity_keywords):
            return False
        if any(noise in blob for noise in ["分公司", "门店", "股东信息", "股东名单", "sholder", "咸宁店", "富阳区"]):
            return False
        if any(domain.endswith(expected) for expected in official_domains if expected):
            return True
        if any(noise_domain in domain for noise_domain in ["qcc.com", "tianyancha.com", "7icp.com", "guishudi.com"]):
            return "经营范围" in blob or "主营业务" in blob
        return True
    return True


def _infer_grade(kind: str, url: str, official_domains: list[str]) -> str:
    domain = domain_from_url(url)
    if any(domain.endswith(expected) for expected in official_domains if expected):
        return "A"
    if kind == "school" and domain.endswith(".edu.cn"):
        return "A"
    if kind == "company" and ("about" in url or "news" in url or "company" in url):
        return "B"
    return "B"


def _extract_field_proposals(
    workspace_id: str,
    source_kind: str,
    source_label: str,
    source_uri: str,
    grade: str,
    text: str,
) -> list[dict[str, Any]]:
    metadata = extract_metadata(text)
    created: list[dict[str, Any]] = []
    for key in ["mentor_title", "research_direction", "program_name", "school_name"]:
        value = metadata.get(key)
        if not value:
            continue
        created.append(
            add_field_value(
                workspace_id=workspace_id,
                field_key=key,
                value=value,
                source_label=source_label,
                source_kind="official_web",
                source_uri=source_uri,
                source_grade=grade,
                confidence=0.78,
                confirmed=False,
            )
        )
    if source_kind == "company":
        created.append(
            add_field_value(
                workspace_id=workspace_id,
                field_key="company_domain",
                value=domain_from_url(source_uri),
                source_label=source_label,
                source_kind="official_web",
                source_uri=source_uri,
                source_grade=grade,
                confidence=0.7,
                confirmed=False,
            )
        )
        created.append(
            add_field_value(
                workspace_id=workspace_id,
                field_key="company_profile_url",
                value=source_uri,
                source_label=source_label,
                source_kind="official_web",
                source_uri=source_uri,
                source_grade=grade,
                confidence=0.7,
                confirmed=False,
            )
        )
    if source_kind == "school":
        created.append(
            add_field_value(
                workspace_id=workspace_id,
                field_key="school_requirement_url",
                value=source_uri,
                source_label=source_label,
                source_kind="official_web",
                source_uri=source_uri,
                source_grade=grade,
                confidence=0.82,
                confirmed=False,
            )
        )
    if source_kind == "mentor":
        created.append(
            add_field_value(
                workspace_id=workspace_id,
                field_key="mentor_source_url",
                value=source_uri,
                source_label=source_label,
                source_kind="official_web",
                source_uri=source_uri,
                source_grade=grade,
                confidence=0.82,
                confirmed=False,
            )
        )
    return created


def _extract_grounding_field_proposals(
    workspace_id: str,
    source_kind: str,
    source_label: str,
    source_uri: str,
    grade: str,
    current: dict[str, Any],
    evidence: dict[str, Any],
) -> list[dict[str, Any]]:
    if source_kind not in {"mentor", "company"}:
        return []
    grounding = build_grounding_context(current, [evidence], allow_llm=True)
    proposals: list[tuple[str, str]] = []
    if source_kind == "mentor":
        mentor_fields = "、".join(str(item).strip() for item in grounding.get("mentor_research_fields") or [] if str(item).strip())
        mentor_expertise = "、".join(str(item).strip() for item in grounding.get("mentor_expertise") or [] if str(item).strip())
        if mentor_fields:
            proposals.append(("mentor_research_fields", mentor_fields))
        if mentor_expertise:
            proposals.append(("mentor_expertise", mentor_expertise))
    if source_kind == "company":
        company_business = str(grounding.get("company_business") or "").strip()
        company_keywords = "、".join(str(item).strip() for item in grounding.get("company_keywords") or [] if str(item).strip())
        if company_business:
            proposals.append(("company_business", company_business))
        if company_keywords:
            proposals.append(("company_keywords", company_keywords))
    created: list[dict[str, Any]] = []
    for field_key, value in proposals:
        created.append(
            add_field_value(
                workspace_id=workspace_id,
                field_key=field_key,
                value=value,
                source_label=source_label,
                source_kind="official_web",
                source_uri=source_uri,
                source_grade=grade,
                confidence=0.76,
                confirmed=False,
            )
        )
    return created


def _backfill_existing_grounding_fields(
    workspace_id: str,
    current: dict[str, Any],
    evidence_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    created: list[dict[str, Any]] = []
    for evidence in evidence_items:
        metadata = evidence.get("metadata") or {}
        source_kind = str(metadata.get("kind") or "").strip()
        if source_kind not in {"mentor", "company"}:
            continue
        created.extend(
            _extract_grounding_field_proposals(
                workspace_id=workspace_id,
                source_kind=source_kind,
                source_label=str(evidence.get("title") or evidence.get("source_label") or source_kind),
                source_uri=str(evidence.get("source_uri") or ""),
                grade=str(evidence.get("grade") or "B"),
                current=current,
                evidence=evidence,
            )
        )
    return created
