import fs from "node:fs/promises";
import { createRequire } from "node:module";

import PptxGenJS from "pptxgenjs";

const require = createRequire(import.meta.url);
const {
  warnIfSlideHasOverlaps,
  warnIfSlideElementsOutOfBounds,
} = require("./pptxgenjs_helpers/layout.js");
let SHAPE_TYPE;

const COLORS = {
  navy: "13263D",
  navySoft: "213C5A",
  ink: "1A2433",
  inkSoft: "6D7788",
  sand: "E8D9C3",
  sandDeep: "D7B899",
  warm: "F5EEE3",
  warmAlt: "FBF8F2",
  paper: "FFFDFC",
  line: "E5DCCF",
  accent: "D87934",
  accentSoft: "F1D9C4",
};

const FONTS = {
  head: "PingFang SC",
  body: "PingFang SC",
};

const PAGE_LABELS = {
  cover: "开题答辩汇报",
  background: "选题背景",
  problem: "问题界定",
  questions: "研究目标",
  methods: "研究设计",
  sources: "文献与资料基础",
  outline: "结构与方案",
  timeline: "进度安排",
};

function textLength(value) {
  return String(value || "").replace(/\s+/g, "").length;
}

function clipText(value, max = 52) {
  const source = String(value || "").trim();
  return source.length > max ? `${source.slice(0, max - 1)}…` : source;
}

function toBulletText(value) {
  return String(value || "")
    .replace(/^(?:[-•]\s+|\(?\d{1,2}[.\-、)]\s+)/, "")
    .replace(/\s+/g, " ")
    .trim();
}

function titleSize(title, { cover = false } = {}) {
  const length = textLength(title);
  if (cover) {
    if (length > 28) return 24;
    if (length > 20) return 27;
    return 31;
  }
  if (length > 18) return 21;
  if (length > 12) return 23;
  return 25;
}

function bulletFontSize(text) {
  const length = textLength(text);
  if (length > 66) return 13.5;
  if (length > 48) return 14.2;
  return 15.2;
}

function estimateBulletHeight(text) {
  const length = textLength(text);
  const lines = Math.max(1, Math.ceil(length / 26));
  return 0.5 + lines * 0.3;
}

function addText(slide, text, options = {}) {
  slide.addText(String(text || ""), {
    fontFace: FONTS.body,
    color: COLORS.ink,
    margin: 0,
    valign: "mid",
    ...options,
  });
}

function addPageShell(slide) {
  slide.background = { color: COLORS.warm };
  slide.addShape(SHAPE_TYPE.roundRect, {
    x: 0.28,
    y: 0.22,
    w: 12.78,
    h: 7.02,
    rectRadius: 0.12,
    fill: { color: COLORS.paper },
    line: { color: COLORS.line, width: 1.2 },
  });
  slide.addShape(SHAPE_TYPE.rect, {
    x: 0.28,
    y: 0.22,
    w: 12.78,
    h: 0.16,
    fill: { color: COLORS.accentSoft, transparency: 20 },
    line: { color: COLORS.accentSoft, transparency: 100 },
  });
}

function addContentHeader(slide, spec, payload) {
  addText(slide, payload.role || PAGE_LABELS[payload.id] || "开题汇报", {
    x: 0.82,
    y: 0.58,
    w: 3.0,
    h: 0.18,
    fontSize: 8.5,
    bold: false,
    color: COLORS.inkSoft,
    charSpace: 2.8,
    allCaps: true,
    valign: "mid",
  });
  addText(slide, payload.title, {
    x: 0.82,
    y: 0.82,
    w: 8.05,
    h: 0.5,
    fontFace: FONTS.head,
    fontSize: titleSize(payload.title),
    bold: true,
    color: COLORS.navy,
    valign: "mid",
  });

  slide.addShape(SHAPE_TYPE.roundRect, {
    x: 10.62,
    y: 0.62,
    w: 1.54,
    h: 0.48,
    rectRadius: 0.14,
    fill: { color: COLORS.warmAlt },
    line: { color: COLORS.line, width: 1 },
  });
  addText(slide, `${payload.duration_seconds}秒`, {
    x: 10.62,
    y: 0.62,
    w: 1.54,
    h: 0.48,
    align: "center",
    fontSize: 10.5,
    bold: true,
    color: COLORS.accent,
  });
  slide.addShape(SHAPE_TYPE.line, {
    x: 0.82,
    y: 1.34,
    w: 11.52,
    h: 0,
    line: { color: COLORS.line, width: 1.1 },
  });
  addText(slide, spec.footerLabel || "", {
    x: 0.86,
    y: 6.82,
    w: 2.6,
    h: 0.18,
    fontSize: 9.5,
    color: COLORS.inkSoft,
    valign: "mid",
  });
}

