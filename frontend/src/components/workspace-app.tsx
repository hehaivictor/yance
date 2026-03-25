"use client";

import { type DragEvent, type FormEvent, type ReactNode, type RefObject, useCallback, useEffect, useRef, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";
const BRAND = {
  zhName: "研策",
  enName: "Yance",
  zhPosition: "专业学位论文开题智能参谋",
  enPosition: "Academic Proposal Strategist",
} as const;

const corporateSuffixes = ["股份有限公司", "有限责任公司", "有限公司", "集团公司", "集团", "公司"] as const;
const nonCompanyHints = ["大学", "学院", "研究院", "医院", "实验室", "中心", "事务所", "协会", "委员会", "政府", "机关", "学校"] as const;
const locationPrefixes = [
  "北京",
  "上海",
  "广州",
  "深圳",
  "武汉",
  "杭州",
  "南京",
  "苏州",
  "成都",
  "重庆",
  "天津",
  "西安",
  "长沙",
  "青岛",
  "厦门",
  "福州",
  "合肥",
  "郑州",
  "济南",
  "宁波",
  "无锡",
  "东莞",
  "佛山",
  "珠海",
  "南昌",
  "沈阳",
  "大连",
  "长春",
  "哈尔滨",
  "昆明",
  "贵阳",
  "南宁",
  "海口",
  "石家庄",
  "太原",
  "兰州",
  "西宁",
  "银川",
  "呼和浩特",
  "乌鲁木齐",
  "拉萨",
  "湖北",
  "湖南",
  "广东",
  "广西",
  "浙江",
  "江苏",
  "山东",
  "河南",
  "河北",
  "山西",
  "福建",
  "江西",
  "辽宁",
  "吉林",
  "黑龙江",
  "陕西",
  "四川",
  "云南",
  "贵州",
  "甘肃",
  "青海",
  "海南",
  "安徽",
] as const;
const businessSuffixes = [
  "信息技术",
  "工业软件",
  "管理咨询",
  "软件技术",
  "数字科技",
  "智能科技",
  "科技服务",
  "信息服务",
  "技术服务",
  "信息",
  "技术",
  "科技",
  "软件",
  "服饰",
  "网络",
  "数据",
  "智能",
  "管理",
  "咨询",
  "服务",
  "实业",
  "制造",
  "电子",
  "系统",
  "工程",
] as const;
const pinyinBoundaries = [
  ["阿", "A"],
  ["芭", "B"],
  ["擦", "C"],
  ["搭", "D"],
  ["蛾", "E"],
  ["发", "F"],
  ["噶", "G"],
  ["哈", "H"],
  ["机", "J"],
  ["喀", "K"],
  ["垃", "L"],
  ["妈", "M"],
  ["拿", "N"],
  ["哦", "O"],
  ["啪", "P"],
  ["期", "Q"],
  ["然", "R"],
  ["撒", "S"],
  ["塌", "T"],
  ["挖", "W"],
  ["昔", "X"],
  ["压", "Y"],
  ["匝", "Z"],
] as const;

type WorkspaceSummary = {
  id: string;
  name: string;
  school_profile: string;
};

type FieldGroup = {
  key: string;
  current: {
    value: string;
    source_label: string;
    source_grade: string;
    confirmed: boolean;
  };
  values: Array<{
    id: string;
    value: string;
    source_label: string;
    source_grade: string;
    confirmed: boolean;
  }>;
  has_conflict: boolean;
};

type EvidenceItem = {
  id: string;
  evidence_type: string;
  title: string;
  summary: string;
  grade: string;
  status: string;
  source_label: string;
  source_uri?: string;
};

type TitleCandidate = {
  id: string;
  title: string;
  school_fit: number;
  mentor_fit: number;
  role_fit: number;
  evidence_fit: number;
  confidentiality_fit: number;
  total_score: number;
  recommendation: string;
  caution: string;
  selected: boolean;
  reasons: string[];
  risk_tags: string[];
};

type InterviewQuestion = {
  key: string;
  question: string;
  placeholder: string;
};

type InterviewSession = {
  id: string;
  status: string;
  trigger_reasons: string[];
  questions: InterviewQuestion[];
  answers: Record<string, string>;
};

type DeliverableBundle = {
  report_markdown_path: string;
  report_docx_path: string;
  deck_pptx_path: string;
  notes_md_path: string;
  notes_docx_path: string;
  snapshot_path: string;
} | null;

type WorkspaceBundle = {
  workspace: {
    id: string;
    name: string;
    school_profile: string;
  };
  current_fields: Record<string, string>;
  field_groups: FieldGroup[];
  evidence_items: EvidenceItem[];
  title_candidates: TitleCandidate[];
  interview_session: InterviewSession | null;
  deliverable_bundle: DeliverableBundle;
  risks: Array<{ id: string; title: string; body: string; priority: number }>;
  profile: {
    name: string;
    required_sections: string[];
  };
  statistics: {
    evidence_count: number;
    citation_count: number;
    verified_citation_count: number;
  };
};

type ProfileOption = { id: string; name: string };

type ActionResponse = {
  workspace?: WorkspaceBundle;
  report?: { report_markdown?: string; report_title?: string };
  deliverables?: { report?: { report_markdown?: string; report_title?: string } };
};

type DeleteWorkspaceResponse = {
  deleted: boolean;
  workspace_id: string;
  name: string;
};

type DeleteUploadedFileResponse = {
  deleted: boolean;
  evidence_id: string;
  title: string;
  workspace: WorkspaceBundle;
};

type WorkspaceSection = "background" | "titles" | "proposal" | "materials";
type WorkspaceAction = "interview" | "recommend" | "generate-report" | "freeze-deliverables";
type ExportFormat = "word" | "ppt";
type DownloadArtifact = "report_md" | "report_docx" | "deck_pptx" | "notes_docx" | "snapshot";
type ReportSection = {
  heading: string;
  blocks: string[];
};

const editableKeys = [
  ["school_name", "学校名称", "例如：武汉大学", "single"],
  ["mentor_name", "导师姓名", "例如：王建国", "single"],
  ["student_name", "学生姓名", "例如：李军", "single"],
  ["student_id", "学号", "例如：2024012345", "single"],
  ["company_name", "工作单位", "例如：武汉思维创新股份有限公司", "single"],
  ["role_title", "工作职位", "例如：AI 产品负责人", "single"],
  ["work_scope", "负责内容描述", "写明你主要负责的业务、项目、流程或团队工作。", "multi"],
  ["research_direction", "拟研究方向", "例如：AI 智能体落地、组织协同、数据治理等。", "multi"],
] as const;

const fieldLabels = Object.fromEntries(
  editableKeys.map(([key, label]) => [key, label]),
) as Record<string, string>;
fieldLabels.pain_point = "真实管理问题";
fieldLabels.research_goal = "预期成果";
fieldLabels.confidentiality_notes = "保密边界";
fieldLabels.mentor_title = "导师职称";
fieldLabels.program_name = "项目类型";
fieldLabels.school_requirement_url = "写作要求链接";
fieldLabels.mentor_source_url = "导师来源链接";
fieldLabels.company_profile_url = "单位来源链接";

const coreFieldKeys = ["school_name", "mentor_name", "student_name", "student_id"] as const;
const mentorFieldKeys = ["school_name", "mentor_name"] as const;
const studentFieldKeys = ["student_name", "student_id"] as const;
const optionalFieldKeys = ["company_name", "role_title", "work_scope", "research_direction"] as const;
const mentorEditableKeys = editableKeys.filter(([key]) => mentorFieldKeys.includes(key as (typeof mentorFieldKeys)[number]));
const studentEditableKeys = editableKeys.filter(([key]) => studentFieldKeys.includes(key as (typeof studentFieldKeys)[number]));
const optionalEditableKeys = editableKeys.filter(([key]) => optionalFieldKeys.includes(key as (typeof optionalFieldKeys)[number]));
const sectionMeta: Record<
  WorkspaceSection,
  { label: string; title: string; body: string; short: string }
> = {
  background: {
    label: "基础信息",
    title: "基础信息",
    body: "先填必填项，再补资料。",
    short: "信息",
  },
  titles: {
    label: "推荐选题",
    title: "推荐选题",
    body: "保存后直接生成候选题。",
    short: "题目",
  },
  proposal: {
    label: "开题生成",
    title: "开题生成",
    body: "选题后直接生成报告，并从这里导出 Word 或 PPT。",
    short: "生成",
  },
  materials: {
    label: "开题生成",
    title: "开题生成",
    body: "Word、PPT、讲稿和来源快照只从冻结版报告派生，避免口径漂移。",
    short: "生成",
  },
};

function getFieldLabel(key: string) {
  return fieldLabels[key] || key.replaceAll("_", " ");
}

function prettifyCopy(value: string) {
  return Object.entries(fieldLabels).reduce(
    (current, [key, label]) => current.replaceAll(key, label),
    value,
  );
}

function extractReportTitleFromPath(path: string | undefined) {
  const normalized = String(path || "").trim();
  if (!normalized) return "";
  const filename = normalized.split("/").pop() || "";
  return filename
    .replace(/-开题报告\.(md|docx)$/i, "")
    .replace(/-report\.md$/i, "")
    .trim();
}

function anonymizedSubjectName(name: string, confidentiality = "") {
  const normalized = String(name || "").trim();
  if (!normalized) return "研究对象";
  const confidential = ["匿名", "保密", "不便披露", "化名"].some((keyword) =>
    String(confidentiality || "").includes(keyword),
  );
  const isCompany = !nonCompanyHints.some((hint) => normalized.includes(hint));
  if (confidential) return isCompany ? "K公司" : "K单位";
  const initial = subjectAliasInitial(normalized) || "K";
  return isCompany ? `${initial}公司` : `${initial}单位`;
}

function shortenSubjectName(name: string, maxLength = 10) {
  const normalized = String(name || "").trim();
  if (!normalized || normalized.length <= maxLength) return normalized;
  let stripped = normalized;
  corporateSuffixes.forEach((suffix) => {
    if (stripped.endsWith(suffix)) {
      stripped = stripped.slice(0, -suffix.length).trim();
    }
  });
  if (stripped && stripped.length <= maxLength) return stripped;
  return (stripped || normalized).slice(0, maxLength);
}

function subjectAliasInitial(name: string) {
  const core = companyCoreName(name);
  const firstChar = core.charAt(0);
  if (!firstChar) return "";
  if (/^[A-Za-z]$/.test(firstChar)) return firstChar.toUpperCase();
  for (let index = pinyinBoundaries.length - 1; index >= 0; index -= 1) {
    const [boundary, initial] = pinyinBoundaries[index];
    if (firstChar.localeCompare(boundary, "zh-CN-u-co-pinyin") >= 0) {
      return initial;
    }
  }
  return "";
}

function companyCoreName(name: string) {
  const normalized = String(name || "").replace(/[\s·•()（）\-_/]+/g, "").trim();
  if (!normalized) return "";
  let stripped = normalized;
  corporateSuffixes.forEach((suffix) => {
    if (stripped.endsWith(suffix)) {
      stripped = stripped.slice(0, -suffix.length).trim();
    }
  });
  let core = stripped || normalized;
  locationPrefixes.some((prefix) => {
    if (core.startsWith(prefix) && core.length > prefix.length + 1) {
      core = core.slice(prefix.length).trim();
      return true;
    }
    return false;
  });
  businessSuffixes.some((suffix) => {
    if (core.endsWith(suffix) && core.length > suffix.length + 1) {
      core = core.slice(0, -suffix.length).trim();
      return true;
    }
    return false;
  });
  return core || stripped || normalized;
}

function privacySafeReportTitle(title: string, companyName = "", confidentiality = "") {
  let normalized = String(title || "").trim();
  const subjectName = String(companyName || "").trim();
  if (!normalized || !subjectName) return normalized;
  const alias = anonymizedSubjectName(subjectName, confidentiality);
  const replacements = new Set<string>([subjectName, shortenSubjectName(subjectName)]);
  let stripped = subjectName;
  corporateSuffixes.forEach((suffix) => {
    if (stripped.endsWith(suffix)) {
      stripped = stripped.slice(0, -suffix.length).trim();
    }
  });
  if (stripped) replacements.add(stripped);
  Array.from(replacements)
    .filter(Boolean)
    .sort((a, b) => b.length - a.length)
    .forEach((candidate) => {
      normalized = normalized.replaceAll(candidate, alias);
    });
  return normalized;
}

function sanitizedDraftValue(key: string, value: string) {
  const normalized = String(value || "").trim();
  if (key === "research_direction" && normalized === "工商管理") {
    return "";
  }
  return value || "";
}

type NextStepInfo = {
  title: string;
  body: string;
  tone: "success" | "warning" | "danger" | "muted";
  section: WorkspaceSection;
};

function getNextStepInfo(
  bundle: WorkspaceBundle | null,
  selectedTitle: TitleCandidate | undefined,
  reportPreview: string,
): NextStepInfo {
  if (!bundle) {
    return {
      title: "先创建一个项目",
      body: "从学校规则开始，建立一个开题项目后再填写导师、单位和真实问题。",
      tone: "muted",
      section: "background",
    };
  }
  const missingCoreFields = coreFieldKeys.filter((key) => !(bundle.current_fields[key] || "").trim());
  if (missingCoreFields.length) {
    return {
      title: "先补全导师和学生必填信息",
      body: `至少还缺 ${missingCoreFields.map((key) => getFieldLabel(key)).join("、")}，题目推荐会明显失真。`,
      tone: "warning",
      section: "background",
    };
  }
  if (bundle.interview_session && bundle.interview_session.status !== "completed") {
    return {
      title: "回答收敛访谈",
      body: "把场景、案例、数据边界和导师偏好补具体，再让系统重新推荐题目。",
      tone: "warning",
      section: "titles",
    };
  }
  if (!bundle.title_candidates.length) {
    return {
      title: "生成推荐题目",
      body: "先出 3 到 5 个候选题，再从中冻结一个题目继续写。",
      tone: "warning",
      section: "titles",
    };
  }
  if (!selectedTitle) {
    return {
      title: "先选定一个题目",
      body: "没有冻结题目之前，报告和导出材料都会持续漂移。",
      tone: "warning",
      section: "titles",
    };
  }
  if (!reportPreview && !bundle.deliverable_bundle) {
    return {
      title: "生成开题报告",
      body: "题目确定后先生成报告草稿，再统一导出 Word、PPT 和讲稿。",
      tone: "warning",
      section: "proposal",
    };
  }
  if (!bundle.deliverable_bundle) {
    return {
      title: "导出开题材料",
      body: "报告草稿已经有了，下一步直接生成 Word、PPT 和讲稿。",
      tone: "warning",
      section: "proposal",
    };
  }
  return {
    title: "检查并下载开题材料",
    body: "现在重点看题目、研究问题和讲稿口径是否一致，再下载导出件。",
    tone: "success",
    section: "proposal",
  };
}

function normalizeSection(section: WorkspaceSection): WorkspaceSection {
  return section === "materials" ? "proposal" : section;
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || `请求失败: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

function toErrorMessage(error: unknown) {
  return error instanceof Error ? error.message : "请求失败";
}

async function fetchArtifactText(workspaceId: string, artifactName: DownloadArtifact): Promise<string> {
  const response = await fetch(`${API_BASE}/api/workspaces/${workspaceId}/download/${artifactName}`);
  if (!response.ok) {
    throw new Error(`读取报告失败: ${response.status}`);
  }
  return response.text();
}

function parseReportMarkdown(markdown: string) {
  const normalized = String(markdown || "").replace(/\r/g, "").trim();
  const lines = normalized.split("\n");
  const sections: ReportSection[] = [];
  let title = "";
  let currentSection: ReportSection | null = null;
  let blockBuffer: string[] = [];

  const flushBlock = () => {
    if (!currentSection) return;
    const block = blockBuffer.join("\n").trim();
    if (block) {
      currentSection.blocks.push(block);
    }
    blockBuffer = [];
  };

  for (const rawLine of lines) {
    const line = rawLine.trimEnd();
    if (!line.trim()) {
      flushBlock();
      continue;
    }
    if (line.startsWith("# ")) {
      title = line.replace(/^#\s+/, "").trim();
      continue;
    }
    if (line.startsWith("## ")) {
      flushBlock();
      if (currentSection) {
        sections.push(currentSection);
      }
      currentSection = {
        heading: line.replace(/^##\s+/, "").trim(),
        blocks: [],
      };
      continue;
    }
    if (!currentSection) {
      currentSection = {
        heading: "开题摘要",
        blocks: [],
      };
    }
    blockBuffer.push(line);
  }

  flushBlock();
  if (currentSection) {
    sections.push(currentSection);
  }

  return { title, sections };
}

function formatSectionIndex(index: number) {
  return String(index + 1).padStart(2, "0");
}

function sanitizeDownloadFilename(value: string) {
  return String(value || "")
    .replace(/[\\/:*?"<>|]+/g, "-")
    .replace(/\s+/g, " ")
    .trim();
}

function artifactPathFromBundle(bundle: WorkspaceBundle | null, artifactName: DownloadArtifact) {
  if (!bundle?.deliverable_bundle) return "";
  const artifactMap: Record<DownloadArtifact, string> = {
    report_md: bundle.deliverable_bundle.report_markdown_path,
    report_docx: bundle.deliverable_bundle.report_docx_path,
    deck_pptx: bundle.deliverable_bundle.deck_pptx_path,
    notes_docx: bundle.deliverable_bundle.notes_docx_path,
    snapshot: bundle.deliverable_bundle.snapshot_path,
  };
  return artifactMap[artifactName] || "";
}

function preferredArtifactFilename(bundle: WorkspaceBundle | null, artifactName: DownloadArtifact, fallbackTitle: string) {
  const path = artifactPathFromBundle(bundle, artifactName);
  const fromPath = path.split("/").pop() || "";
  if (fromPath) return fromPath;

  const safeTitle = sanitizeDownloadFilename(fallbackTitle || "开题材料") || "开题材料";
  const fallbackMap: Record<DownloadArtifact, string> = {
    report_md: `${safeTitle}-report.md`,
    report_docx: `${safeTitle}-开题报告.docx`,
    deck_pptx: `${safeTitle}-答辩稿.pptx`,
    notes_docx: `${safeTitle}-讲稿.docx`,
    snapshot: `${safeTitle}-snapshot.json`,
  };
  return fallbackMap[artifactName];
}

export function WorkspaceApp() {
  const [profiles, setProfiles] = useState<ProfileOption[]>([]);
  const [workspaces, setWorkspaces] = useState<WorkspaceSummary[]>([]);
  const [bundle, setBundle] = useState<WorkspaceBundle | null>(null);
  const [workspaceName, setWorkspaceName] = useState("我的研策开题项目");
  const [profileId, setProfileId] = useState("whu");
  const [fieldDraft, setFieldDraft] = useState<Record<string, string>>({});
  const [interviewDraft, setInterviewDraft] = useState<Record<string, string>>({});
  const [linkDraft, setLinkDraft] = useState("");
  const [reportPreview, setReportPreview] = useState("");
  const [reportTitle, setReportTitle] = useState("");
  const [message, setMessage] = useState("先创建一个研策项目");
  const [error, setError] = useState("");
  const [deletingWorkspaceId, setDeletingWorkspaceId] = useState<string | null>(null);
  const [deletingFileId, setDeletingFileId] = useState<string | null>(null);
  const [runningAction, setRunningAction] = useState<WorkspaceAction | null>(null);
  const [isSelectingTitle, setIsSelectingTitle] = useState(false);
  const [isAdvancingToTitles, setIsAdvancingToTitles] = useState(false);
  const [isExportMenuOpen, setIsExportMenuOpen] = useState(false);
  const [exportingFormat, setExportingFormat] = useState<ExportFormat | null>(null);
  const [activeSection, setActiveSection] = useState<WorkspaceSection>("background");
  const exportMenuRef = useRef<HTMLDivElement | null>(null);

  const selectedTitle = bundle?.title_candidates.find((item) => item.selected);
  const uploadedLocalFiles = bundle?.evidence_items.filter((item) => item.evidence_type === "local_file") || [];
  const profileNameById = Object.fromEntries(
    profiles.map((profile) => [profile.id, profile.name]),
  ) as Record<string, string>;
  const hasDraftPrimaryFields = coreFieldKeys.every((key) => (fieldDraft[key] || bundle?.current_fields[key] || "").trim());
  const canAccessTitles = Boolean(bundle) && hasDraftPrimaryFields;
  const canAccessProposal = Boolean(bundle) && hasDraftPrimaryFields && Boolean(selectedTitle);
  const displayReportTitle =
    reportTitle ||
    extractReportTitleFromPath(bundle?.deliverable_bundle?.report_docx_path) ||
    extractReportTitleFromPath(bundle?.deliverable_bundle?.report_markdown_path) ||
    privacySafeReportTitle(
      selectedTitle?.title || "",
      bundle?.current_fields.company_name || fieldDraft.company_name || "",
      bundle?.current_fields.confidentiality_notes || fieldDraft.confidentiality_notes || "",
    ) ||
      "先在推荐选题里选定一个题目";

  useEffect(() => {
    const handlePointerDown = (event: MouseEvent) => {
      if (exportMenuRef.current && !exportMenuRef.current.contains(event.target as Node)) {
        setIsExportMenuOpen(false);
      }
    };
    document.addEventListener("mousedown", handlePointerDown);
    return () => document.removeEventListener("mousedown", handlePointerDown);
  }, []);

  function applyActionResponse(result: ActionResponse) {
    if (result.workspace) {
      setBundle(result.workspace);
    }
    if (result.report?.report_markdown) {
      setReportPreview(result.report.report_markdown);
    }
    if (result.report?.report_title) {
      setReportTitle(result.report.report_title);
    }
    if (result.deliverables?.report?.report_markdown) {
      setReportPreview(result.deliverables.report.report_markdown);
    }
    if (result.deliverables?.report?.report_title) {
      setReportTitle(result.deliverables.report.report_title);
    }
  }

  async function downloadArtifact(workspaceId: string, artifactName: DownloadArtifact, filename: string) {
    const response = await fetch(`${API_BASE}/api/workspaces/${workspaceId}/download/${artifactName}`);
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.detail || "下载失败");
    }
    const blob = await response.blob();
    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
  }

  const loadWorkspace = useCallback(async (workspaceId: string) => {
    try {
      setError("");
      const data = await apiFetch<WorkspaceBundle>(`/api/workspaces/${workspaceId}`);
      const selectedTitleCandidate = data.title_candidates.find((item) => item.selected);
      let storedReportPreview = "";
      const nextReportTitle =
        extractReportTitleFromPath(data.deliverable_bundle?.report_docx_path) ||
        extractReportTitleFromPath(data.deliverable_bundle?.report_markdown_path);
      if (data.deliverable_bundle?.report_markdown_path) {
        try {
          storedReportPreview = await fetchArtifactText(data.workspace.id, "report_md");
        } catch {
          storedReportPreview = "";
        }
      }

      setBundle(data);
      const nextDraft: Record<string, string> = {};
      editableKeys.forEach(([key]) => {
        nextDraft[key] = sanitizedDraftValue(key, data.current_fields[key] || "");
      });
      setFieldDraft(nextDraft);
      setInterviewDraft(data.interview_session?.answers || {});
      setReportPreview(storedReportPreview);
      setReportTitle(nextReportTitle);
      setIsExportMenuOpen(false);
      setActiveSection(
        normalizeSection(getNextStepInfo(data, data.title_candidates.find((item) => item.selected), storedReportPreview).section),
      );
      setMessage(
        selectedTitleCandidate && !storedReportPreview && !data.deliverable_bundle
          ? `已加载 ${data.workspace.name}，正在后台恢复开题报告。`
          : `已加载 ${data.workspace.name}，可以继续按当前建议推进。`,
      );

      if (selectedTitleCandidate && !storedReportPreview && !data.deliverable_bundle) {
        void (async () => {
          try {
            setRunningAction("generate-report");
            const generated = await apiFetch<ActionResponse>(`/api/workspaces/${data.workspace.id}/report/generate`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({}),
            });
            applyActionResponse(generated);
            setMessage(`已加载 ${data.workspace.name}，并自动恢复开题报告。`);
          } catch (fetchError) {
            setError(`已加载 ${data.workspace.name}，但开题报告未恢复：${toErrorMessage(fetchError)}`);
            setMessage(`已加载 ${data.workspace.name}。`);
          } finally {
            setRunningAction((current) => (current === "generate-report" ? null : current));
          }
        })();
      }
    } catch (fetchError) {
      setError(fetchError instanceof Error ? fetchError.message : "加载工作区失败");
    }
  }, []);

  useEffect(() => {
    void (async () => {
      try {
        const [profileData, workspaceData] = await Promise.all([
          apiFetch<ProfileOption[]>("/api/profiles"),
          apiFetch<WorkspaceSummary[]>("/api/workspaces"),
        ]);
        setProfiles(profileData);
        setWorkspaces(workspaceData);
        if (profileData[0]) {
          setProfileId(profileData[0].id);
        }
        if (workspaceData[0]) {
          await loadWorkspace(workspaceData[0].id);
        }
      } catch (fetchError) {
        setError(fetchError instanceof Error ? fetchError.message : "初始化失败");
      }
    })();
  }, [loadWorkspace]);

  async function createWorkspace(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      setError("");
      const data = await apiFetch<WorkspaceBundle>("/api/workspaces", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: workspaceName, school_profile: profileId }),
      });
      setWorkspaces((current) => [data.workspace, ...current]);
      setBundle(data);
      setMessage("项目已创建。先补真实问题和可用材料，再让研策开始收敛题目。");
      const nextDraft: Record<string, string> = {};
      editableKeys.forEach(([key]) => {
        nextDraft[key] = sanitizedDraftValue(key, data.current_fields[key] || "");
      });
      setFieldDraft(nextDraft);
      setInterviewDraft({});
      setReportPreview("");
      setReportTitle("");
      setIsExportMenuOpen(false);
      setActiveSection("background");
    } catch (fetchError) {
      setError(fetchError instanceof Error ? fetchError.message : "创建工作区失败");
    }
  }

  async function persistFields() {
    if (!bundle) return false;
    try {
      setError("");
      const values = editableKeys.map(([key]) => ({ key, value: fieldDraft[key] || "", confirmed: true }));
      const data = await apiFetch<WorkspaceBundle>(`/api/workspaces/${bundle.workspace.id}/fields`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ values }),
      });
      setBundle(data);
      const importedLinks = await importPendingLinks(data.workspace.id);
      setMessage(
        importedLinks
          ? "基本信息已保存，补充链接也已纳入后续选题参考。"
          : "基本信息已保存，研策会自动补全学校、导师和单位的公开信息。",
      );
      return true;
    } catch (fetchError) {
      setError(fetchError instanceof Error ? fetchError.message : "保存字段失败");
      return false;
    }
  }

  async function goToTitleRecommendation() {
    if (!hasDraftPrimaryFields) {
      setError("请先补全学校名称、导师姓名、学生姓名和学号，再进入推荐选题。");
      return;
    }
    try {
      setIsAdvancingToTitles(true);
      const saved = await persistFields();
      if (!saved) return;
      await runAction("recommend");
    } finally {
      setIsAdvancingToTitles(false);
    }
  }

  async function uploadFiles(fileList: FileList | null) {
    if (!bundle || !fileList?.length) return;
    try {
      setError("");
      const formData = new FormData();
      Array.from(fileList).forEach((file) => formData.append("files", file));
      const result = await apiFetch<{ workspace: WorkspaceBundle }>(
        `/api/workspaces/${bundle.workspace.id}/files/upload`,
        {
          method: "POST",
          body: formData,
        },
      );
      setBundle(result.workspace);
      setMessage(`已上传 ${fileList.length} 个文件，资料会自动归档并作为后续选题参考。`);
    } catch (fetchError) {
      setError(fetchError instanceof Error ? fetchError.message : "上传失败");
    }
  }

  async function deleteUploadedFile(evidenceId: string, title: string) {
    if (!bundle) return;
    const accepted = window.confirm(`确认删除“${title}”？删除后该文件将不再参与后续推荐选题和开题生成。`);
    if (!accepted) return;
    try {
      setError("");
      setDeletingFileId(evidenceId);
      const result = await apiFetch<DeleteUploadedFileResponse>(
        `/api/workspaces/${bundle.workspace.id}/files/${evidenceId}`,
        { method: "DELETE" },
      );
      setBundle(result.workspace);
      setMessage(`已删除 ${result.title}。`);
    } catch (fetchError) {
      setError(fetchError instanceof Error ? fetchError.message : "删除文件失败");
    } finally {
      setDeletingFileId(null);
    }
  }

  async function importPendingLinks(workspaceId: string) {
    const urls = linkDraft
      .split(/\n+/)
      .map((item) => item.trim())
      .filter(Boolean);
    const uniqueUrls = Array.from(new Set(urls));
    if (!uniqueUrls.length) return false;
    try {
      const result = await apiFetch<{ workspace: WorkspaceBundle }>(`/api/workspaces/${workspaceId}/links/import`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ urls: uniqueUrls }),
      });
      setBundle(result.workspace);
      setLinkDraft("");
      return true;
    } catch (fetchError) {
      throw new Error(fetchError instanceof Error ? fetchError.message : "导入链接失败");
    }
  }

  async function removeWorkspace(workspaceId: string, workspaceName: string) {
    const accepted = window.confirm(
      `确认删除“${workspaceName}”？这会同时删除该项目的资料、快照和导出文件，且无法恢复。`,
    );
    if (!accepted) return;
    try {
      setError("");
      setDeletingWorkspaceId(workspaceId);
      const result = await apiFetch<DeleteWorkspaceResponse>(`/api/workspaces/${workspaceId}`, {
        method: "DELETE",
      });
      const remaining = workspaces.filter((workspace) => workspace.id !== workspaceId);
      setWorkspaces(remaining);
      if (bundle?.workspace.id === workspaceId) {
        if (remaining[0]) {
          await loadWorkspace(remaining[0].id);
        } else {
          setBundle(null);
          setFieldDraft({});
          setInterviewDraft({});
          setReportPreview("");
          setReportTitle("");
          setIsExportMenuOpen(false);
          setMessage(`已删除 ${result.name}，当前没有工作区。`);
        }
      } else {
        setMessage(`已删除 ${result.name}。`);
      }
    } catch (fetchError) {
      setError(fetchError instanceof Error ? fetchError.message : "删除工作区失败");
    } finally {
      setDeletingWorkspaceId(null);
    }
  }

  async function runAction(action: WorkspaceAction) {
    if (!bundle) return;
    const actionMap: Record<WorkspaceAction, string> = {
      interview: `/api/workspaces/${bundle.workspace.id}/interview/generate`,
      recommend: `/api/workspaces/${bundle.workspace.id}/titles/recommend`,
      "generate-report": `/api/workspaces/${bundle.workspace.id}/report/generate`,
      "freeze-deliverables": `/api/workspaces/${bundle.workspace.id}/deliverables/freeze`,
    };
    try {
      setError("");
      setRunningAction(action);
      if (action === "interview" || action === "recommend") {
        await importPendingLinks(bundle.workspace.id);
      }
      const result = await apiFetch<ActionResponse>(actionMap[action], {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body:
          action === "generate-report" || action === "freeze-deliverables"
            ? JSON.stringify({})
            : undefined,
      });
      applyActionResponse(result);
      const nextSections: Record<WorkspaceAction, WorkspaceSection> = {
        interview: "titles",
        recommend: "titles",
        "generate-report": "proposal",
        "freeze-deliverables": "proposal",
      };
      setActiveSection(normalizeSection(nextSections[action]));
      const messages: Record<WorkspaceAction, string> = {
        interview: "访谈问题已生成。回答越具体，题目越不会虚。",
        recommend: "候选题已生成，直接比较后选定一个题目即可。",
        "generate-report": "正文草稿已生成。先读逻辑和引用，不要急着导出。",
        "freeze-deliverables": "冻结版导出已生成。现在可以直接下载。",
      };
      setMessage(messages[action]);
    } catch (fetchError) {
      setError(fetchError instanceof Error ? fetchError.message : "执行动作失败");
    } finally {
      setRunningAction(null);
    }
  }

  async function exportDeliverable(format: ExportFormat) {
    if (!bundle || !selectedTitle) return;
    const workspaceId = bundle.workspace.id;
    const artifactName: Record<ExportFormat, DownloadArtifact> = {
      word: "report_docx",
      ppt: "deck_pptx",
    };
    const formatLabel: Record<ExportFormat, string> = {
      word: "Word",
      ppt: "PPT",
    };
    try {
      setError("");
      setIsExportMenuOpen(false);
      setExportingFormat(format);
      let nextBundle: WorkspaceBundle | null = bundle;
      if (!bundle.deliverable_bundle) {
        setRunningAction("freeze-deliverables");
        const result = await apiFetch<ActionResponse>(`/api/workspaces/${workspaceId}/deliverables/freeze`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({}),
        });
        applyActionResponse(result);
        nextBundle = result.workspace || bundle;
      }
      await downloadArtifact(
        workspaceId,
        artifactName[format],
        preferredArtifactFilename(nextBundle, artifactName[format], displayReportTitle),
      );
      setMessage(`${formatLabel[format]} 导出已开始。`);
    } catch (fetchError) {
      setError(fetchError instanceof Error ? fetchError.message : `${formatLabel[format]} 导出失败`);
    } finally {
      setRunningAction((current) => (current === "freeze-deliverables" ? null : current));
      setExportingFormat(null);
    }
  }

  async function submitInterviewAnswers() {
    if (!bundle || !bundle.interview_session) return;
    try {
      setError("");
      await importPendingLinks(bundle.workspace.id);
      const result = await apiFetch<{ workspace: WorkspaceBundle }>(
        `/api/workspaces/${bundle.workspace.id}/interview/answer`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ answers: interviewDraft }),
        },
      );
      setBundle(result.workspace);
      await runAction("recommend");
    } catch (fetchError) {
      setError(fetchError instanceof Error ? fetchError.message : "提交访谈失败");
    }
  }

  async function selectTitle(titleId: string) {
    if (!bundle || isSelectingTitle) return;
    let selectionApplied = false;
    try {
      setError("");
      setIsSelectingTitle(true);
      setIsExportMenuOpen(false);
      const data = await apiFetch<WorkspaceBundle>(`/api/workspaces/${bundle.workspace.id}/titles/select`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title_id: titleId }),
      });
      selectionApplied = true;
      setBundle(data);
      setReportPreview("");
      setReportTitle("");
      setActiveSection("proposal");
      setRunningAction("generate-report");
      const result = await apiFetch<ActionResponse>(`/api/workspaces/${data.workspace.id}/report/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      applyActionResponse(result);
      setActiveSection("proposal");
      setMessage("题目已选定，开题报告已按当前资料自动生成。");
    } catch (fetchError) {
      const fallbackMessage = fetchError instanceof Error ? fetchError.message : "冻结题目失败";
      if (selectionApplied) {
        setError(`题目已选定，但报告生成失败：${fallbackMessage}`);
        setMessage("题目已选定，但报告还没有成功生成。你可以在报告区重新生成。");
      } else {
        setError(fallbackMessage);
      }
    } finally {
      setRunningAction((current) => (current === "generate-report" ? null : current));
      setIsSelectingTitle(false);
    }
  }

  return (
    <main className="relative min-h-screen overflow-hidden px-4 py-4 md:px-6 md:py-6">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_12%_12%,rgba(240,133,52,0.14),transparent_18%),radial-gradient(circle_at_85%_18%,rgba(118,167,208,0.12),transparent_24%),linear-gradient(180deg,rgba(8,18,30,0.18),transparent_36%)]" />
      <div className="pointer-events-none absolute inset-x-0 top-0 h-[24rem] bg-[linear-gradient(180deg,rgba(14,30,47,0.92),rgba(14,30,47,0.08))]" />

      <div className="relative mx-auto max-w-[1760px]">
        <header className="reveal overflow-hidden rounded-[40px] border border-[var(--line-strong)] bg-[linear-gradient(145deg,rgba(12,26,42,0.98),rgba(22,44,66,0.88))] px-5 py-5 text-[var(--canvas)] shadow-[var(--shadow-strong)] md:px-8 md:py-6 xl:px-10 xl:py-7">
          <div className="studio-glow pointer-events-none absolute inset-0" />
          <div className="relative flex items-center gap-5 md:gap-6">
            <HeroLogo />
            <div className="min-w-0">
              <div className="flex flex-wrap items-end gap-x-4 gap-y-2">
                <h1 className="font-serif text-[2.2rem] leading-none tracking-[-0.04em] text-[var(--canvas)] md:text-[2.8rem]">
                  {BRAND.enName}
                </h1>
                <p className="pb-1 font-serif text-[1.7rem] leading-none tracking-[-0.03em] text-[rgba(244,239,230,0.9)] md:text-[2.1rem]">
                  {BRAND.zhName}
                </p>
              </div>
              <p className="mt-3 text-[1rem] leading-7 text-[rgba(244,239,230,0.82)] md:text-[1.15rem]">
                {BRAND.zhPosition}
              </p>
              <p className="mt-3 text-[11px] uppercase tracking-[0.36em] text-[rgba(244,239,230,0.54)]">
                {BRAND.enPosition}
              </p>
            </div>
          </div>
        </header>

        <div className="mt-6 grid gap-6 xl:grid-cols-[320px_minmax(0,1fr)]">
          <aside className="reveal space-y-6 xl:sticky xl:top-5 xl:self-start">
            <RailPanel eyebrow="入口" title="创建项目">
              <form onSubmit={createWorkspace} className="space-y-4">
                <label className="grid gap-2">
                  <span className="text-xs uppercase tracking-[0.22em] text-[var(--ink-soft)]">项目名称</span>
                  <input
                    value={workspaceName}
                    onChange={(event) => setWorkspaceName(event.target.value)}
                    placeholder="例如：智能体选题优化"
                    className="rounded-[18px] border border-[rgba(19,33,51,0.12)] bg-[rgba(255,255,255,0.72)] px-4 py-3 text-sm text-[var(--foreground)] outline-none transition focus:border-[rgba(240,133,52,0.42)]"
                  />
                </label>
                <label className="grid gap-2">
                  <span className="text-xs uppercase tracking-[0.22em] text-[var(--ink-soft)]">学校</span>
                  <div className="relative">
                    <select
                      value={profileId}
                      onChange={(event) => setProfileId(event.target.value)}
                      className="w-full appearance-none rounded-[18px] border border-[rgba(19,33,51,0.12)] bg-[rgba(255,255,255,0.72)] px-4 py-3 pr-12 text-sm text-[var(--foreground)] outline-none transition focus:border-[rgba(240,133,52,0.42)]"
                    >
                      {profiles.map((profile) => (
                        <option key={profile.id} value={profile.id} className="text-slate-900">
                          {profile.name}
                        </option>
                      ))}
                    </select>
                    <span className="pointer-events-none absolute inset-y-0 right-4 flex items-center justify-center text-[rgba(19,33,51,0.72)]">
                      <span className="h-2.5 w-2.5 rotate-45 border-b-[1.5px] border-r-[1.5px] border-current" />
                    </span>
                  </div>
                </label>
                <button
                  type="submit"
                  className="inline-flex w-full items-center justify-center rounded-full bg-[var(--accent)] px-4 py-3 text-sm font-semibold text-[var(--canvas)] transition hover:bg-[var(--accent-strong)]"
                >
                  开始一个新项目
                </button>
              </form>
            </RailPanel>

            <RailPanel eyebrow="项目" title="项目列表">
              <div className="space-y-2">
                {workspaces.length ? (
                  workspaces.map((workspace) => (
                    <div
                      key={workspace.id}
                      role="button"
                      tabIndex={0}
                      onClick={() => void loadWorkspace(workspace.id)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          void loadWorkspace(workspace.id);
                        }
                      }}
                      className={`flex cursor-pointer items-center gap-3 rounded-[18px] px-3 py-3 transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[rgba(240,133,52,0.4)] ${
                        bundle?.workspace.id === workspace.id
                          ? "bg-[rgba(240,133,52,0.1)]"
                          : "hover:bg-[rgba(17,30,46,0.04)]"
                      }`}
                    >
                      <div className="min-w-0 flex-1 rounded-[14px] px-1 py-1 text-left">
                        <span className="line-clamp-2 block text-sm leading-6 text-[var(--foreground)]">
                          {workspace.name}
                        </span>
                        <span className="mt-1 block text-[11px] uppercase tracking-[0.18em] text-[var(--accent)]">
                          {profileNameById[workspace.school_profile] || workspace.school_profile}
                        </span>
                      </div>
                      <button
                        type="button"
                        aria-label={`删除 ${workspace.name}`}
                        title={`删除 ${workspace.name}`}
                        disabled={deletingWorkspaceId === workspace.id}
                        onClick={(event) => {
                          event.stopPropagation();
                          void removeWorkspace(workspace.id, workspace.name);
                        }}
                        className="shrink-0 self-center rounded-full border border-[rgba(157,60,51,0.18)] bg-[rgba(157,60,51,0.08)] px-3 py-1.5 text-[11px] uppercase tracking-[0.12em] text-[var(--danger)] transition hover:bg-[rgba(157,60,51,0.14)] disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {deletingWorkspaceId === workspace.id ? "删除中" : "删除"}
                      </button>
                    </div>
                  ))
                ) : null}
              </div>
            </RailPanel>
          </aside>

          <section className="reveal space-y-6">
            <p className="sr-only" aria-live="polite">
              {error ? `错误：${error}` : message}
            </p>
            <nav className="grid gap-3 rounded-[32px] border border-[var(--line-strong)] bg-[rgba(248,242,234,0.86)] p-3 shadow-[var(--shadow-soft)] md:grid-cols-3">
              {(["background", "titles", "proposal"] as WorkspaceSection[]).map((section) => (
                <WorkspaceNavButton
                  key={section}
                  active={normalizeSection(activeSection) === section}
                  label={sectionMeta[section].label}
                  hint={sectionMeta[section].body}
                  disabled={
                    !bundle ||
                    (section === "titles" && !canAccessTitles) ||
                    (section === "proposal" && !canAccessProposal)
                  }
                  onClick={() => setActiveSection(section)}
                />
              ))}
            </nav>

            {error ? (
              <StatusBanner tone="danger" text={error} />
            ) : message ? (
              <StatusBanner tone="muted" text={message} />
            ) : null}

            {bundle ? (
              <>
                {normalizeSection(activeSection) === "background" ? (
                  <PaperSection eyebrow="基础信息" title="先填导师侧、学生侧和上传资料" hideHeader>
                    <div className="space-y-6">
                      <div className="rounded-[26px] border border-[var(--line)] bg-[rgba(255,255,255,0.72)] p-5">
                        <SectionLead
                          title="导师信息"
                          body="学校名称和导师姓名是起点。系统会基于它们自动联网搜索学校写作要求和导师研究方向。"
                          compact
                        />
                        <div className="mt-4 grid gap-4 md:grid-cols-2">
                          {mentorEditableKeys.map(([key, label, placeholder, mode]) => (
                            <FieldEditor
                              key={key}
                              label={label}
                              value={fieldDraft[key] || ""}
                              placeholder={placeholder}
                              multiline={mode === "multi"}
                              required
                              onChange={(value) =>
                                setFieldDraft((current) => ({
                                  ...current,
                                  [key]: value,
                                }))
                              }
                            />
                          ))}
                        </div>
                      </div>

                      <div className="rounded-[26px] border border-[var(--line)] bg-[rgba(255,255,255,0.72)] p-5">
                        <SectionLead
                          title="学生信息"
                          body="学生姓名和学号会进入最终导出材料，也用于项目归档。"
                          compact
                        />
                        <div className="mt-4 grid gap-4 md:grid-cols-2">
                          {studentEditableKeys.map(([key, label, placeholder, mode]) => (
                            <FieldEditor
                              key={key}
                              label={label}
                              value={fieldDraft[key] || ""}
                              placeholder={placeholder}
                              multiline={mode === "multi"}
                              required
                              onChange={(value) =>
                                setFieldDraft((current) => ({
                                  ...current,
                                  [key]: value,
                                }))
                              }
                            />
                          ))}
                        </div>
                      </div>

                      <div className="rounded-[26px] border border-[var(--line)] bg-[rgba(255,255,255,0.72)] p-5">
                        <SectionLead
                          title="补充信息"
                          body="这些信息不是必填，但会让推荐题目更贴近你的工作场景。"
                          compact
                        />
                        <div className="mt-4 grid gap-4 md:grid-cols-2">
                          {optionalEditableKeys.map(([key, label, placeholder, mode]) => (
                            <FieldEditor
                              key={key}
                              label={label}
                              value={fieldDraft[key] || ""}
                              placeholder={placeholder}
                              multiline={mode === "multi"}
                              onChange={(value) =>
                                setFieldDraft((current) => ({
                                  ...current,
                                  [key]: value,
                                }))
                              }
                            />
                          ))}
                        </div>
                      </div>

                      <div className="rounded-[28px] border border-[var(--line)] bg-[linear-gradient(180deg,rgba(255,255,255,0.86),rgba(250,245,238,0.78))] p-5 md:p-6">
                        <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(320px,0.9fr)]">
                          <div className="h-full">
                            <UploadStage
                              title="参考资料"
                              body="上传写作要求、内部材料和项目资料，后续选题和开题生成会优先参考。"
                              hint="支持 md、txt、doc、docx、ppt、pptx、pdf"
                              accept=".md,.txt,.doc,.docx,.ppt,.pptx,.pdf,image/*"
                              onChange={(files) => void uploadFiles(files)}
                              files={uploadedLocalFiles}
                              removingId={deletingFileId}
                              onRemove={(evidenceId, title) => void deleteUploadedFile(evidenceId, title)}
                            />
                          </div>

                          <div className="flex h-full flex-col rounded-[24px] border border-[var(--line)] bg-[rgba(255,255,255,0.74)] p-4 md:p-5">
                            <SectionLead
                              title="参考链接"
                              body="学校要求网页、导师主页、单位官网和项目介绍页都可以直接贴进来。每行一个链接，后续推荐选题会自动参考。"
                              compact
                            />
                            <textarea
                              rows={5}
                              value={linkDraft}
                              onChange={(event) => setLinkDraft(event.target.value)}
                              placeholder={"https://...\nhttps://..."}
                              className="mt-4 min-h-[220px] w-full flex-1 rounded-[20px] border border-[rgba(19,33,51,0.08)] bg-[rgba(255,255,255,0.86)] px-4 py-3 text-sm leading-7 text-[var(--foreground)] outline-none placeholder:text-[rgba(19,33,51,0.36)]"
                            />
                          </div>
                        </div>
                        <div className="mt-6 flex justify-end">
                          <div className="w-full sm:w-[220px]">
                            <PrimaryButton
                              onClick={() => void goToTitleRecommendation()}
                              disabled={!bundle || !hasDraftPrimaryFields || isAdvancingToTitles || runningAction === "recommend"}
                            >
                              {isAdvancingToTitles || runningAction === "recommend" ? "正在生成候选题" : "下一步"}
                            </PrimaryButton>
                          </div>
                        </div>
                      </div>
                    </div>

                  </PaperSection>
                ) : null}

                {normalizeSection(activeSection) === "titles" ? (
                  <PaperSection eyebrow="推荐选题" title="比较候选题并确定一个题目" showDivider={false}>
                    <div className="space-y-6">
                      {bundle?.interview_session ? (
                        <div className="rounded-[26px] border border-[var(--line)] bg-[rgba(255,248,240,0.72)] p-5">
                          <div className="flex items-center justify-between gap-3">
                            <SectionLead
                              title="补充访谈"
                              body="如果上一轮候选题还不够准，就把这些关键问题回答具体，系统会自动重算候选题。"
                              compact
                            />
                            <TonePill tone={bundle.interview_session.status === "completed" ? "success" : "warning"}>
                              {bundle.interview_session.status === "completed" ? "已完成" : "待回答"}
                            </TonePill>
                          </div>
                          <ul className="mt-4 space-y-3 text-sm leading-7 text-[var(--ink-soft)]">
                            {bundle.interview_session.trigger_reasons.map((reason) => (
                              <li key={reason} className="flex gap-3">
                                <span className="mt-[9px] h-1.5 w-1.5 rounded-full bg-[var(--accent)]" />
                                <span>{prettifyCopy(reason)}</span>
                              </li>
                            ))}
                          </ul>

                          <div className="mt-5 space-y-5">
                            {bundle.interview_session.questions.map((question) => (
                              <label key={question.key} className="grid gap-2">
                                <span className="text-sm font-medium text-[var(--foreground)]">{question.question}</span>
                                <textarea
                                  rows={3}
                                  value={interviewDraft[question.key] || ""}
                                  onChange={(event) =>
                                    setInterviewDraft((current) => ({
                                      ...current,
                                      [question.key]: event.target.value,
                                    }))
                                  }
                                  placeholder={question.placeholder}
                                  className="min-h-[106px] rounded-[22px] border border-[var(--line)] bg-[rgba(255,253,249,0.82)] px-4 py-3 text-sm leading-7 outline-none transition focus:border-[var(--accent)]"
                                />
                              </label>
                            ))}
                          </div>
                          <div className="mt-5 flex justify-end">
                            <div className="w-full sm:w-[220px]">
                              <PrimaryButton
                                onClick={() => void submitInterviewAnswers()}
                                disabled={runningAction === "recommend"}
                              >
                                {runningAction === "recommend" ? "正在更新候选题" : "保存回答并更新候选题"}
                              </PrimaryButton>
                            </div>
                          </div>
                        </div>
                      ) : null}

                      {bundle?.title_candidates.length ? (
                        <div className="grid gap-4 xl:grid-cols-2">
                          {bundle.title_candidates.map((candidate) => (
                            <TitleBoardRow
                              key={candidate.id}
                              candidate={candidate}
                              disabled={isSelectingTitle || runningAction === "generate-report"}
                              onSelect={() => void selectTitle(candidate.id)}
                            />
                          ))}
                        </div>
                      ) : (
                        <MutedBlock
                          text={
                            runningAction === "recommend"
                              ? "正在根据当前填写的信息、资料和公开链接生成候选题，请稍候。"
                              : "当前还没有候选题，补充更多资料后重新生成即可。"
                          }
                          padded
                        />
                      )}
                    </div>
                  </PaperSection>
                ) : null}

                {normalizeSection(activeSection) === "proposal" ? (
                  <PaperSection
                    eyebrow="开题生成"
                    title=""
                    actions={
                      <ExportMenu
                        menuRef={exportMenuRef}
                        open={isExportMenuOpen}
                        disabled={!selectedTitle || isSelectingTitle || runningAction === "generate-report" || exportingFormat !== null}
                        isExporting={exportingFormat !== null || runningAction === "freeze-deliverables"}
                        onToggle={() => setIsExportMenuOpen((current) => !current)}
                        onExport={(format) => void exportDeliverable(format)}
                      />
                    }
                  >
                    <div className="overflow-hidden rounded-[30px] border border-[rgba(19,33,51,0.1)] bg-[linear-gradient(180deg,rgba(255,255,255,0.92),rgba(252,247,240,0.88))] shadow-[inset_0_1px_0_rgba(255,255,255,0.5)]">
                      {reportPreview ? (
                        <ReportDocument
                          markdown={reportPreview}
                          fallbackTitle={displayReportTitle}
                        />
                      ) : (
                        <div className="px-5 py-7 md:px-8 md:py-9">
                          <MutedBlock
                            text={
                              selectedTitle
                                ? runningAction === "generate-report"
                                  ? "正在整理开题报告正文，请稍候。"
                                  : "当前还没有可展示的开题报告。你可以重新生成一次，或先回到上一步更换题目。"
                                : "请先在推荐选题阶段选择一个题目，这里会直接展示生成后的开题报告。"
                            }
                            padded
                          />
                          {selectedTitle && runningAction !== "generate-report" ? (
                            <div className="mt-5 flex justify-end">
                              <button
                                type="button"
                                onClick={() => void runAction("generate-report")}
                                className="inline-flex items-center justify-center rounded-full border border-[rgba(19,33,51,0.12)] bg-[rgba(255,255,255,0.82)] px-4 py-2.5 text-sm font-medium text-[var(--foreground)] transition hover:border-[rgba(240,133,52,0.34)] hover:text-[var(--accent)]"
                              >
                                重新生成报告
                              </button>
                            </div>
                          ) : null}
                        </div>
                      )}
                    </div>
                  </PaperSection>
                ) : null}
              </>
            ) : (
              <div className="flex min-h-[420px] items-center justify-center px-6">
                <p className="text-center text-base leading-8 text-[var(--ink-soft)]">
                  还没有项目，先在左上角创建一个项目。
                </p>
              </div>
            )}
          </section>
        </div>
      </div>
    </main>
  );
}

