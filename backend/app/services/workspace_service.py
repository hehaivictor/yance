from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from ..config import settings
from ..core.parsing import (
    classify_local_file,
    evidence_summary_from_text,
    extract_metadata,
    extract_urls,
    grade_for_local_category,
    read_text,
    slug_from_title,
    today_string,
)
from ..db import get_connection, row_to_dict


def now_string() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def load_profile(profile_id: str) -> dict[str, Any]:
    path = settings.profile_dir / f"{profile_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"Unknown profile: {profile_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def list_profiles() -> list[dict[str, Any]]:
    profiles = []
    for path in sorted(settings.profile_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        profiles.append({"id": payload["id"], "name": payload["name"]})
    return profiles


def ensure_workspace_dirs(workspace_id: str, name: str) -> Path:
    slug = slug_from_title(name)
    workspace_dir = settings.workspace_root / f"{slug}-{workspace_id[:8]}"
    (workspace_dir / "sources").mkdir(parents=True, exist_ok=True)
    (workspace_dir / "generated").mkdir(parents=True, exist_ok=True)
    (workspace_dir / "snapshots").mkdir(parents=True, exist_ok=True)
    return workspace_dir


def create_workspace(name: str, school_profile: str) -> dict[str, Any]:
    profile = load_profile(school_profile)
    workspace_id = str(uuid.uuid4())
    workspace_dir = ensure_workspace_dirs(workspace_id, name)
    timestamp = now_string()
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO workspaces (id, name, school_profile, status, workspace_dir, selected_title_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                workspace_id,
                name,
                school_profile,
                "draft",
                str(workspace_dir),
                None,
                timestamp,
                timestamp,
            ),
        )
    for key, value in profile.get("defaults", {}).items():
        add_field_value(
            workspace_id=workspace_id,
            field_key=key,
            value=value,
            source_label=f"{profile['name']} 默认规则",
            source_kind="profile",
            source_uri="profile",
            source_grade="B",
            confidence=0.95,
            confirmed=True,
        )
    return get_workspace_bundle(workspace_id)


def list_workspaces() -> list[dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, name, school_profile, status, workspace_dir, selected_title_id, created_at, updated_at
            FROM workspaces
            ORDER BY updated_at DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def delete_workspace(workspace_id: str) -> dict[str, Any]:
    workspace = get_workspace_row(workspace_id)
    workspace_dir = Path(workspace["workspace_dir"]).resolve()
    workspace_root = settings.workspace_root.resolve()
    with get_connection() as connection:
        connection.execute("DELETE FROM field_values WHERE workspace_id = ?", (workspace_id,))
        connection.execute("DELETE FROM evidence_items WHERE workspace_id = ?", (workspace_id,))
        connection.execute("DELETE FROM interview_sessions WHERE workspace_id = ?", (workspace_id,))
        connection.execute("DELETE FROM title_candidates WHERE workspace_id = ?", (workspace_id,))
        connection.execute("DELETE FROM deliverable_bundles WHERE workspace_id = ?", (workspace_id,))
        connection.execute("DELETE FROM workspaces WHERE id = ?", (workspace_id,))
    if workspace_dir != workspace_root and workspace_root in workspace_dir.parents:
        shutil.rmtree(workspace_dir, ignore_errors=True)
    return {
        "deleted": True,
        "workspace_id": workspace_id,
        "name": workspace["name"],
    }


def get_workspace_row(workspace_id: str) -> dict[str, Any]:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT id, name, school_profile, status, workspace_dir, selected_title_id, created_at, updated_at
            FROM workspaces
            WHERE id = ?
            """,
            (workspace_id,),
        ).fetchone()
    if row is None:
        raise KeyError(f"Workspace not found: {workspace_id}")
    return dict(row)


def touch_workspace(workspace_id: str) -> None:
    with get_connection() as connection:
        connection.execute(
            "UPDATE workspaces SET updated_at = ? WHERE id = ?",
            (now_string(), workspace_id),
        )


def add_field_value(
    workspace_id: str,
    field_key: str,
    value: Any,
    source_label: str,
    source_kind: str,
    source_uri: str | None = None,
    source_grade: str = "C",
    confidence: float = 0.8,
    confirmed: bool = False,
    notes: str = "",
) -> dict[str, Any]:
    field_id = str(uuid.uuid4())
    captured_at = now_string()
    payload = (
        field_id,
        workspace_id,
        field_key,
        str(value),
        source_label,
        source_kind,
        source_uri,
        source_grade,
        captured_at,
        confidence,
        1 if confirmed else 0,
        notes,
    )
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO field_values
            (id, workspace_id, field_key, value, source_label, source_kind, source_uri, source_grade, captured_at, confidence, confirmed, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            payload,
        )
    touch_workspace(workspace_id)
    return {
        "id": field_id,
        "workspace_id": workspace_id,
        "field_key": field_key,
        "value": str(value),
        "source_label": source_label,
        "source_kind": source_kind,
        "source_uri": source_uri,
        "source_grade": source_grade,
        "captured_at": captured_at,
        "confidence": confidence,
        "confirmed": confirmed,
        "notes": notes,
    }


def list_field_values(workspace_id: str) -> list[dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM field_values
            WHERE workspace_id = ?
            ORDER BY field_key ASC, captured_at DESC
            """,
            (workspace_id,),
        ).fetchall()
    items = []
    for row in rows:
        item = dict(row)
        item["confirmed"] = bool(item["confirmed"])
        items.append(item)
    return items


def add_evidence_item(
    workspace_id: str,
    evidence_type: str,
    title: str,
    summary: str,
    grade: str,
    status: str,
    source_label: str,
    metadata: dict[str, Any],
    content: dict[str, Any],
    source_uri: str | None = None,
    source_date: str | None = None,
) -> dict[str, Any]:
    evidence_id = str(uuid.uuid4())
    captured_at = now_string()
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO evidence_items
            (id, workspace_id, evidence_type, title, summary, grade, status, source_uri, source_label, source_date, captured_at, metadata_json, content_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                evidence_id,
                workspace_id,
                evidence_type,
                title,
                summary,
                grade,
                status,
                source_uri,
                source_label,
                source_date,
                captured_at,
                json.dumps(metadata, ensure_ascii=False),
                json.dumps(content, ensure_ascii=False),
            ),
        )
    touch_workspace(workspace_id)
    return {
        "id": evidence_id,
        "workspace_id": workspace_id,
        "evidence_type": evidence_type,
        "title": title,
        "summary": summary,
        "grade": grade,
        "status": status,
        "source_uri": source_uri,
        "source_label": source_label,
        "source_date": source_date,
        "captured_at": captured_at,
        "metadata": metadata,
        "content": content,
    }