function pickCanvasBullets(payload, maxItems) {
  const source = Array.isArray(payload.bullets) ? payload.bullets.map(toBulletText) : [];
  const selected = [];
  let usedHeight = 0;
  for (const bullet of source) {
    const nextHeight = estimateBulletHeight(bullet);
    if (selected.length >= maxItems) break;
    if (selected.length > 0 && usedHeight + 0.18 + nextHeight > 4.72) break;
    usedHeight += (selected.length > 0 ? 0.18 : 0) + nextHeight;
    selected.push(bullet);
  }
  return selected.length ? selected : ["待根据正文补充。"];
}

function addBulletCards(slide, payload) {
  const bullets = pickCanvasBullets(payload, 3);
  let y = 1.64;
  bullets.forEach((bullet, index) => {
    const cardHeight = estimateBulletHeight(bullet);
    slide.addShape(SHAPE_TYPE.roundRect, {
      x: 0.82,
      y,
      w: 8.14,
      h: cardHeight,
      rectRadius: 0.08,
      fill: { color: index % 2 === 0 ? COLORS.warmAlt : COLORS.paper },
      line: { color: COLORS.line, width: 1 },
    });
    slide.addShape(SHAPE_TYPE.rect, {
      x: 0.98,
      y: y + 0.16,
      w: 0.07,
      h: cardHeight - 0.32,
      fill: { color: index % 2 === 0 ? COLORS.accent : COLORS.navySoft },
      line: { color: index % 2 === 0 ? COLORS.accent : COLORS.navySoft, transparency: 100 },
    });
    addText(slide, String(index + 1).padStart(2, "0"), {
      x: 1.18,
      y: y + 0.14,
      w: 0.42,
      h: 0.16,
      fontSize: 10,
      bold: true,
      color: COLORS.accent,
      valign: "mid",
    });
    addText(slide, bullet, {
      x: 1.68,
      y: y + 0.15,
      w: 6.86,
      h: cardHeight - 0.3,
      fontSize: bulletFontSize(bullet),
      bold: false,
      color: COLORS.ink,
      breakLine: false,
      valign: "mid",
    });
    y += cardHeight + 0.18;
  });
}

function addInsightPanel(slide, payload) {
  slide.addShape(SHAPE_TYPE.roundRect, {
    x: 9.3,
    y: 1.6,
    w: 3.0,
    h: 4.7,
    rectRadius: 0.12,
    fill: { color: COLORS.warm },
    line: { color: COLORS.line, width: 1 },
  });
  addText(slide, "本页重点", {
    x: 9.62,
    y: 1.9,
    w: 1.3,
    h: 0.18,
    fontSize: 8.5,
    color: COLORS.inkSoft,
    charSpace: 2,
    allCaps: true,
  });
  addText(slide, clipText(payload.role || payload.title, 12), {
    x: 9.62,
    y: 2.16,
    w: 2.2,
    h: 0.32,
    fontFace: FONTS.head,
    fontSize: 18,
    bold: true,
    color: COLORS.navy,
  });
  slide.addShape(SHAPE_TYPE.line, {
    x: 9.62,
    y: 2.68,
    w: 2.32,
    h: 0,
    line: { color: COLORS.sandDeep, width: 1.4 },
  });

  addText(slide, "建议时长", {
    x: 9.62,
    y: 2.95,
    w: 1.2,
    h: 0.18,
    fontSize: 9.5,
    bold: true,
    color: COLORS.inkSoft,
  });
  addText(slide, `${payload.duration_seconds} 秒`, {
    x: 9.62,
    y: 3.2,
    w: 2.0,
    h: 0.28,
    fontSize: 16,
    bold: true,
    color: COLORS.accent,
  });

  addText(slide, "核心信息", {
    x: 9.62,
    y: 3.72,
    w: 1.2,
    h: 0.18,
    fontSize: 9.5,
    bold: true,
    color: COLORS.inkSoft,
  });
  slide.addShape(SHAPE_TYPE.roundRect, {
    x: 9.62,
    y: 4.02,
    w: 2.28,
    h: 1.48,
    rectRadius: 0.08,
    fill: { color: COLORS.paper },
    line: { color: COLORS.line, width: 0.8 },
  });
  addText(slide, clipText(toBulletText(payload.summary), 56), {
    x: 9.84,
    y: 4.22,
    w: 1.86,
    h: 1.02,
    fontSize: 13.2,
    color: COLORS.ink,
    valign: "top",
  });

  addText(slide, `第 ${String(payload.page_no).padStart(2, "0")} 页 · ${clipText(payload.role || payload.title, 10)}`, {
    x: 9.62,
    y: 5.82,
    w: 2.28,
    h: 0.18,
    fontSize: 9.5,
    color: COLORS.navy,
    bold: true,
    align: "center",
  });
}