function RailPanel({
  eyebrow,
  title,
  children,
}: {
  eyebrow: string;
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="rounded-[30px] border border-[var(--line-strong)] bg-[rgba(247,241,233,0.82)] p-4 shadow-[var(--shadow-soft)] backdrop-blur md:p-5">
      <p className="text-[10px] uppercase tracking-[0.28em] text-[var(--ink-soft)]">{eyebrow}</p>
      <h2 className="mt-2 font-serif text-[1.75rem] leading-tight text-[var(--foreground)]">{title}</h2>
      <div className="mt-4">{children}</div>
    </section>
  );
}

function PaperSection({
  eyebrow,
  title,
  children,
  hideHeader = false,
  showDivider = true,
  actions,
}: {
  eyebrow: string;
  title: string;
  children: ReactNode;
  hideHeader?: boolean;
  showDivider?: boolean;
  actions?: ReactNode;
}) {
  return (
    <section className="rounded-[34px] border border-[var(--line-strong)] bg-[var(--paper)] p-5 shadow-[var(--shadow-soft)] backdrop-blur md:p-6">
      {!hideHeader ? (
        <div className={`flex flex-wrap items-end justify-between gap-4 ${showDivider ? "border-b border-[rgba(19,33,51,0.08)] pb-4" : ""}`}>
          <div>
            <p className="text-[10px] uppercase tracking-[0.28em] text-[var(--ink-soft)]">{eyebrow}</p>
            {title ? <h2 className="mt-2 font-serif text-[2.15rem] leading-tight text-[var(--foreground)]">{title}</h2> : null}
          </div>
          {actions ? <div className="shrink-0">{actions}</div> : null}
        </div>
      ) : null}
      <div className={hideHeader ? undefined : showDivider ? "mt-6" : "mt-4"}>{children}</div>
    </section>
  );
}

