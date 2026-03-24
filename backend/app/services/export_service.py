from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from docx import Document
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT
from docx.shared import Pt
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt as PptPt


def markdown_to_docx(markdown_text: str, output_path: Path) -> None:
    document = Document()
    style = document.styles["Normal"]
    style.font.name = "PingFang SC"
    style.font.size = Pt(11)
    for raw_line in markdown_text.splitlines():
        line = raw_line.rstrip()
        if not line:
            document.add_paragraph("")
            continue
        if line.startswith("# "):
            paragraph = document.add_paragraph()
            paragraph.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
            run = paragraph.add_run(line[2:].strip())
            run.bold = True
            run.font.size = Pt(16)
            continue
        if line.startswith("## "):
            document.add_heading(line[3:].strip(), level=1)
            continue
        if re.match(r"^\d+\.\s+", line):
            document.add_paragraph(re.sub(r"^\d+\.\s+", "", line), style="List Number")
            continue
        if line.startswith("- "):
            document.add_paragraph(line[2:].strip(), style="List Bullet")
            continue
        document.add_paragraph(line)
    document.save(str(output_path))


def extract_markdown_sections(markdown: str) -> dict[str, str]:
    current = "ROOT"
    sections: dict[str, list[str]] = {current: []}
    for line in markdown.splitlines():
        if line.startswith("#"):
            current = line.lstrip("#").strip()
            sections.setdefault(current, [])
            continue
        sections[current].append(line)
    return {key: "\n".join(lines).strip() for key, lines in sections.items()}


def compress_to_bullets(text: str, max_items: int = 4) -> list[str]:
    candidates = re.split(r"(?<=[。！？；])\s*", re.sub(r"\s+", " ", text))
    bullets = []
    for sentence in candidates:
        cleaned = sentence.strip(" -")
        if not cleaned:
            continue
        bullets.append(cleaned[:88] + ("..." if len(cleaned) > 88 else ""))
        if len(bullets) >= max_items:
            break
    return bullets or ["待根据正文补充。"]


def render_bundle(
    markdown: str,
    title: str,
    deck_outline: list[dict[str, Any]],
    output_dir: Path,
    basic_info: dict[str, str],
    footer_label: str,
) -> dict[str, str]:
    safe_title = re.sub(r"[/:]", "-", title).strip()
    report_md_path = output_dir / f"{safe_title}-开题报告.md"
    report_docx_path = output_dir / f"{safe_title}-开题报告.docx"
    deck_path = output_dir / f"{safe_title}-开题答辩PPT.pptx"
    notes_md_path = output_dir / f"{safe_title}-开题答辩讲稿.md"
    notes_docx_path = output_dir / f"{safe_title}-开题答辩讲稿.docx"
    report_md_path.write_text(markdown, encoding="utf-8")
    markdown_to_docx(markdown, report_docx_path)

    sections = extract_markdown_sections(markdown)
    payloads = []
    section_map = {
        "background": compress_to_bullets(sections.get("选题背景与问题提出", "")),
        "problem": compress_to_bullets(sections.get("选题背景与问题提出", "")),
        "questions": compress_to_bullets(sections.get("研究目的", "")),
        "methods": compress_to_bullets(sections.get("研究方法、资料来源与技术路线", "")),
        "sources": compress_to_bullets(sections.get("研究方法、资料来源与技术路线", "")),
        "outline": compress_to_bullets(sections.get("研究内容、拟解决的关键问题及理论工具", "")),
        "timeline": compress_to_bullets(sections.get("研究计划与进度安排", "")),
    }
    for index, slide in enumerate(deck_outline, start=1):
        if slide["id"] == "cover":
            bullets = [
                f"题目：{title}",
                f"学生：{basic_info.get('student_name') or '待确认'}",
                f"导师：{basic_info.get('mentor_name') or '待确认'}",
                f"论文类型：{basic_info.get('thesis_type') or '专题研究类'}",
            ]
        else:
            bullets = section_map.get(slide["id"], ["待根据正文补充。"])
        payloads.append(
            {
                "page_no": index,
                "title": slide["title"],
                "id": slide["id"],
                "bullets": bullets[:5],
                "duration_seconds": slide["duration_seconds"],
            }
        )
    _render_presentation(payloads, footer_label, deck_path)
    notes_markdown = _render_notes_markdown(payloads, title)
    notes_md_path.write_text(notes_markdown, encoding="utf-8")
    markdown_to_docx(notes_markdown, notes_docx_path)
    return {
        "report_markdown_path": str(report_md_path),
        "report_docx_path": str(report_docx_path),
        "deck_pptx_path": str(deck_path),
        "notes_md_path": str(notes_md_path),
        "notes_docx_path": str(notes_docx_path),
    }


def _render_presentation(payloads: list[dict[str, Any]], footer_label: str, output_path: Path) -> None:
    presentation = Presentation()
    presentation.slide_width = Inches(13.333)
    presentation.slide_height = Inches(7.5)
    for payload in payloads:
        slide = presentation.slides.add_slide(presentation.slide_layouts[6])
        slide.background.fill.solid()
        slide.background.fill.fore_color.rgb = RGBColor(245, 242, 236)

        title_box = slide.shapes.add_textbox(Inches(0.6), Inches(0.5), Inches(10.8), Inches(0.6))
        paragraph = title_box.text_frame.paragraphs[0]
        paragraph.text = payload["title"]
        paragraph.font.size = PptPt(24)
        paragraph.font.bold = True
        paragraph.font.name = "PingFang SC"
        paragraph.font.color.rgb = RGBColor(20, 48, 78)

        page_no_box = slide.shapes.add_textbox(Inches(11.7), Inches(0.55), Inches(0.9), Inches(0.3))
        page_no = page_no_box.text_frame.paragraphs[0]
        page_no.text = str(payload["page_no"])
        page_no.alignment = PP_ALIGN.RIGHT
        page_no.font.size = PptPt(11)
        page_no.font.bold = True
        page_no.font.name = "PingFang SC"

        body_box = slide.shapes.add_textbox(Inches(0.9), Inches(1.45), Inches(11.3), Inches(5.3))
        frame = body_box.text_frame
        frame.word_wrap = True
        for index, bullet in enumerate(payload["bullets"]):
            paragraph = frame.paragraphs[0] if index == 0 else frame.add_paragraph()
            paragraph.text = bullet
            paragraph.level = 0
            paragraph.bullet = True
            paragraph.font.size = PptPt(19 if payload["id"] != "cover" else 18)
            paragraph.font.name = "PingFang SC"
            paragraph.font.color.rgb = RGBColor(34, 42, 53)
            paragraph.space_after = PptPt(10)

        footer = slide.shapes.add_textbox(Inches(0.9), Inches(6.9), Inches(4.0), Inches(0.3))
        footer_p = footer.text_frame.paragraphs[0]
        footer_p.text = footer_label
        footer_p.font.size = PptPt(10)
        footer_p.font.name = "PingFang SC"
        footer_p.font.color.rgb = RGBColor(92, 102, 112)
    presentation.save(str(output_path))


def _render_notes_markdown(payloads: list[dict[str, Any]], title: str) -> str:
    blocks = [f"# 《{title}》开题答辩讲稿", ""]
    for payload in payloads:
        bullets_text = "；".join(item.strip("0123456789. ") for item in payload["bullets"])
        blocks.extend(
            [
                f"## 第{payload['page_no']}页 {payload['title']}",
                "",
                f"建议时长：{payload['duration_seconds']}秒",
                "",
                f"本页重点说明：{bullets_text}",
                "",
            ]
        )
    return "\n".join(blocks).strip() + "\n"