def list_evidence_items(workspace_id: str) -> list[dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM evidence_items
            WHERE workspace_id = ?
            ORDER BY captured_at DESC
            """,
            (workspace_id,),
        ).fetchall()
    items = []
    for row in rows:
        item = dict(row)
        item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
        item["content"] = json.loads(item.pop("content_json") or "{}")
        items.append(item)
    return items


def save_interview_session(
    workspace_id: str,
    needs_interview: bool,
    trigger_reasons: list[str],
    questions: list[dict[str, Any]],
    answers: dict[str, str] | None = None,
    status: str = "open",
) -> dict[str, Any]:
    interview_id = str(uuid.uuid4())
    timestamp = now_string()
    answers = answers or {}
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO interview_sessions
            (id, workspace_id, status, needs_interview, trigger_reasons_json, questions_json, answers_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                interview_id,
                workspace_id,
                status,
                1 if needs_interview else 0,
                json.dumps(trigger_reasons, ensure_ascii=False),
                json.dumps(questions, ensure_ascii=False),
                json.dumps(answers, ensure_ascii=False),
                timestamp,
                timestamp,
            ),
        )
    touch_workspace(workspace_id)
    return get_latest_interview_session(workspace_id) or {}


def update_interview_answers(workspace_id: str, answers: dict[str, str]) -> dict[str, Any]:
    latest = get_latest_interview_session(workspace_id)
    if not latest:
        raise KeyError("Interview session not found")
    merged_answers = dict(latest["answers"])
    merged_answers.update(answers)
    status = "completed" if all(merged_answers.get(question["key"], "").strip() for question in latest["questions"]) else "open"
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE interview_sessions
            SET answers_json = ?, updated_at = ?, status = ?
            WHERE id = ?
            """,
            (
                json.dumps(merged_answers, ensure_ascii=False),
                now_string(),
                status,
                latest["id"],
            ),
        )
    touch_workspace(workspace_id)
    return get_latest_interview_session(workspace_id) or {}