function StatusBanner({
  tone,
  text,
}: {
  tone: "danger" | "muted";
  text: string;
}) {
  return (
    <div
      className={`rounded-[22px] border px-4 py-3 text-sm leading-7 whitespace-pre-line ${
        tone === "danger"
          ? "border-[rgba(157,60,51,0.18)] bg-[rgba(157,60,51,0.08)] text-[var(--danger)]"
          : "border-[rgba(19,33,51,0.08)] bg-[rgba(255,255,255,0.58)] text-[var(--ink-soft)]"
      }`}
    >
      {text}
    </div>
  );
}

function HeroLogo() {
  return (
    <div className="relative flex h-[72px] w-[72px] shrink-0 items-center justify-center rounded-full border border-[rgba(233,202,162,0.26)] bg-[radial-gradient(circle_at_34%_28%,rgba(250,235,210,0.14),rgba(22,44,70,0.96)_58%,rgba(8,20,34,1))] shadow-[0_0_0_8px_rgba(255,255,255,0.03),0_18px_36px_rgba(7,17,28,0.28)] md:h-[86px] md:w-[86px]">
      <div className="absolute inset-[5px] rounded-full border border-[rgba(236,209,173,0.22)] bg-[radial-gradient(circle_at_30%_28%,rgba(255,255,255,0.06),transparent_54%)] md:inset-[6px]" />
      <div className="absolute inset-[11px] rounded-full border border-[rgba(236,209,173,0.18)] shadow-[inset_0_0_0_1px_rgba(255,255,255,0.03)] md:inset-[13px]" />

      <div className="absolute top-[8px] h-[4px] w-[4px] rounded-full bg-[rgba(244,226,196,0.88)] md:top-[10px]" />
      <div className="absolute bottom-[8px] h-[4px] w-[4px] rounded-full bg-[rgba(244,226,196,0.72)] md:bottom-[10px]" />
      <div className="absolute left-[8px] h-[4px] w-[4px] rounded-full bg-[rgba(244,226,196,0.72)] md:left-[10px]" />
      <div className="absolute right-[8px] h-[4px] w-[4px] rounded-full bg-[rgba(244,226,196,0.72)] md:right-[10px]" />

      <div className="absolute left-[13px] flex flex-col gap-[3px] md:left-[16px] md:gap-[4px]">
        <span className="h-[7px] w-[4px] rounded-full bg-[linear-gradient(180deg,rgba(248,227,192,0.9),rgba(212,154,83,0.82))] rotate-[-34deg] md:h-[8px]" />
        <span className="ml-[2px] h-[7px] w-[4px] rounded-full bg-[linear-gradient(180deg,rgba(248,227,192,0.9),rgba(212,154,83,0.82))] rotate-[-18deg] md:h-[8px]" />
        <span className="ml-[3px] h-[7px] w-[4px] rounded-full bg-[linear-gradient(180deg,rgba(248,227,192,0.9),rgba(212,154,83,0.82))] rotate-[2deg] md:h-[8px]" />
        <span className="ml-[2px] h-[7px] w-[4px] rounded-full bg-[linear-gradient(180deg,rgba(248,227,192,0.9),rgba(212,154,83,0.82))] rotate-[18deg] md:h-[8px]" />
      </div>
      <div className="absolute right-[13px] flex flex-col gap-[3px] md:right-[16px] md:gap-[4px]">
        <span className="mr-[2px] h-[7px] w-[4px] rounded-full bg-[linear-gradient(180deg,rgba(248,227,192,0.9),rgba(212,154,83,0.82))] rotate-[34deg] md:h-[8px]" />
        <span className="h-[7px] w-[4px] rounded-full bg-[linear-gradient(180deg,rgba(248,227,192,0.9),rgba(212,154,83,0.82))] rotate-[18deg] md:h-[8px]" />
        <span className="mr-[1px] h-[7px] w-[4px] rounded-full bg-[linear-gradient(180deg,rgba(248,227,192,0.9),rgba(212,154,83,0.82))] rotate-[0deg] md:h-[8px]" />
        <span className="h-[7px] w-[4px] rounded-full bg-[linear-gradient(180deg,rgba(248,227,192,0.9),rgba(212,154,83,0.82))] rotate-[-18deg] md:h-[8px]" />
      </div>

      <div className="absolute inset-[21px] rounded-full bg-[radial-gradient(circle_at_50%_32%,rgba(252,238,214,0.14),rgba(17,35,56,0.88)_70%)] md:inset-[25px]" />
      <div className="absolute top-[18px] h-[10px] w-px bg-[linear-gradient(180deg,rgba(249,229,194,0.96),rgba(249,229,194,0))] md:top-[22px] md:h-[12px]" />
      <div className="absolute h-[30px] w-px bg-[linear-gradient(180deg,rgba(255,255,255,0.08),rgba(244,225,193,0.88),rgba(255,255,255,0.08))] md:h-[36px]" />
      <div className="absolute top-[22px] h-[5px] w-[5px] rounded-full bg-[rgba(248,229,197,0.96)] shadow-[0_0_10px_rgba(248,229,197,0.2)] md:top-[27px]" />

      <div className="absolute top-[33px] flex items-start gap-[2px] md:top-[39px]">
        <div className="h-[11px] w-[10px] rounded-bl-[9px] rounded-tl-[3px] rounded-tr-[7px] border border-[rgba(239,214,181,0.82)] bg-[linear-gradient(180deg,rgba(253,242,222,0.9),rgba(222,178,118,0.88))] md:h-[13px] md:w-[12px]" />
        <div className="h-[11px] w-[10px] rounded-br-[9px] rounded-tl-[7px] rounded-tr-[3px] border border-[rgba(239,214,181,0.82)] bg-[linear-gradient(180deg,rgba(253,242,222,0.9),rgba(222,178,118,0.88))] md:h-[13px] md:w-[12px]" />
      </div>
      <div className="absolute top-[34px] h-[12px] w-px bg-[rgba(18,37,58,0.9)] md:top-[40px] md:h-[14px]" />
      <div className="absolute bottom-[18px] h-px w-[20px] bg-[linear-gradient(90deg,rgba(255,255,255,0),rgba(240,214,182,0.76),rgba(255,255,255,0))] md:bottom-[22px] md:w-[24px]" />
    </div>
  );
}

