from __future__ import annotations

from typing import Any

from ..core.parsing import domain_from_url, evidence_summary_from_text, extract_metadata
from ..core.search import fetch_page, rank_search_results, school_domain_hints, search_duckduckgo
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

    search_plan = [
        {
            "kind": "school",
            "query": f"{school_name} EMBA 开题 报告 写作 指南",
            "official_domains": school_domain_hints(school_name),
            "keywords": [school_name, "开题", "EMBA", "写作"],
        }
    ]
    if mentor_name:
        search_plan.append(
            {
                "kind": "mentor",
                "query": f"{mentor_name} {school_name} 导师 研究",
                "official_domains": school_domain_hints(school_name),
                "keywords": [mentor_name, "教授", "研究方向", school_name],
            }
        )
    if company_name:
        official_domains = [company_domain] if company_domain else []
        search_plan.append(
            {
                "kind": "company",
                "query": f"{company_name} 官网 关于我们",
                "official_domains": official_domains,
                "keywords": [company_name, "官网", "关于我们", "产品"],
            }
        )

    for item in search_plan:
        try:
            results = search_duckduckgo(item["query"], max_results=4)
        except Exception:  # pragma: no cover - network instability
            continue
        for result in rank_search_results(results, item["official_domains"], item["keywords"])[:2]:
            if result["url"] in existing_urls:
                continue
            page = fetch_page(result["url"])
            grade = _infer_grade(item["kind"], result["url"], item["official_domains"])
            status = "verified" if page.get("status") == "verified" else "pending_confirmation"
            evidence = add_evidence_item(
                workspace_id=workspace_id,
                evidence_type="public_web",
                title=page.get("title") or result["title"],
                summary=evidence_summary_from_text(page.get("text", "") or result.get("snippet", "")),
                grade=grade,
                status=status,
                source_label=item["kind"],
                source_uri=result["url"],
                source_date=page.get("published_date", ""),
                metadata={
                    "kind": item["kind"],
                    "query": item["query"],
                    "domain": domain_from_url(result["url"]),
                    "search_title": result["title"],
                    "search_snippet": result["snippet"],
                },
                content={"text": page.get("text", "")},
            )
            existing_urls.add(result["url"])
            created_sources.append(evidence)
            created_fields.extend(
                _extract_field_proposals(
                    workspace_id=workspace_id,
                    source_kind=item["kind"],
                    source_label=evidence["title"],
                    source_uri=result["url"],
                    grade=grade,
                    text=page.get("text", ""),
                )
            )
    return {"sources": created_sources, "fields": created_fields}


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