def get_latest_interview_session(workspace_id: str) -> dict[str, Any] | None:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT *
            FROM interview_sessions
            WHERE workspace_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (workspace_id,),
        ).fetchone()
    if row is None:
        return None
    item = dict(row)
    item["needs_interview"] = bool(item["needs_interview"])
    item["trigger_reasons"] = json.loads(item.pop("trigger_reasons_json") or "[]")
    item["questions"] = json.loads(item.pop("questions_json") or "[]")
    item["answers"] = json.loads(item.pop("answers_json") or "{}")
    return item


def replace_title_candidates(workspace_id: str, candidates: list[dict[str, Any]], selected_title_id: str | None = None) -> list[dict[str, Any]]:
    timestamp = now_string()
    with get_connection() as connection:
        connection.execute("DELETE FROM title_candidates WHERE workspace_id = ?", (workspace_id,))
        for candidate in candidates:
            candidate_id = candidate.get("id") or str(uuid.uuid4())
            connection.execute(
                """
                INSERT INTO title_candidates
                (id, workspace_id, title, school_fit, mentor_fit, role_fit, evidence_fit, confidentiality_fit, total_score,
                 recommendation, caution, reasons_json, risk_tags_json, selected, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    candidate_id,
                    workspace_id,
                    candidate["title"],
                    candidate["school_fit"],
                    candidate["mentor_fit"],
                    candidate["role_fit"],
                    candidate["evidence_fit"],
                    candidate["confidentiality_fit"],
                    candidate["total_score"],
                    candidate["recommendation"],
                    candidate["caution"],
                    json.dumps(candidate.get("reasons", []), ensure_ascii=False),
                    json.dumps(candidate.get("risk_tags", []), ensure_ascii=False),
                    1 if candidate_id == selected_title_id else 0,
                    timestamp,
                ),
            )
    if selected_title_id:
        set_selected_title(workspace_id, selected_title_id)
    touch_workspace(workspace_id)
    return list_title_candidates(workspace_id)


def set_selected_title(workspace_id: str, title_id: str) -> None:
    with get_connection() as connection:
        connection.execute(
            "UPDATE title_candidates SET selected = CASE WHEN id = ? THEN 1 ELSE 0 END WHERE workspace_id = ?",
            (title_id, workspace_id),
        )
        connection.execute(
            "UPDATE workspaces SET selected_title_id = ?, updated_at = ? WHERE id = ?",
            (title_id, now_string(), workspace_id),
        )


def list_title_candidates(workspace_id: str) -> list[dict[str, Any]]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM title_candidates
            WHERE workspace_id = ?
            ORDER BY total_score DESC, created_at DESC
            """,
            (workspace_id,),
        ).fetchall()
    items = []
    for row in rows:
        item = dict(row)
        item["selected"] = bool(item["selected"])
        item["reasons"] = json.loads(item.pop("reasons_json") or "[]")
        item["risk_tags"] = json.loads(item.pop("risk_tags_json") or "[]")
        items.append(item)
    return items