function SectionLead({
  title,
  body,
  compact = false,
}: {
  title: string;
  body: string;
  compact?: boolean;
}) {
  return (
    <div>
      <h3 className={`font-serif text-[var(--foreground)] ${compact ? "text-2xl" : "text-[2rem] leading-tight"}`}>
        {title}
      </h3>
      <p className={`mt-2 text-[var(--ink-soft)] ${compact ? "text-sm leading-6" : "text-sm leading-7"}`}>{body}</p>
    </div>
  );
}

function FieldEditor({
  label,
  value,
  placeholder,
  multiline,
  required = false,
  onChange,
}: {
  label: string;
  value: string;
  placeholder: string;
  multiline: boolean;
  required?: boolean;
  onChange: (value: string) => void;
}) {
  return (
    <label className="grid gap-2 rounded-[24px] border border-[rgba(19,33,51,0.08)] bg-[rgba(255,255,255,0.72)] p-4 transition hover:border-[rgba(19,33,51,0.16)]">
      <span className="flex items-center gap-2 text-xs uppercase tracking-[0.24em] text-[var(--ink-soft)]">
        <span>{label}</span>
        {required ? <span className="text-[11px] tracking-normal text-[var(--danger)]">* 必填</span> : null}
      </span>
      {multiline ? (
        <textarea
          rows={4}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
          className="min-h-[126px] resize-y border-0 bg-transparent px-0 py-0 text-sm leading-7 text-[var(--foreground)] outline-none placeholder:text-[rgba(19,33,51,0.36)]"
        />
      ) : (
        <input
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
          className="border-0 bg-transparent px-0 py-1 text-sm leading-7 text-[var(--foreground)] outline-none placeholder:text-[rgba(19,33,51,0.36)]"
        />
      )}
    </label>
  );
}

