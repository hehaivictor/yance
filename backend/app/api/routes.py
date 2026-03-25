from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..services.evidence_service import import_citation_file
from ..services.enrichment_service import enrich_public_sources
from ..services.generation_service import freeze_deliverables, generate_report
from ..services.interview_service import generate_interview, submit_interview_answers
from ..services.recommendation_service import recommend_titles
from ..services.workspace_service import (
    add_field_value,
    create_workspace,
    delete_local_file_evidence,
    delete_workspace,
    get_latest_deliverable_bundle,
    get_workspace_bundle,
    ingest_local_file,
    ingest_web_link,
    list_profiles,
    list_workspaces,
    set_selected_title,
)


router = APIRouter(prefix="/api")


class WorkspaceCreatePayload(BaseModel):
    name: str = Field(..., min_length=2)
    school_profile: str = "whu"


class FieldValuePayload(BaseModel):
    key: str
    value: str
    confirmed: bool = True


class FieldUpdatePayload(BaseModel):
    values: list[FieldValuePayload]


class InterviewAnswerPayload(BaseModel):
    answers: dict[str, str]


class LinkImportPayload(BaseModel):
    urls: list[str]


class TitleSelectPayload(BaseModel):
    title_id: str


class GeneratePayload(BaseModel):
    title_id: Optional[str] = None


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/profiles")
def profiles() -> list[dict[str, Any]]:
    return list_profiles()


@router.get("/workspaces")
def workspaces() -> list[dict[str, Any]]:
    return list_workspaces()


@router.post("/workspaces")
def create_workspace_endpoint(payload: WorkspaceCreatePayload) -> dict[str, Any]:
    return create_workspace(payload.name, payload.school_profile)


@router.delete("/workspaces/{workspace_id}")
def delete_workspace_endpoint(workspace_id: str) -> dict[str, Any]:
    try:
        return delete_workspace(workspace_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/workspaces/{workspace_id}")
def get_workspace_endpoint(workspace_id: str) -> dict[str, Any]:
    try:
        return get_workspace_bundle(workspace_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/workspaces/{workspace_id}/fields")
def update_fields_endpoint(workspace_id: str, payload: FieldUpdatePayload) -> dict[str, Any]:
    try:
        for item in payload.values:
            add_field_value(
                workspace_id=workspace_id,
                field_key=item.key,
                value=item.value,
                source_label="用户输入",
                source_kind="user_input",
                source_uri="manual",
                source_grade="C",
                confidence=0.92,
                confirmed=item.confirmed,
            )
        try:
            enrich_public_sources(workspace_id)
        except Exception:
            pass
        return get_workspace_bundle(workspace_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/workspaces/{workspace_id}/files/upload")
async def upload_files_endpoint(
    workspace_id: str,
    files: list[UploadFile] = File(...),
) -> dict[str, Any]:
    workspace = get_workspace_bundle(workspace_id)
    source_dir = Path(workspace["workspace"]["workspace_dir"]) / "sources"
    created = []
    for upload in files:
        target = source_dir / upload.filename
        target.write_bytes(await upload.read())
        created.append(ingest_local_file(workspace_id, target))
    return {"uploaded": created, "workspace": get_workspace_bundle(workspace_id)}


@router.delete("/workspaces/{workspace_id}/files/{evidence_id}")
def delete_uploaded_file_endpoint(workspace_id: str, evidence_id: str) -> dict[str, Any]:
    try:
        result = delete_local_file_evidence(workspace_id, evidence_id)
        return {**result, "workspace": get_workspace_bundle(workspace_id)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/workspaces/{workspace_id}/citations/upload")
async def upload_citations_endpoint(
    workspace_id: str,
    files: list[UploadFile] = File(...),
) -> dict[str, Any]:
    workspace = get_workspace_bundle(workspace_id)
    source_dir = Path(workspace["workspace"]["workspace_dir"]) / "sources"
    created = []
    for upload in files:
        target = source_dir / upload.filename
        target.write_bytes(await upload.read())
        created.extend(import_citation_file(workspace_id, target))
    return {"citations": created, "workspace": get_workspace_bundle(workspace_id)}


@router.post("/workspaces/{workspace_id}/links/import")
def import_links_endpoint(workspace_id: str, payload: LinkImportPayload) -> dict[str, Any]:
    created = []
    for url in payload.urls:
        normalized = url.strip()
        if not normalized:
            continue
        created.append(ingest_web_link(workspace_id, normalized))
    return {"links": created, "workspace": get_workspace_bundle(workspace_id)}


@router.post("/workspaces/{workspace_id}/enrich")
def enrich_endpoint(workspace_id: str) -> dict[str, Any]:
    try:
        result = enrich_public_sources(workspace_id)
        return {"result": result, "workspace": get_workspace_bundle(workspace_id)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/workspaces/{workspace_id}/interview/generate")
def generate_interview_endpoint(workspace_id: str) -> dict[str, Any]:
    try:
        session = generate_interview(workspace_id)
        return {"interview_session": session, "workspace": get_workspace_bundle(workspace_id)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/workspaces/{workspace_id}/interview/answer")
def submit_interview_endpoint(workspace_id: str, payload: InterviewAnswerPayload) -> dict[str, Any]:
    try:
        session = submit_interview_answers(workspace_id, payload.answers)
        return {"interview_session": session, "workspace": get_workspace_bundle(workspace_id)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/workspaces/{workspace_id}/titles/recommend")
def recommend_titles_endpoint(workspace_id: str) -> dict[str, Any]:
    try:
        titles = recommend_titles(workspace_id)
        return {"title_candidates": titles, "workspace": get_workspace_bundle(workspace_id)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/workspaces/{workspace_id}/titles/select")
def select_title_endpoint(workspace_id: str, payload: TitleSelectPayload) -> dict[str, Any]:
    try:
        set_selected_title(workspace_id, payload.title_id)
        return get_workspace_bundle(workspace_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/workspaces/{workspace_id}/report/generate")
def generate_report_endpoint(workspace_id: str, payload: GeneratePayload) -> dict[str, Any]:
    try:
        result = generate_report(workspace_id, payload.title_id)
        return {"report": result, "workspace": get_workspace_bundle(workspace_id)}
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/workspaces/{workspace_id}/deliverables/freeze")
def freeze_deliverables_endpoint(workspace_id: str, payload: GeneratePayload) -> dict[str, Any]:
    try:
        result = freeze_deliverables(workspace_id, payload.title_id)
        return {"deliverables": result, "workspace": get_workspace_bundle(workspace_id)}
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/workspaces/{workspace_id}/download/{artifact_name}")
def download_artifact_endpoint(workspace_id: str, artifact_name: str) -> FileResponse:
    bundle = get_latest_deliverable_bundle(workspace_id)
    if bundle is None:
        raise HTTPException(status_code=404, detail="No deliverable bundle found")
    allowed = {
        "report_md": bundle["report_markdown_path"],
        "report_docx": bundle["report_docx_path"],
        "deck_pptx": bundle["deck_pptx_path"],
        "notes_md": bundle["notes_md_path"],
        "notes_docx": bundle["notes_docx_path"],
        "snapshot": bundle["snapshot_path"],
    }
    if artifact_name not in allowed:
        raise HTTPException(status_code=404, detail="Unknown artifact")
    path = Path(allowed[artifact_name])
    if not path.exists():
        raise HTTPException(status_code=404, detail="Artifact file not found")
    return FileResponse(path, filename=path.name)