def save_deliverable_bundle(
    workspace_id: str,
    report_markdown_path: str,
    report_docx_path: str,
    deck_pptx_path: str,
    notes_md_path: str,
    notes_docx_path: str,
    snapshot_path: str,
) -> dict[str, Any]:
    bundle_id = str(uuid.uuid4())
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO deliverable_bundles
            (id, workspace_id, report_markdown_path, report_docx_path, deck_pptx_path, notes_md_path, notes_docx_path, snapshot_path, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                bundle_id,
                workspace_id,
                report_markdown_path,
                report_docx_path,
                deck_pptx_path,
                notes_md_path,
                notes_docx_path,
                snapshot_path,
                now_string(),
            ),
        )
    touch_workspace(workspace_id)
    return get_latest_deliverable_bundle(workspace_id) or {}


def get_latest_deliverable_bundle(workspace_id: str) -> dict[str, Any] | None:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT *
            FROM deliverable_bundles
            WHERE workspace_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (workspace_id,),
        ).fetchone()
    return row_to_dict(row)


def ingest_local_file(workspace_id: str, source_path: Path, custom_category: str | None = None) -> dict[str, Any]:
    workspace = get_workspace_row(workspace_id)
    source_dir = Path(workspace["workspace_dir"]) / "sources"
    source_dir.mkdir(parents=True, exist_ok=True)
    target_path = source_dir / source_path.name
    if source_path.resolve() != target_path.resolve():
        shutil.copy2(source_path, target_path)
    category = custom_category or classify_local_file(target_path)
    text = read_text(target_path) if target_path.suffix.lower() in {".md", ".txt", ".docx", ".pdf"} else ""
    metadata = extract_metadata(text)
    evidence = add_evidence_item(
        workspace_id=workspace_id,
        evidence_type="local_file",
        title=target_path.name,
        summary=evidence_summary_from_text(text),
        grade=grade_for_local_category(category),
        status="verified" if text else "uploaded",
        source_label=category,
        source_uri=str(target_path),
        source_date=today_string(),
        metadata={
            "category": category,
            "path": str(target_path),
            "metadata": metadata,
            "urls": extract_urls(text),
        },
        content={"excerpt": text[:4000]},
    )
    for key, value in metadata.items():
        add_field_value(
            workspace_id=workspace_id,
            field_key=key,
            value=value,
            source_label=target_path.name,
            source_kind="upload",
            source_uri=str(target_path),
            source_grade=evidence["grade"],
            confidence=0.85,
            confirmed=False,
        )
    return evidence


def _field_rank(item: dict[str, Any]) -> tuple[int, int, int, float, str]:
    grade_weight = {"A": 4, "B": 3, "C": 2, "D": 1}.get(item["source_grade"], 0)
    kind_weight = {
        "official_web": 4,
        "upload": 4,
        "citation": 4,
        "profile": 3,
        "interview": 2,
        "user_input": 2,
        "inference": 1,
    }.get(item["source_kind"], 0)
    confirmed_weight = 1 if item["confirmed"] else 0
    return (
        confirmed_weight,
        grade_weight,
        kind_weight,
        float(item["confidence"]),
        item["captured_at"],
    )


def group_field_values(workspace_id: str) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in list_field_values(workspace_id):
        grouped.setdefault(item["field_key"], []).append(item)
    result: dict[str, dict[str, Any]] = {}
    for key, values in grouped.items():
        values.sort(key=_field_rank, reverse=True)
        unique_values = {item["value"] for item in values if item["value"].strip()}
        result[key] = {
            "key": key,
            "current": values[0],
            "values": values,
            "has_conflict": len(unique_values) > 1,
        }
    return result


def current_field_map(workspace_id: str) -> dict[str, Any]:
    groups = group_field_values(workspace_id)
    return {key: payload["current"]["value"] for key, payload in groups.items()}