function UploadStage({
  title,
  body,
  hint,
  accept,
  onChange,
  files,
  removingId,
  onRemove,
}: {
  title: string;
  body: string;
  hint: string;
  accept?: string;
  onChange: (files: FileList | null) => void;
  files: EvidenceItem[];
  removingId: string | null;
  onRemove: (evidenceId: string, title: string) => void;
}) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const dragDepthRef = useRef(0);
  const [isDragActive, setIsDragActive] = useState(false);

  const handleDragEnter = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    dragDepthRef.current += 1;
    setIsDragActive(true);
  };

  const handleDragLeave = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    dragDepthRef.current = Math.max(0, dragDepthRef.current - 1);
    if (dragDepthRef.current === 0) {
      setIsDragActive(false);
    }
  };

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    dragDepthRef.current = 0;
    setIsDragActive(false);
    onChange(event.dataTransfer.files);
  };

  return (
    <div
      onDragEnter={handleDragEnter}
      onDragOver={(event) => event.preventDefault()}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      className={`group relative flex h-full min-h-[320px] overflow-hidden rounded-[26px] border border-dashed bg-[linear-gradient(180deg,rgba(255,255,255,0.8),rgba(247,241,233,0.74))] p-4 md:p-5 transition ${
        isDragActive
          ? "border-[var(--accent)] shadow-[0_20px_40px_rgba(240,133,52,0.12)]"
          : "border-[rgba(19,33,51,0.18)] hover:border-[var(--accent)]"
      }`}
    >
      <div
        className={`pointer-events-none absolute inset-x-0 top-0 h-16 bg-[linear-gradient(180deg,rgba(240,133,52,0.08),transparent)] transition ${
          isDragActive ? "opacity-100" : "opacity-0 group-hover:opacity-100"
        }`}
      />
      <div className="relative flex h-full flex-1 flex-col">
        <p className="font-serif text-2xl text-[var(--foreground)]">{title}</p>
        <p className="mt-2 text-sm leading-7 text-[var(--ink-soft)]">{body}</p>
        <div className="mt-auto pt-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={() => inputRef.current?.click()}
                className="rounded-full bg-[rgba(240,133,52,0.1)] px-4 py-2 text-[11px] uppercase tracking-[0.2em] text-[var(--accent)] transition hover:bg-[rgba(240,133,52,0.16)]"
              >
                选择文件
              </button>
            </div>
            <span className="text-xs leading-6 text-[var(--ink-soft)]">{hint}</span>
          </div>
        </div>
        {files.length ? (
          <div className="mt-5 border-t border-[rgba(19,33,51,0.08)] pt-4">
            <div className="mb-3 flex items-center justify-between gap-3">
              <p className="text-xs uppercase tracking-[0.22em] text-[var(--ink-soft)]">已上传文件</p>
              <span className="text-xs text-[var(--ink-soft)]">{files.length} 个</span>
            </div>
            <div className="space-y-3">
              {files.map((file) => (
                <div
                  key={file.id}
                  className="flex items-center justify-between gap-3 rounded-[20px] border border-[rgba(19,33,51,0.08)] bg-[rgba(255,255,255,0.7)] px-4 py-3"
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-[var(--foreground)]">{file.title}</p>
                    <p className="mt-1 text-xs leading-6 text-[var(--ink-soft)]">
                      {file.source_label || "本地上传"}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => onRemove(file.id, file.title)}
                    disabled={removingId === file.id}
                    className="shrink-0 rounded-full border border-[rgba(157,60,51,0.18)] px-3 py-1.5 text-xs font-medium text-[var(--danger)] transition hover:bg-[rgba(157,60,51,0.06)] disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {removingId === file.id ? "删除中" : "删除"}
                  </button>
                </div>
              ))}
            </div>
          </div>
        ) : null}
      </div>
      <input
        ref={inputRef}
        type="file"
        multiple
        accept={accept}
        className="hidden"
        onChange={(event) => {
          onChange(event.target.files);
          event.currentTarget.value = "";
        }}
      />
    </div>
  );
}

