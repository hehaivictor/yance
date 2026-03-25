import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core import parsing


def test_read_text_uses_ocr_for_image_when_enabled(tmp_path: Path, monkeypatch) -> None:
    image_path = tmp_path / "sample.png"
    image_path.write_bytes(b"fake-image")

    monkeypatch.setattr(parsing, "is_enabled", lambda: True)
    monkeypatch.setattr(parsing, "extract_image_text", lambda path: "识别出的图片文字")

    assert parsing.read_text(image_path) == "识别出的图片文字"


def test_read_text_returns_empty_for_image_when_ocr_disabled(tmp_path: Path, monkeypatch) -> None:
    image_path = tmp_path / "sample.jpg"
    image_path.write_bytes(b"fake-image")

    monkeypatch.setattr(parsing, "is_enabled", lambda: False)

    assert parsing.read_text(image_path) == ""


def test_normalize_ocr_text_drops_empty_markers() -> None:
    assert parsing._normalize_ocr_text("空字符串") == ""
    assert parsing._normalize_ocr_text("```text\n识别内容\n```") == "识别内容"
