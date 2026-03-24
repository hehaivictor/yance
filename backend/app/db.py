from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .config import settings


SCHEMA = """
CREATE TABLE IF NOT EXISTS workspaces (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  school_profile TEXT NOT NULL,
  status TEXT NOT NULL,
  workspace_dir TEXT NOT NULL,
  selected_title_id TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS field_values (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL,
  field_key TEXT NOT NULL,
  value TEXT NOT NULL,
  source_label TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  source_uri TEXT,
  source_grade TEXT NOT NULL,
  captured_at TEXT NOT NULL,
  confidence REAL NOT NULL,
  confirmed INTEGER NOT NULL,
  notes TEXT,
  FOREIGN KEY(workspace_id) REFERENCES workspaces(id)
);

CREATE TABLE IF NOT EXISTS evidence_items (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL,
  evidence_type TEXT NOT NULL,
  title TEXT NOT NULL,
  summary TEXT NOT NULL,
  grade TEXT NOT NULL,
  status TEXT NOT NULL,
  source_uri TEXT,
  source_label TEXT NOT NULL,
  source_date TEXT,
  captured_at TEXT NOT NULL,
  metadata_json TEXT NOT NULL,
  content_json TEXT NOT NULL,
  FOREIGN KEY(workspace_id) REFERENCES workspaces(id)
);

CREATE TABLE IF NOT EXISTS interview_sessions (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL,
  status TEXT NOT NULL,
  needs_interview INTEGER NOT NULL,
  trigger_reasons_json TEXT NOT NULL,
  questions_json TEXT NOT NULL,
  answers_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  FOREIGN KEY(workspace_id) REFERENCES workspaces(id)
);

CREATE TABLE IF NOT EXISTS title_candidates (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL,
  title TEXT NOT NULL,
  school_fit REAL NOT NULL,
  mentor_fit REAL NOT NULL,
  role_fit REAL NOT NULL,
  evidence_fit REAL NOT NULL,
  confidentiality_fit REAL NOT NULL,
  total_score REAL NOT NULL,
  recommendation TEXT NOT NULL,
  caution TEXT NOT NULL,
  reasons_json TEXT NOT NULL,
  risk_tags_json TEXT NOT NULL,
  selected INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY(workspace_id) REFERENCES workspaces(id)
);

CREATE TABLE IF NOT EXISTS deliverable_bundles (
  id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL,
  report_markdown_path TEXT NOT NULL,
  report_docx_path TEXT NOT NULL,
  deck_pptx_path TEXT NOT NULL,
  notes_md_path TEXT NOT NULL,
  notes_docx_path TEXT NOT NULL,
  snapshot_path TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY(workspace_id) REFERENCES workspaces(id)
);
"""


def init_db() -> None:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(settings.database_path)
    try:
        connection.executescript(SCHEMA)
        connection.commit()
    finally:
        connection.close()


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    connection = sqlite3.connect(settings.database_path)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row is not None else None


def path_exists(path: str | Path) -> bool:
    return Path(path).exists()