function renderStandardSlide(pptx, slide, spec, payload) {
  addPageShell(slide);
  addContentHeader(slide, spec, payload);
  addBulletCards(slide, payload);
  addInsightPanel(slide, payload);
  warnIfSlideHasOverlaps(slide, pptx);
  warnIfSlideElementsOutOfBounds(slide, pptx);
}

function renderTimelineSlide(pptx, slide, spec, payload) {
  addPageShell(slide);
  addContentHeader(slide, spec, payload);

  const milestones = pickCanvasBullets(payload, 4);
  const positions = [
    { x: 0.94, y: 1.72 },
    { x: 6.06, y: 1.72 },
    { x: 0.94, y: 4.1 },
    { x: 6.06, y: 4.1 },
  ];

  slide.addShape(SHAPE_TYPE.line, {
    x: 2.48,
    y: 3.72,
    w: 5.22,
    h: 0,
    line: { color: COLORS.sandDeep, width: 1.8 },
  });
  milestones.forEach((bullet, index) => {
    const position = positions[index];
    if (!position) return;
    slide.addShape(SHAPE_TYPE.roundRect, {
      x: position.x,
      y: position.y,
      w: 4.28,
      h: 1.74,
      rectRadius: 0.08,
      fill: { color: index % 2 === 0 ? COLORS.warmAlt : COLORS.paper },
      line: { color: COLORS.line, width: 1 },
    });
    slide.addShape(SHAPE_TYPE.ellipse, {
      x: position.x + 0.18,
      y: position.y + 0.18,
      w: 0.34,
      h: 0.34,
      fill: { color: index % 2 === 0 ? COLORS.accent : COLORS.navySoft },
      line: { color: index % 2 === 0 ? COLORS.accent : COLORS.navySoft, transparency: 100 },
    });
    addText(slide, String(index + 1).padStart(2, "0"), {
      x: position.x + 0.68,
      y: position.y + 0.18,
      w: 0.5,
      h: 0.2,
      fontSize: 10,
      bold: true,
      color: COLORS.accent,
    });
    addText(slide, bullet, {
      x: position.x + 0.68,
      y: position.y + 0.48,
      w: 3.16,
      h: 0.88,
      fontSize: 14.2,
      color: COLORS.ink,
      valign: "top",
    });
  });

  slide.addShape(SHAPE_TYPE.roundRect, {
    x: 10.64,
    y: 1.72,
    w: 1.56,
    h: 4.16,
    rectRadius: 0.08,
    fill: { color: COLORS.warm },
    line: { color: COLORS.line, width: 1 },
  });
  addText(slide, "推进节奏", {
    x: 10.86,
    y: 1.98,
    w: 1.08,
    h: 0.18,
    fontSize: 8.5,
    color: COLORS.inkSoft,
    charSpace: 2.2,
    allCaps: true,
  });
  addText(slide, `${payload.duration_seconds}秒`, {
    x: 10.86,
    y: 2.3,
    w: 1.08,
    h: 0.28,
    fontSize: 16,
    bold: true,
    color: COLORS.accent,
    align: "center",
  });
  addText(slide, "从开题、调研、分析到成稿，节奏按阶段推进并预留修改缓冲。", {
    x: 10.86,
    y: 2.82,
    w: 1.08,
    h: 2.16,
    fontSize: 12.4,
    color: COLORS.ink,
    valign: "top",
    align: "left",
  });

  warnIfSlideHasOverlaps(slide, pptx);
  warnIfSlideElementsOutOfBounds(slide, pptx);
}