function WorkspaceNavButton({
  active,
  label,
  hint,
  disabled = false,
  onClick,
}: {
  active: boolean;
  label: string;
  hint: string;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={`rounded-[24px] border px-4 py-4 text-left transition ${
        active
          ? "border-[rgba(240,133,52,0.38)] bg-[rgba(240,133,52,0.12)] shadow-[0_18px_36px_rgba(240,133,52,0.08)]"
          : "border-[rgba(19,33,51,0.08)] bg-[rgba(255,255,255,0.68)] hover:border-[rgba(19,33,51,0.16)]"
      } ${disabled ? "cursor-not-allowed opacity-55 hover:border-[rgba(19,33,51,0.08)]" : ""}`}
    >
      <p className="font-medium text-[var(--foreground)]">{label}</p>
      <p className="mt-2 text-sm leading-6 text-[var(--ink-soft)]">{hint}</p>
    </button>
  );
}

function TitleBoardRow({
  candidate,
  onSelect,
  disabled = false,
}: {
  candidate: TitleCandidate;
  onSelect: () => void;
  disabled?: boolean;
}) {
  return (
    <div
      className={`flex h-full w-full flex-col rounded-[24px] border px-4 py-4 text-left transition ${
        candidate.selected
          ? "border-[rgba(240,133,52,0.42)] bg-[rgba(240,133,52,0.1)] shadow-[0_18px_32px_rgba(240,133,52,0.08)]"
          : "border-[rgba(19,33,51,0.08)] bg-[rgba(255,255,255,0.7)] hover:border-[rgba(19,33,51,0.18)]"
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <p className="font-serif text-xl leading-8 text-[var(--foreground)]">{candidate.title}</p>
        <div
          className={`shrink-0 rounded-[20px] border px-3 py-2 text-right shadow-[inset_0_1px_0_rgba(255,255,255,0.42)] ${
            candidate.selected
              ? "border-[rgba(240,133,52,0.18)] bg-[linear-gradient(180deg,rgba(255,248,240,0.98),rgba(248,232,214,0.94))]"
              : "border-[rgba(19,33,51,0.08)] bg-[linear-gradient(180deg,rgba(255,255,255,0.98),rgba(245,240,232,0.92))]"
          }`}
        >
          <p className="font-mono text-2xl leading-none text-[var(--foreground)]">{candidate.total_score}</p>
          <p className="mt-2 inline-flex rounded-full bg-[rgba(240,133,52,0.12)] px-2 py-1 text-[10px] font-medium tracking-[0.18em] text-[var(--ink-soft)]">
            推荐度
          </p>
        </div>
      </div>
      {candidate.recommendation ? (
        <p className="mt-5 flex-1 text-base leading-8 text-[var(--foreground-soft)]">{prettifyCopy(candidate.recommendation)}</p>
      ) : null}
      <div className="mt-6">
        {candidate.selected ? (
          <button
            type="button"
            disabled
            className="inline-flex min-h-[58px] w-full cursor-default items-center justify-center rounded-[20px] border border-[rgba(37,109,82,0.18)] bg-[linear-gradient(180deg,rgba(37,109,82,0.16),rgba(37,109,82,0.1))] px-4 py-3 text-sm font-semibold text-[var(--success)] shadow-[inset_0_1px_0_rgba(255,255,255,0.24)]"
          >
            当前已选题目
          </button>
        ) : (
          <PrimaryButton onClick={onSelect} accent disabled={disabled}>
            {disabled ? "正在生成报告" : "选择这个题目"}
          </PrimaryButton>
        )}
      </div>
    </div>
  );
}

function TonePill({
  children,
  tone,
}: {
  children: ReactNode;
  tone: "success" | "warning" | "danger" | "muted";
}) {
  const styles: Record<typeof tone, string> = {
    success: "bg-[rgba(37,109,82,0.12)] text-[var(--success)]",
    warning: "bg-[rgba(153,93,29,0.12)] text-[var(--warning)]",
    danger: "bg-[rgba(157,60,51,0.12)] text-[var(--danger)]",
    muted: "bg-[rgba(19,33,51,0.08)] text-[var(--ink-soft)]",
  };
  return <span className={`rounded-full px-3 py-1 text-[10px] uppercase tracking-[0.2em] ${styles[tone]}`}>{children}</span>;
}

function PrimaryButton({
  children,
  onClick,
  disabled,
  accent = false,
}: {
  children: ReactNode;
  onClick: () => void;
  disabled?: boolean;
  accent?: boolean;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={`inline-flex w-full items-center justify-center rounded-full px-4 py-3 text-sm font-semibold transition active:scale-[0.985] ${
        accent
          ? "bg-[var(--accent)] text-[var(--canvas)] hover:bg-[var(--accent-strong)]"
          : "bg-[var(--foreground)] text-[var(--canvas)] hover:bg-[var(--foreground-soft)]"
      } disabled:cursor-not-allowed disabled:opacity-50`}
    >
      {children}
    </button>
  );
}

function ExportMenu({
  menuRef,
  open,
  disabled,
  isExporting,
  onToggle,
  onExport,
}: {
  menuRef: RefObject<HTMLDivElement | null>;
  open: boolean;
  disabled: boolean;
  isExporting: boolean;
  onToggle: () => void;
  onExport: (format: ExportFormat) => void;
}) {
  return (
    <div ref={menuRef} className="relative">
      <button
        type="button"
        disabled={disabled}
        onClick={onToggle}
        className="inline-flex min-h-[46px] items-center justify-center gap-2 rounded-full border border-[rgba(19,33,51,0.12)] bg-[rgba(255,255,255,0.88)] px-4 py-2.5 text-sm font-medium text-[var(--foreground)] transition hover:border-[rgba(240,133,52,0.38)] hover:text-[var(--accent)] disabled:cursor-not-allowed disabled:opacity-50"
      >
        <span>{isExporting ? "导出中" : "导出"}</span>
        <span className={`h-2.5 w-2.5 rotate-45 border-b-[1.5px] border-r-[1.5px] border-current transition ${open ? "translate-y-[-2px] rotate-[225deg]" : "translate-y-[-1px]"}`} />
      </button>
      {open ? (
        <div className="absolute right-0 top-[calc(100%+12px)] z-20 w-[248px] rounded-[24px] border border-[rgba(19,33,51,0.1)] bg-[rgba(255,251,246,0.98)] p-2 shadow-[0_28px_48px_rgba(7,17,28,0.14)] backdrop-blur">
          <button
            type="button"
            onClick={() => onExport("word")}
            className="flex w-full items-center justify-between gap-4 rounded-[18px] px-4 py-3 text-left transition hover:bg-[rgba(240,133,52,0.08)]"
          >
            <span className="block text-sm font-medium text-[var(--foreground)]">导出 Word</span>
            <span className="pt-1 text-[11px] uppercase tracking-[0.22em] text-[var(--ink-soft)]">.docx</span>
          </button>
          <div className="mx-3 border-t border-[rgba(19,33,51,0.08)]" />
          <button
            type="button"
            onClick={() => onExport("ppt")}
            className="mt-1 flex w-full items-center justify-between gap-4 rounded-[18px] px-4 py-3 text-left transition hover:bg-[rgba(240,133,52,0.08)]"
          >
            <span className="block text-sm font-medium text-[var(--foreground)]">导出 PPT</span>
            <span className="pt-1 text-[11px] uppercase tracking-[0.22em] text-[var(--ink-soft)]">.pptx</span>
          </button>
        </div>
      ) : null}
    </div>
  );
}

function ReportDocument({
  markdown,
  fallbackTitle,
}: {
  markdown: string;
  fallbackTitle: string;
}) {
  const report = parseReportMarkdown(markdown);
  const documentTitle = fallbackTitle || report.title.replace(/(?:》)?开题报告$/u, "").trim();

  return (
    <article className="relative overflow-hidden">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-28 bg-[linear-gradient(180deg,rgba(240,133,52,0.1),transparent)]" />
      <div className="relative mx-auto max-w-[980px] px-5 py-7 md:px-8 md:py-9 xl:px-12 xl:py-10">
        <div className="border-b border-[rgba(19,33,51,0.08)] pb-6">
          <h3 className="font-serif text-[1.95rem] leading-tight text-[var(--foreground)] md:text-[2.45rem]">
            {documentTitle}
          </h3>
        </div>

        <div className="mt-8 space-y-8">
          {report.sections.map((section, index) => (
            <section key={`${section.heading}-${index}`} className="grid gap-4 md:grid-cols-[68px_minmax(0,1fr)]">
              <div className="pt-1 font-mono text-xs uppercase tracking-[0.26em] text-[var(--ink-soft)]">
                {formatSectionIndex(index)}
              </div>
              <div className="space-y-4">
                <h4 className="font-serif text-[1.5rem] leading-tight text-[var(--foreground)] md:text-[1.85rem]">
                  {section.heading}
                </h4>
                <div className="space-y-4">
                  {section.blocks.map((block, blockIndex) => (
                    <ReportBlock key={`${section.heading}-${blockIndex}`} block={block} />
                  ))}
                </div>
              </div>
            </section>
          ))}
        </div>
      </div>
    </article>
  );
}

function ReportBlock({ block }: { block: string }) {
  const lines = block
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);

  if (!lines.length) return null;

  if (lines.every((line) => /^-\s+/.test(line))) {
    return (
      <ul className="space-y-3">
        {lines.map((line, index) => (
          <li key={`${line}-${index}`} className="flex gap-3 text-[15px] leading-8 text-[var(--foreground-soft)] md:text-base">
            <span className="mt-3 h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--accent)]" />
            <span>{line.replace(/^-\s+/, "")}</span>
          </li>
        ))}
      </ul>
    );
  }

  if (lines.every((line) => /^\d+\.\s+/.test(line))) {
    return (
      <ol className="space-y-3">
        {lines.map((line, index) => {
          const match = line.match(/^(\d+)\.\s+(.*)$/);
          return (
            <li
              key={`${line}-${index}`}
              className="grid grid-cols-[32px_minmax(0,1fr)] gap-3 text-[15px] leading-8 text-[var(--foreground-soft)] md:text-base"
            >
              <span className="font-mono text-[var(--accent)]">{match?.[1] || ""}.</span>
              <span>{match?.[2] || line}</span>
            </li>
          );
        })}
      </ol>
    );
  }

  return <p className="whitespace-pre-line text-[15px] leading-8 text-[var(--foreground-soft)] md:text-base">{block}</p>;
}

function MutedBlock({ text, padded = false }: { text: string; padded?: boolean }) {
  return (
    <div
      className={`rounded-[22px] border border-dashed border-[rgba(19,33,51,0.16)] bg-[rgba(255,255,255,0.42)] text-sm leading-7 text-[var(--ink-soft)] ${
        padded ? "px-4 py-5" : "px-3 py-4"
      }`}
    >
      {text}
    </div>
  );
}