def build_risks(workspace_id: str) -> list[dict[str, Any]]:
    fields = group_field_values(workspace_id)
    evidence_items = list_evidence_items(workspace_id)
    titles = list_title_candidates(workspace_id)
    deliverable = get_latest_deliverable_bundle(workspace_id)
    risks: list[dict[str, Any]] = []
    required_fields = {
        "mentor_name": "导师信息缺失，题目推荐会偏离导师偏好。",
        "company_name": "单位信息缺失，题目可能脱离真实研究对象。",
        "role_title": "岗位职责缺失，无法准确评估岗位贴合度。",
        "pain_point": "真实痛点缺失，容易生成空泛选题。",
        "data_sources": "资料来源缺失，后续正文无法稳定落地。",
    }
    for field_key, description in required_fields.items():
        if not fields.get(field_key, {}).get("current", {}).get("value"):
            risks.append(
                {
                    "id": f"missing:{field_key}",
                    "title": f"缺少字段：{field_key}",
                    "body": description,
                    "priority": 3,
                }
            )
    for key, payload in fields.items():
        if payload["has_conflict"]:
            risks.append(
                {
                    "id": f"conflict:{key}",
                    "title": f"字段冲突：{key}",
                    "body": "当前字段存在多个不同来源的值，需人工确认。",
                    "priority": 2,
                }
            )
    verified_sources = [item for item in evidence_items if item["grade"] in {"A", "B"}]
    if len(verified_sources) < 5:
        risks.append(
            {
                "id": "evidence:insufficient",
                "title": "高等级证据不足",
                "body": "A/B 级证据少于 5 条，题目和正文容易失真。",
                "priority": 3,
            }
        )
    verified_citations = [
        item
        for item in evidence_items
        if item["evidence_type"] == "citation" and item["status"] == "verified"
    ]
    if not verified_citations:
        risks.append(
            {
                "id": "citation:missing",
                "title": "缺少可用文献",
                "body": "当前没有通过核验的文献，正文只能生成骨架，不能生成可信综述。",
                "priority": 3,
            }
        )
    if not titles:
        risks.append(
            {
                "id": "title:missing",
                "title": "尚未推荐题目",
                "body": "请先跑题目推荐，再进入正文生成。",
                "priority": 2,
            }
        )
    if titles and not any(item["selected"] for item in titles):
        risks.append(
            {
                "id": "title:unselected",
                "title": "尚未冻结题目",
                "body": "请确认一个候选题目，避免导出件继续漂移。",
                "priority": 2,
            }
        )
    if deliverable is None:
        risks.append(
            {
                "id": "deliverable:missing",
                "title": "尚未生成交付件",
                "body": "当前没有冻结版 Word / PPT / 讲稿。",
                "priority": 1,
            }
        )
    return sorted(risks, key=lambda item: item["priority"], reverse=True)


def create_snapshot(workspace_id: str, name: str, payload: dict[str, Any]) -> str:
    workspace = get_workspace_row(workspace_id)
    snapshot_path = Path(workspace["workspace_dir"]) / "snapshots" / f"{slug_from_title(name)}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.json"
    snapshot_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return str(snapshot_path)


def get_workspace_bundle(workspace_id: str) -> dict[str, Any]:
    workspace = get_workspace_row(workspace_id)
    field_groups = group_field_values(workspace_id)
    current_fields = {key: payload["current"]["value"] for key, payload in field_groups.items()}
    evidence_items = list_evidence_items(workspace_id)
    titles = list_title_candidates(workspace_id)
    interview = get_latest_interview_session(workspace_id)
    deliverable = get_latest_deliverable_bundle(workspace_id)
    profile = load_profile(workspace["school_profile"])
    return {
        "workspace": workspace,
        "profile": {
            "id": profile["id"],
            "name": profile["name"],
            "required_sections": profile["required_sections"],
            "deck_outline": profile["deck_outline"],
        },
        "current_fields": current_fields,
        "field_groups": list(field_groups.values()),
        "evidence_items": evidence_items,
        "interview_session": interview,
        "title_candidates": titles,
        "deliverable_bundle": deliverable,
        "risks": build_risks(workspace_id),
        "statistics": {
            "field_count": len(field_groups),
            "evidence_count": len(evidence_items),
            "citation_count": len([item for item in evidence_items if item["evidence_type"] == "citation"]),
            "verified_citation_count": len(
                [item for item in evidence_items if item["evidence_type"] == "citation" and item["status"] == "verified"]
            ),
        },
    }