function renderCoverSlide(pptx, slide, spec, payload) {
  slide.background = { color: COLORS.navy };
  slide.addShape(SHAPE_TYPE.rect, {
    x: 0,
    y: 0,
    w: 13.333,
    h: 7.5,
    fill: { color: COLORS.navy },
    line: { color: COLORS.navy, transparency: 100 },
  });
  slide.addShape(SHAPE_TYPE.roundRect, {
    x: 0.48,
    y: 0.52,
    w: 12.35,
    h: 6.46,
    rectRadius: 0.12,
    fill: { color: COLORS.navySoft, transparency: 12 },
    line: { color: "FFFFFF", transparency: 88, width: 0.8 },
  });
  slide.addShape(SHAPE_TYPE.ellipse, {
    x: 10.18,
    y: 0.08,
    w: 2.78,
    h: 2.78,
    fill: { color: COLORS.accent, transparency: 87 },
    line: { color: COLORS.accent, transparency: 100 },
  });
  slide.addShape(SHAPE_TYPE.ellipse, {
    x: 0.12,
    y: 5.02,
    w: 2.36,
    h: 2.36,
    fill: { color: "FFFFFF", transparency: 95 },
    line: { color: "FFFFFF", transparency: 100 },
  });
  slide.addShape(SHAPE_TYPE.rect, {
    x: 0.92,
    y: 1.14,
    w: 0.12,
    h: 2.34,
    fill: { color: COLORS.accent },
    line: { color: COLORS.accent, transparency: 100 },
  });
  addText(slide, "ACADEMIC PROPOSAL DEFENSE", {
    x: 1.22,
    y: 1.06,
    w: 4.6,
    h: 0.2,
    fontSize: 9,
    color: "E7D8C5",
    charSpace: 2.8,
    allCaps: true,
  });
  addText(slide, spec.title, {
    x: 1.22,
    y: 1.52,
    w: 8.64,
    h: 1.24,
    fontFace: FONTS.head,
    fontSize: titleSize(spec.title, { cover: true }),
    bold: true,
    color: "FFFFFF",
    valign: "mid",
  });
  addText(slide, "专业学位论文开题答辩汇报", {
    x: 1.24,
    y: 3.02,
    w: 4.36,
    h: 0.24,
    fontSize: 12.5,
    color: "E8DDD2",
  });
  addText(slide, clipText(spec.footerLabel || spec.basicInfo.school_name || "", 16), {
    x: 1.24,
    y: 3.38,
    w: 2.66,
    h: 0.2,
    fontSize: 10.5,
    color: "D6C4B2",
  });

  slide.addShape(SHAPE_TYPE.roundRect, {
    x: 1.22,
    y: 4.62,
    w: 10.88,
    h: 1.56,
    rectRadius: 0.08,
    fill: { color: COLORS.paper, transparency: 6 },
    line: { color: "FFFFFF", transparency: 72, width: 0.8 },
  });

  const metaItems = [
    { label: "学生", value: spec.basicInfo.student_name || "待确认" },
    { label: "导师", value: spec.basicInfo.mentor_name || "待确认" },
    { label: "单位", value: spec.basicInfo.company_name || "待确认" },
    { label: "类型", value: spec.basicInfo.thesis_type || "专题研究类" },
  ];
  metaItems.forEach((item, index) => {
    const col = index % 2;
    const row = Math.floor(index / 2);
    const x = 1.56 + col * 5.18;
    const y = 4.96 + row * 0.58;
    addText(slide, item.label, {
      x,
      y,
      w: 0.52,
      h: 0.16,
      fontSize: 9.2,
      bold: true,
      color: COLORS.inkSoft,
    });
    addText(slide, clipText(item.value, 20), {
      x: x + 0.62,
      y: y - 0.02,
      w: 4.16,
      h: 0.2,
      fontSize: 12.8,
      bold: true,
      color: COLORS.navy,
    });
  });

  addText(slide, "Yance 研策", {
    x: 10.86,
    y: 6.54,
    w: 1.18,
    h: 0.18,
    fontSize: 10,
    bold: true,
    color: "F2E7D9",
    align: "right",
  });
  addText(slide, String(payload.page_no).padStart(2, "0"), {
    x: 12.08,
    y: 6.54,
    w: 0.36,
    h: 0.18,
    fontSize: 10,
    bold: true,
    color: "F2E7D9",
    align: "right",
  });

  warnIfSlideHasOverlaps(slide, pptx);
  warnIfSlideElementsOutOfBounds(slide, pptx);
}

async function main() {
  const specPath = process.argv[2];
  if (!specPath) {
    throw new Error("Missing deck spec path");
  }

  const raw = await fs.readFile(specPath, "utf8");
  const spec = JSON.parse(raw);
  const pptx = new PptxGenJS();
  SHAPE_TYPE = pptx.ShapeType;
  pptx.layout = "LAYOUT_WIDE";
  pptx.author = "Yance";
  pptx.company = "Yance";
  pptx.subject = `${spec.title} 开题答辩PPT`;
  pptx.title = `${spec.title} 开题答辩PPT`;
  pptx.lang = "zh-CN";
  pptx.theme = {
    headFontFace: FONTS.head,
    bodyFontFace: FONTS.body,
    lang: "zh-CN",
  };

  for (const payload of spec.slides || []) {
    const slide = pptx.addSlide();
    if (payload.id === "cover") {
      renderCoverSlide(pptx, slide, spec, payload);
    } else if (payload.id === "timeline") {
      renderTimelineSlide(pptx, slide, spec, payload);
    } else {
      renderStandardSlide(pptx, slide, spec, payload);
    }
  }

  await pptx.writeFile({ fileName: spec.outputPath });
}

main().catch((error) => {
  console.error(error?.stack || String(error));
  process.exit(1);
});
