"use client";

import { type FormEvent, type ReactNode, useEffect, useState, useTransition } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";
const BRAND = {
  zhName: "研策",
  enName: "Yance",
  zhPosition: "专业学位论文开题智能参谋",
  enPosition: "Academic Proposal Strategist",
  slogan: "让开题更成体系",
} as const;

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
  report?: { report_markdown?: string };
  deliverables?: { report?: { report_markdown?: string } };
};

type DeleteWorkspaceResponse = {
  deleted: boolean;
  workspace_id: string;
  name: string;
};

type WorkspaceSection = "background" | "titles" | "proposal" | "materials";

const editableKeys = [
  ["student_name", "学生姓名", "例如：程闯", "single"],
  ["mentor_name", "导师姓名", "例如：庄子银", "single"],
  ["company_name", "单位名称", "例如：开目软件", "single"],
  ["role_title", "岗位名称", "例如：AI 产品负责人", "single"],
  ["work_scope", "代表性场景", "写最适合进入论文的一个业务、项目或流程场景。", "multi"],
  ["pain_point", "真实痛点", "不要写愿景，要写最具体、最难的管理问题。", "multi"],
  ["data_sources", "可用材料", "写明内部资料、访谈对象、流程文档、项目复盘等。", "multi"],
  ["research_goal", "预期成果", "这篇论文最终要形成什么改进结果或方案。", "multi"],
  ["confidentiality_notes", "保密边界", "例如：公司需化名、项目名称不便公开。", "multi"],
] as const;

const fieldLabels = Object.fromEntries(
  editableKeys.map(([key, label]) => [key, label]),
) as Record<string, string>;

const evidenceTypeLabels: Record<string, string> = {
  citation: "文献条目",
  local_file: "本地资料",
  web_page: "网页事实",
  web_search: "联网检索",
  interview: "访谈纪要",
  generated_outline: "结构草案",
};

const evidenceStatusLabels: Record<string, string> = {
  verified: "已核验",
  pending: "待核验",
  draft: "待补全",
  blocked: "已拦截",
};

const scoreLabels = ["学校", "导师", "岗位", "资料", "保密"] as const;
const coreFieldKeys = ["mentor_name", "company_name", "role_title", "pain_point", "data_sources"] as const;
const primaryEditableKeys = editableKeys.filter(([key]) => coreFieldKeys.includes(key as (typeof coreFieldKeys)[number]));
const optionalEditableKeys = editableKeys.filter(([key]) => !coreFieldKeys.includes(key as (typeof coreFieldKeys)[number]));
const sectionMeta: Record<
  WorkspaceSection,
  { label: string; title: string; body: string; short: string }
> = {
  background: {
    label: "项目背景",
    title: "项目背景",
    body: "先把导师、单位、岗位、真实痛点和可用材料说清楚，系统会自动补全公开信息。",
    short: "背景",
  },
  titles: {
    label: "推荐题目",
    title: "推荐题目",
    body: "必要时先补几个关键问题，再比较候选题，最后只冻结一个题目继续写。",
    short: "题目",
  },
  proposal: {
    label: "开题报告",
    title: "开题报告",
    body: "围绕已冻结题目查看结构、论证方向和报告草稿，确认后再进入答辩材料。",
    short: "报告",
  },
  materials: {
    label: "答辩材料",
    title: "答辩材料",
    body: "Word、PPT、讲稿和来源快照只从冻结版报告派生，避免口径漂移。",
    short: "材料",
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

function getEvidenceTypeLabel(value: string) {
  return evidenceTypeLabels[value] || value.replaceAll("_", " ");
}

function getEvidenceStatusLabel(value: string) {
  return evidenceStatusLabels[value] || value;
}

function getRiskPriorityLabel(priority: number) {
  if (priority >= 4) return "关键";
  if (priority >= 3) return "高";
  if (priority >= 2) return "中";
  return "低";
}

function getRiskTone(priority: number): "danger" | "warning" | "muted" {
  if (priority >= 4) return "danger";
  if (priority >= 2) return "warning";
  return "muted";
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
      title: "先补全基本信息",
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
      title: "生成开题报告草稿",
      body: "先看正文结构和论证方向，再决定要不要导出正式材料。",
      tone: "warning",
      section: "proposal",
    };
  }
  if (!bundle.deliverable_bundle) {
    return {
      title: "冻结并导出材料",
      body: "题目和草稿已经有了，下一步直接生成 Word、PPT 和讲稿。",
      tone: "warning",
      section: "materials",
    };
  }
  return {
    title: "检查并下载最终材料",
    body: "现在重点看题目、研究问题和讲稿口径是否一致，再下载导出件。",
    tone: "success",
    section: "materials",
  };
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || `请求失败: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function WorkspaceApp() {
  const [profiles, setProfiles] = useState<ProfileOption[]>([]);
  const [workspaces, setWorkspaces] = useState<WorkspaceSummary[]>([]);
  const [bundle, setBundle] = useState<WorkspaceBundle | null>(null);
  const [workspaceName, setWorkspaceName] = useState("我的研策开题项目");
  const [profileId, setProfileId] = useState("whu-emba");
  const [fieldDraft, setFieldDraft] = useState<Record<string, string>>({});
  const [interviewDraft, setInterviewDraft] = useState<Record<string, string>>({});
  const [reportPreview, setReportPreview] = useState("");
  const [message, setMessage] = useState("先创建一个研策项目");
  const [error, setError] = useState("");
  const [deletingWorkspaceId, setDeletingWorkspaceId] = useState<string | null>(null);
  const [activeSection, setActiveSection] = useState<WorkspaceSection>("background");
  const [isPending, startTransition] = useTransition();

  const selectedTitle = bundle?.title_candidates.find((item) => item.selected);
  const profileNameById = Object.fromEntries(
    profiles.map((profile) => [profile.id, profile.name]),
  ) as Record<string, string>;
  const nextStep = getNextStepInfo(bundle, selectedTitle, reportPreview);
  const filledFieldCount = editableKeys.filter(([key]) => (bundle?.current_fields[key] || "").trim()).length;
  const readyTitleCount = bundle?.title_candidates.length || 0;
  const hasExports = Boolean(bundle?.deliverable_bundle);
  const hasPrimaryFields = primaryEditableKeys.every(([key]) => (bundle?.current_fields[key] || "").trim());
  const activeSectionInfo = sectionMeta[activeSection];
  const topRisk = bundle?.risks[0];
  const statusText = error ? `错误：${error}` : message;

  const loadWorkspace = async (workspaceId: string) => {
    try {
      setError("");
      const data = await apiFetch<WorkspaceBundle>(`/api/workspaces/${workspaceId}`);
      setBundle(data);
      const nextDraft: Record<string, string> = {};
      editableKeys.forEach(([key]) => {
        nextDraft[key] = data.current_fields[key] || "";
      });
      setFieldDraft(nextDraft);
      setInterviewDraft(data.interview_session?.answers || {});
      setReportPreview("");
      setActiveSection(getNextStepInfo(data, data.title_candidates.find((item) => item.selected), "").section);
      setMessage(`已加载 ${data.workspace.name}，可以继续按当前建议推进。`);
    } catch (fetchError) {
      setError(fetchError instanceof Error ? fetchError.message : "加载工作区失败");
    }
  };

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
  }, []);

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
        nextDraft[key] = data.current_fields[key] || "";
      });
      setFieldDraft(nextDraft);
      setInterviewDraft({});
      setReportPreview("");
      setActiveSection("background");
    } catch (fetchError) {
      setError(fetchError instanceof Error ? fetchError.message : "创建工作区失败");
    }
  }

  async function persistFields() {
    if (!bundle) return;
    try {
      setError("");
      const values = editableKeys
        .map(([key]) => ({ key, value: fieldDraft[key] || "", confirmed: true }))
        .filter((item) => item.value.trim());
      const data = await apiFetch<WorkspaceBundle>(`/api/workspaces/${bundle.workspace.id}/fields`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ values }),
      });
      setBundle(data);
      setMessage("基本信息已保存，研策会自动补全学校、导师和单位的公开信息。");
    } catch (fetchError) {
      setError(fetchError instanceof Error ? fetchError.message : "保存字段失败");
    }
  }

  async function uploadFiles(target: "files" | "citations", fileList: FileList | null) {
    if (!bundle || !fileList?.length) return;
    try {
      setError("");
      const formData = new FormData();
      Array.from(fileList).forEach((file) => formData.append("files", file));
      const endpoint =
        target === "files"
          ? `/api/workspaces/${bundle.workspace.id}/files/upload`
          : `/api/workspaces/${bundle.workspace.id}/citations/upload`;
      const result = await apiFetch<{ workspace: WorkspaceBundle }>(endpoint, {
        method: "POST",
        body: formData,
      });
      setBundle(result.workspace);
      setMessage(target === "files" ? "资料已导入并分类。" : "文献已导入，系统已尝试补全元数据。");
    } catch (fetchError) {
      setError(fetchError instanceof Error ? fetchError.message : "上传失败");
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

  async function runAction(
    action: "interview" | "recommend" | "generate-report" | "freeze-deliverables",
  ) {
    if (!bundle) return;
    const actionMap: Record<typeof action, string> = {
      interview: `/api/workspaces/${bundle.workspace.id}/interview/generate`,
      recommend: `/api/workspaces/${bundle.workspace.id}/titles/recommend`,
      "generate-report": `/api/workspaces/${bundle.workspace.id}/report/generate`,
      "freeze-deliverables": `/api/workspaces/${bundle.workspace.id}/deliverables/freeze`,
    };
    try {
      setError("");
      const result = await apiFetch<ActionResponse>(actionMap[action], {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body:
          action === "generate-report" || action === "freeze-deliverables"
            ? JSON.stringify({})
            : undefined,
      });
      if (result.workspace) {
        setBundle(result.workspace);
      }
      if (result.report?.report_markdown) {
        setReportPreview(result.report.report_markdown);
      }
      if (result.deliverables?.report?.report_markdown) {
        setReportPreview(result.deliverables.report.report_markdown);
      }
      const nextSections: Record<typeof action, WorkspaceSection> = {
        interview: "titles",
        recommend: "titles",
        "generate-report": "proposal",
        "freeze-deliverables": "materials",
      };
      setActiveSection(nextSections[action]);
      const messages: Record<typeof action, string> = {
        interview: "访谈问题已生成。回答越具体，题目越不会虚。",
        recommend: "候选题已重算。建议先冻结一个题目再写正文。",
        "generate-report": "正文草稿已生成。先读逻辑和引用，不要急着导出。",
        "freeze-deliverables": "冻结版导出已生成。现在可以直接下载。",
      };
      setMessage(messages[action]);
    } catch (fetchError) {
      setError(fetchError instanceof Error ? fetchError.message : "执行动作失败");
    }
  }

  async function submitInterviewAnswers() {
    if (!bundle || !bundle.interview_session) return;
    try {
      setError("");
      const result = await apiFetch<{ workspace: WorkspaceBundle }>(
        `/api/workspaces/${bundle.workspace.id}/interview/answer`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ answers: interviewDraft }),
        },
      );
      setBundle(result.workspace);
      setActiveSection("titles");
      setMessage("访谈结论已回填。现在可以重新生成候选题。");
    } catch (fetchError) {
      setError(fetchError instanceof Error ? fetchError.message : "提交访谈失败");
    }
  }

  async function selectTitle(titleId: string) {
    if (!bundle) return;
    startTransition(() => {
      void (async () => {
        try {
          setError("");
          const data = await apiFetch<WorkspaceBundle>(
            `/api/workspaces/${bundle.workspace.id}/titles/select`,
            {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ title_id: titleId }),
            },
          );
          setBundle(data);
          setActiveSection("proposal");
          setMessage("题目已冻结。接下来正文和交付件都会围绕这一题展开。");
        } catch (fetchError) {
          setError(fetchError instanceof Error ? fetchError.message : "冻结题目失败");
        }
      })();
    });
  }

  return (
    <main className="relative min-h-screen overflow-hidden px-4 py-4 md:px-6 md:py-6">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_12%_12%,rgba(240,133,52,0.14),transparent_18%),radial-gradient(circle_at_85%_18%,rgba(118,167,208,0.12),transparent_24%),linear-gradient(180deg,rgba(8,18,30,0.18),transparent_36%)]" />
      <div className="pointer-events-none absolute inset-x-0 top-0 h-[24rem] bg-[linear-gradient(180deg,rgba(14,30,47,0.92),rgba(14,30,47,0.08))]" />

      <div className="relative mx-auto max-w-[1760px]">
        <header className="reveal overflow-hidden rounded-[40px] border border-[var(--line-strong)] bg-[linear-gradient(145deg,rgba(12,26,42,0.98),rgba(22,44,66,0.88))] px-5 py-6 text-[var(--canvas)] shadow-[var(--shadow-strong)] md:px-8 md:py-8">
          <div className="studio-glow pointer-events-none absolute inset-0" />
          <div className="relative grid gap-8 xl:grid-cols-[minmax(0,1.2fr)_360px]">
            <div className="max-w-4xl">
              <div className="flex flex-wrap items-center gap-3">
                <span className="rounded-full border border-white/12 bg-white/6 px-3 py-1 text-[10px] uppercase tracking-[0.34em] text-[rgba(244,239,230,0.76)]">
                  {BRAND.zhName} {BRAND.enName}
                </span>
                <span className="rounded-full border border-[rgba(240,133,52,0.16)] bg-[rgba(240,133,52,0.1)] px-3 py-1 text-[10px] uppercase tracking-[0.26em] text-[rgba(255,203,154,0.92)]">
                  {BRAND.zhPosition}
                </span>
              </div>
              <p className="mt-5 text-[11px] uppercase tracking-[0.36em] text-[rgba(244,239,230,0.58)]">
                {BRAND.enPosition}
              </p>
              <h1 className="mt-5 max-w-4xl font-serif text-[2.15rem] leading-[1.04] tracking-[-0.04em] text-[var(--canvas)] md:text-[3.2rem] xl:text-[4.15rem]">
                {BRAND.slogan}
                <span className="text-[rgba(255,209,169,0.98)]"> 用四个清晰区块完成选题、论证与答辩。</span>
              </h1>
              <p className="mt-4 max-w-2xl text-sm leading-7 text-[rgba(244,239,230,0.76)] md:text-base">
                你只需要先说清导师、单位、岗位和真实问题，研策会自动补全公开资料，必要时追问关键细节，再生成可核对的开题报告、PPT 和讲稿。
              </p>
              <div className="mt-6 flex flex-col gap-3 sm:flex-row">
                <div className="sm:w-[220px]">
                  <PrimaryButton onClick={() => setActiveSection(nextStep.section)} accent>
                    前往{sectionMeta[nextStep.section].label}
                  </PrimaryButton>
                </div>
                <div className="sm:w-[220px]">
                  <SecondaryButton onClick={() => setActiveSection("background")}>
                    返回项目背景
                  </SecondaryButton>
                </div>
              </div>
              <div className="mt-6 grid gap-3 md:grid-cols-3">
                <HeaderStat
                  label="当前项目"
                  value={bundle?.workspace.name || "未创建"}
                  hint={bundle?.profile.name || "请选择学校规则"}
                />
                <HeaderStat
                  label="当前题目"
                  value={selectedTitle?.title || "尚未冻结"}
                  hint={selectedTitle ? "可以继续生成正文" : "先完成题目收敛"}
                />
                <HeaderStat
                  label="下一步"
                  value={nextStep.title}
                  hint={nextStep.body}
                />
              </div>
            </div>
            <div className="rounded-[32px] border border-white/10 bg-[linear-gradient(180deg,rgba(255,255,255,0.08),rgba(255,255,255,0.03))] p-5 backdrop-blur md:p-6">
              <p className="text-xs uppercase tracking-[0.28em] text-[rgba(244,239,230,0.62)]">
                当前建议
              </p>
              <h2 className="mt-3 font-serif text-3xl text-[var(--canvas)]">{nextStep.title}</h2>
              <p className="mt-3 text-sm leading-7 text-[rgba(244,239,230,0.74)]">{nextStep.body}</p>
              <div className="mt-6 space-y-3">
                <SignalCard
                  title={bundle ? bundle.workspace.name : "尚未创建项目"}
                  body={bundle ? `${bundle.profile.name} · ${activeSectionInfo.label}` : "先创建一个项目，四个区块才会开始工作。"}
                />
                <SignalCard
                  title={topRisk ? prettifyCopy(topRisk.title) : "当前没有关键提醒"}
                  body={topRisk ? prettifyCopy(topRisk.body) : "系统校验默认下沉，只在需要你处理时抬到这里。"}
                  tone={topRisk ? getRiskTone(topRisk.priority) : "muted"}
                />
              </div>
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
                  <span className="text-xs uppercase tracking-[0.22em] text-[var(--ink-soft)]">学校规则</span>
                  <select
                    value={profileId}
                    onChange={(event) => setProfileId(event.target.value)}
                    className="rounded-[18px] border border-[rgba(19,33,51,0.12)] bg-[rgba(255,255,255,0.72)] px-4 py-3 text-sm text-[var(--foreground)] outline-none transition focus:border-[rgba(240,133,52,0.42)]"
                  >
                    {profiles.map((profile) => (
                      <option key={profile.id} value={profile.id} className="text-slate-900">
                        {profile.name}
                      </option>
                    ))}
                  </select>
                </label>
                <button
                  type="submit"
                  className="inline-flex w-full items-center justify-center rounded-full bg-[var(--accent)] px-4 py-3 text-sm font-semibold text-[var(--canvas)] transition hover:bg-[var(--accent-strong)]"
                >
                  开始一个新项目
                </button>
              </form>
            </RailPanel>

            <RailPanel eyebrow="当前项目" title={bundle?.workspace.name || "尚未选择"}>
              <div className="space-y-4">
                <StageRow
                  label="学校规则"
                  value={bundle?.profile.name || "未设置"}
                  hint="项目背景、推荐题目、开题报告和答辩材料都围绕这套规则展开"
                />
                <StageRow
                  label="当前题目"
                  value={selectedTitle?.title || "尚未冻结"}
                  hint={selectedTitle ? "后续报告和答辩材料都会锁定围绕这一题" : "先去推荐题目里选定一个题目"}
                />
                <StageRow
                  label="当前步骤"
                  value={nextStep.title}
                  hint={nextStep.body}
                />
              </div>
            </RailPanel>

            <RailPanel eyebrow="项目" title="项目列表">
              <div className="space-y-2">
                {workspaces.length ? (
                  workspaces.map((workspace) => (
                    <div
                      key={workspace.id}
                      className={`flex items-start gap-2 rounded-[18px] px-2 py-2 transition ${
                        bundle?.workspace.id === workspace.id
                          ? "bg-[rgba(240,133,52,0.1)]"
                          : "hover:bg-[rgba(17,30,46,0.04)]"
                      }`}
                    >
                      <button
                        type="button"
                        onClick={() => void loadWorkspace(workspace.id)}
                        className="min-w-0 flex-1 rounded-[14px] px-2 py-1 text-left"
                      >
                        <span className="line-clamp-2 block text-sm leading-6 text-[var(--foreground)]">
                          {workspace.name}
                        </span>
                        <span className="mt-1 block text-[11px] uppercase tracking-[0.18em] text-[var(--accent)]">
                          {profileNameById[workspace.school_profile] || workspace.school_profile}
                        </span>
                      </button>
                      <button
                        type="button"
                        aria-label={`删除 ${workspace.name}`}
                        title={`删除 ${workspace.name}`}
                        disabled={deletingWorkspaceId === workspace.id}
                        onClick={() => void removeWorkspace(workspace.id, workspace.name)}
                        className="shrink-0 rounded-full border border-[rgba(157,60,51,0.18)] bg-[rgba(157,60,51,0.08)] px-3 py-1.5 text-[11px] uppercase tracking-[0.16em] text-[var(--danger)] transition hover:bg-[rgba(157,60,51,0.14)] disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {deletingWorkspaceId === workspace.id ? "删除中" : "删除"}
                      </button>
                    </div>
                  ))
                ) : (
                  <MutedBlock text="还没有项目。先在左上角创建一个项目。" />
                )}
              </div>
            </RailPanel>
          </aside>

          <section className="reveal space-y-6">
            <nav className="grid gap-3 rounded-[32px] border border-[var(--line-strong)] bg-[rgba(248,242,234,0.86)] p-3 shadow-[var(--shadow-soft)] md:grid-cols-4">
              {(Object.keys(sectionMeta) as WorkspaceSection[]).map((section) => (
                <WorkspaceNavButton
                  key={section}
                  active={activeSection === section}
                  label={sectionMeta[section].label}
                  hint={sectionMeta[section].body}
                  onClick={() => setActiveSection(section)}
                />
              ))}
            </nav>

            <section className="rounded-[32px] border border-[var(--line-strong)] bg-[rgba(248,242,234,0.82)] p-5 shadow-[var(--shadow-soft)]">
              <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
                <div>
                  <p className="text-[10px] uppercase tracking-[0.28em] text-[var(--ink-soft)]">当前步骤</p>
                  <h2 className="mt-2 font-serif text-[2.4rem] leading-tight text-[var(--foreground)]">
                    {activeSectionInfo.title}
                  </h2>
                  <p className="mt-3 max-w-3xl text-sm leading-7 text-[var(--ink-soft)]">
                    {activeSectionInfo.body}
                  </p>
                </div>
                <div className="rounded-[26px] border border-[rgba(19,33,51,0.08)] bg-[rgba(255,255,255,0.7)] p-4">
                  <div className="flex items-center justify-between gap-3">
                    <p className="font-medium text-[var(--foreground)]">系统状态</p>
                    <TonePill tone={error ? "danger" : nextStep.tone}>{error ? "异常" : "正常"}</TonePill>
                  </div>
                  <p className="mt-3 text-sm leading-7 text-[var(--ink-soft)]">{statusText}</p>
                </div>
              </div>
            </section>

            {activeSection === "background" ? (
              <PaperSection eyebrow="项目背景" title="把研究对象和资料边界说清楚">
                <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_340px]">
                  <div>
                    <SectionLead
                      title="核心信息"
                      body="这里先填真正决定题目质量的核心信息。研策会在保存后自动补全学校、导师和单位的公开信息。"
                    />
                    <div className="mt-6 grid gap-4 md:grid-cols-2">
                      {primaryEditableKeys.map(([key, label, placeholder, mode]) => (
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

                    <details className="mt-6 rounded-[24px] border border-[var(--line)] bg-[rgba(255,255,255,0.64)] p-4">
                      <summary className="cursor-pointer list-none text-sm font-medium text-[var(--foreground)]">
                        展开补充信息
                      </summary>
                      <p className="mt-2 text-sm leading-7 text-[var(--ink-soft)]">
                        这些内容不是一开始必须填写，题目收敛或导出前再补也来得及。
                      </p>
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
                    </details>
                  </div>

                  <div className="space-y-4">
                    <ProgressTile
                      label="背景完成度"
                      value={bundle ? `${filledFieldCount}/${editableKeys.length}` : "未开始"}
                      hint="先把研究对象说清，再进入题目比较"
                    />
                    <UploadStage
                      title="导入项目资料"
                      body="上传学校要求、已有草稿、内部材料或访谈纪要，系统会自动归档并作为事实层使用。"
                      hint="支持 md / txt / docx / pdf"
                      onChange={(files) => void uploadFiles("files", files)}
                    />
                    <UploadStage
                      title="导入参考文献"
                      body="优先导入 RIS、BibTeX 或 JSON，后续写综述时会直接使用这些真实条目。"
                      hint="支持 ris / bib / json"
                      onChange={(files) => void uploadFiles("citations", files)}
                    />
                    <div className="rounded-[24px] border border-[var(--line)] bg-[rgba(255,255,255,0.68)] p-4">
                      <div className="grid gap-3 sm:grid-cols-3 xl:grid-cols-1">
                        <StageRow
                          label="资料记录"
                          value={String(bundle?.statistics.evidence_count || 0)}
                          hint="已导入或已补全的资料条目"
                        />
                        <StageRow
                          label="文献数量"
                          value={String(bundle?.statistics.citation_count || 0)}
                          hint="已进入项目空间的参考文献"
                        />
                        <StageRow
                          label="已核验文献"
                          value={String(bundle?.statistics.verified_citation_count || 0)}
                          hint="能进入最终正文的真实引用"
                        />
                      </div>
                    </div>
                    <PrimaryButton onClick={() => void persistFields()} disabled={!bundle}>
                      保存并自动补全
                    </PrimaryButton>
                  </div>
                </div>

                <details className="mt-6 group rounded-[24px] border border-[var(--line)] bg-[rgba(255,255,255,0.62)] p-4">
                  <summary className="flex cursor-pointer list-none items-center justify-between gap-3">
                    <div>
                      <p className="font-medium text-[var(--foreground)]">查看校验与依据</p>
                      <p className="mt-1 text-sm leading-6 text-[var(--ink-soft)]">
                        自动补全、风险提醒、字段冲突和资料清单默认下沉到这里。
                      </p>
                    </div>
                    <span className="text-xs uppercase tracking-[0.22em] text-[var(--accent)] transition group-open:rotate-45">
                      展开
                    </span>
                  </summary>

                  <div className="mt-6 space-y-6">
                    <div>
                      <SectionLead
                        title="系统提醒"
                        body="只有真正会影响题目或正文质量的问题，才值得你在这里花时间看。"
                        compact
                      />
                      <div className="mt-4 space-y-3">
                        {bundle?.risks.length ? (
                          bundle.risks.map((risk) => <RiskRow key={risk.id} risk={risk} />)
                        ) : (
                          <MutedBlock text="当前没有需要额外提醒的问题。" padded />
                        )}
                      </div>
                    </div>

                    <div className="grid gap-6 xl:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]">
                      <div>
                        <SectionLead
                          title="当前口径"
                          body="用于核对同一字段有没有多个不同版本，避免后面写着写着跑偏。"
                          compact
                        />
                        <div className="mt-4 overflow-hidden rounded-[26px] border border-[var(--line)] bg-[rgba(255,255,255,0.76)]">
                          {bundle?.field_groups.length ? (
                            bundle.field_groups.map((group, index) => (
                              <LedgerRow
                                key={group.key}
                                title={getFieldLabel(group.key)}
                                subtitle={group.current.value || "未设置"}
                                meta={`${group.current.source_label} · ${group.current.source_grade}级来源`}
                                status={group.has_conflict ? "conflict" : group.current.confirmed ? "confirmed" : "draft"}
                                bordered={index !== bundle.field_groups.length - 1}
                              />
                            ))
                          ) : (
                            <MutedBlock text="保存字段或导入资料后，这里会显示当前口径和可能的冲突。" padded />
                          )}
                        </div>
                      </div>

                      <div>
                        <SectionLead
                          title="资料与文献"
                          body="所有已导入和已补全的资料都会出现在这里，供你按需核对。"
                          compact
                        />
                        <div className="mt-4 overflow-hidden rounded-[26px] border border-[var(--line)] bg-[rgba(255,255,255,0.76)]">
                          {bundle?.evidence_items.length ? (
                            bundle.evidence_items.map((item, index) => (
                              <EvidenceLedgerRow
                                key={item.id}
                                item={item}
                                bordered={index !== bundle.evidence_items.length - 1}
                              />
                            ))
                          ) : (
                            <MutedBlock text="还没有资料记录。保存基本信息或导入文件后，系统会自动补全并更新这里。" padded />
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                </details>
              </PaperSection>
            ) : null}

            {activeSection === "titles" ? (
              <PaperSection eyebrow="推荐题目" title="先问清，再比较">
                <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_320px]">
                  <div>
                    {bundle?.interview_session ? (
                      <div className="rounded-[26px] border border-[var(--line)] bg-[rgba(255,248,240,0.72)] p-5">
                        <div className="flex items-center justify-between gap-3">
                          <SectionLead
                            title="访谈收敛"
                            body="这些问题只服务于题目收敛，不需要你先理解系统内部逻辑。"
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
                          <PrimaryButton onClick={() => void submitInterviewAnswers()}>
                            保存访谈回答
                          </PrimaryButton>
                        </div>
                      </div>
                    ) : (
                      <MutedBlock text="如果你觉得题目还不够聚焦，可以先触发收敛访谈，让系统补问几个关键问题。" padded />
                    )}

                    <div className="mt-6">
                      {bundle?.title_candidates.length ? (
                        <div className="grid gap-4 xl:grid-cols-2">
                          {bundle.title_candidates.map((candidate) => (
                            <TitleBoardRow
                              key={candidate.id}
                              candidate={candidate}
                              onSelect={() => void selectTitle(candidate.id)}
                            />
                          ))}
                        </div>
                      ) : (
                        <MutedBlock text="还没有推荐题目。先补资料，或直接点“生成推荐题目”。" padded />
                      )}
                    </div>
                  </div>

                  <div className="space-y-4">
                    <StageRow
                      label="候选题数量"
                      value={String(readyTitleCount)}
                      hint="建议先比较 3 到 5 个题目，再冻结一个题目"
                    />
                    <StageRow
                      label="已冻结题目"
                      value={selectedTitle ? "1 个" : "未冻结"}
                      hint={selectedTitle ? selectedTitle.title : "冻结后才能稳定生成报告和材料"}
                    />
                    <SecondaryButton onClick={() => void runAction("interview")} disabled={!bundle || !hasPrimaryFields}>
                      触发收敛访谈
                    </SecondaryButton>
                    <PrimaryButton onClick={() => void runAction("recommend")} disabled={!bundle || !hasPrimaryFields}>
                      生成推荐题目
                    </PrimaryButton>
                  </div>
                </div>
              </PaperSection>
            ) : null}

            {activeSection === "proposal" ? (
              <PaperSection eyebrow="开题报告" title={selectedTitle?.title || "先从推荐题目里确定一个题目"}>
                <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_320px]">
                  <div className="rounded-[28px] border border-[var(--line)] bg-[linear-gradient(180deg,rgba(255,255,255,0.86),rgba(252,247,239,0.8))] p-5">
                    <div className="flex flex-wrap items-start justify-between gap-4">
                      <div>
                        <p className="text-xs uppercase tracking-[0.26em] text-[var(--ink-soft)]">报告预览</p>
                        <h3 className="mt-2 font-serif text-3xl leading-tight text-[var(--foreground)]">
                          {selectedTitle?.title || "先去推荐题目里选定一个题目"}
                        </h3>
                      </div>
                      {isPending ? <TonePill tone="warning">更新中</TonePill> : null}
                    </div>
                    {reportPreview ? (
                      <pre className="paper-preview mt-5 max-h-[760px] overflow-auto whitespace-pre-wrap rounded-[24px] border border-[rgba(19,33,51,0.08)] bg-[rgba(255,255,255,0.82)] px-5 py-5 text-sm leading-7 text-[var(--foreground)]">
                        {reportPreview}
                      </pre>
                    ) : (
                      <MutedBlock text="这里会显示开题报告草稿。先确定题目，再点击生成报告。" padded />
                    )}
                  </div>

                  <div className="space-y-4">
                    <div className="rounded-[28px] border border-[var(--line)] bg-[rgba(249,244,236,0.88)] p-5">
                      <SectionLead
                        title="报告动作"
                        body="先看结构和论证方向，再决定是否进入答辩材料导出。"
                        compact
                      />
                      <div className="mt-5">
                        <PrimaryButton onClick={() => void runAction("generate-report")} disabled={!selectedTitle}>
                          生成开题报告
                        </PrimaryButton>
                      </div>
                    </div>

                    <div className="rounded-[28px] border border-[var(--line)] bg-[rgba(255,255,255,0.76)] p-5">
                      <SectionLead
                        title="学校要求"
                        body="这部分是当前学校规则要求的报告结构，正文生成会围绕它来组织。"
                        compact
                      />
                      <div className="mt-4 space-y-2">
                        {bundle?.profile.required_sections.length ? (
                          bundle.profile.required_sections.map((section) => (
                            <div
                              key={section}
                              className="rounded-[18px] border border-[rgba(19,33,51,0.08)] bg-[rgba(255,255,255,0.68)] px-4 py-3 text-sm text-[var(--foreground)]"
                            >
                              {section}
                            </div>
                          ))
                        ) : (
                          <MutedBlock text="当前还没有加载到学校结构要求。" />
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              </PaperSection>
            ) : null}

            {activeSection === "materials" ? (
              <PaperSection eyebrow="答辩材料" title="统一导出你真正会用到的成果">
                <div className="grid gap-6 xl:grid-cols-[320px_minmax(0,1fr)]">
                  <div className="space-y-4">
                    <StageRow
                      label="当前题目"
                      value={selectedTitle?.title || "尚未冻结"}
                      hint="答辩材料只会围绕冻结题目生成"
                    />
                    <StageRow
                      label="导出状态"
                      value={hasExports ? "已冻结" : "未导出"}
                      hint={hasExports ? "可以直接下载和预览" : "先生成报告，再冻结导出"}
                    />
                    <PrimaryButton
                      onClick={() => void runAction("freeze-deliverables")}
                      disabled={!selectedTitle}
                      accent
                    >
                      冻结并生成答辩材料
                    </PrimaryButton>
                  </div>

                  <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                    <DeliverableCard
                      label="开题报告 Markdown"
                      hint="便于快速审阅与版本对比"
                      ready={Boolean(bundle?.deliverable_bundle)}
                      href={bundle ? `${API_BASE}/api/workspaces/${bundle.workspace.id}/download/report_md` : undefined}
                    />
                    <DeliverableCard
                      label="开题报告 Word"
                      hint="正式提交和编辑时使用"
                      ready={Boolean(bundle?.deliverable_bundle)}
                      href={bundle ? `${API_BASE}/api/workspaces/${bundle.workspace.id}/download/report_docx` : undefined}
                    />
                    <DeliverableCard
                      label="答辩 PPT"
                      hint="从冻结版报告自动派生"
                      ready={Boolean(bundle?.deliverable_bundle)}
                      href={bundle ? `${API_BASE}/api/workspaces/${bundle.workspace.id}/download/deck_pptx` : undefined}
                    />
                    <DeliverableCard
                      label="讲稿 Markdown"
                      hint="适合先看逻辑和口语化节奏"
                      ready={Boolean(bundle?.deliverable_bundle)}
                      href={bundle ? `${API_BASE}/api/workspaces/${bundle.workspace.id}/download/notes_md` : undefined}
                    />
                    <DeliverableCard
                      label="讲稿 Word"
                      hint="适合打印和二次修订"
                      ready={Boolean(bundle?.deliverable_bundle)}
                      href={bundle ? `${API_BASE}/api/workspaces/${bundle.workspace.id}/download/notes_docx` : undefined}
                    />
                    <DeliverableCard
                      label="来源快照"
                      hint="用于回看引用和证据依据"
                      ready={Boolean(bundle?.deliverable_bundle)}
                      href={bundle ? `${API_BASE}/api/workspaces/${bundle.workspace.id}/download/snapshot` : undefined}
                    />
                  </div>
                </div>
              </PaperSection>
            ) : null}
          </section>
        </div>
      </div>
    </main>
  );
}

function HeaderStat({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint: string;
}) {
  return (
    <div className="rounded-[22px] border border-white/10 bg-[rgba(255,255,255,0.06)] px-4 py-4">
      <p className="text-[10px] uppercase tracking-[0.24em] text-[rgba(244,239,230,0.56)]">{label}</p>
      <p className="mt-2 line-clamp-3 text-sm leading-6 text-[var(--canvas)]">{value}</p>
      <p className="mt-2 text-xs text-[rgba(244,239,230,0.58)]">{hint}</p>
    </div>
  );
}

function SignalCard({
  title,
  body,
  tone = "muted",
}: {
  title: string;
  body: string;
  tone?: "success" | "warning" | "danger" | "muted";
}) {
  const styles: Record<typeof tone, string> = {
    success: "border-[rgba(37,109,82,0.18)] bg-[rgba(37,109,82,0.08)]",
    warning: "border-[rgba(153,93,29,0.18)] bg-[rgba(153,93,29,0.08)]",
    danger: "border-[rgba(157,60,51,0.18)] bg-[rgba(157,60,51,0.08)]",
    muted: "border-white/10 bg-[rgba(255,255,255,0.05)]",
  };

  return (
    <div className={`rounded-[22px] border px-4 py-4 ${styles[tone]}`}>
      <p className="text-sm font-medium text-[var(--canvas)]">{title}</p>
      <p className="mt-2 text-sm leading-6 text-[rgba(244,239,230,0.7)]">{body}</p>
    </div>
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
}: {
  eyebrow: string;
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="rounded-[34px] border border-[var(--line-strong)] bg-[var(--paper)] p-5 shadow-[var(--shadow-soft)] backdrop-blur md:p-6">
      <div className="flex flex-wrap items-end justify-between gap-4 border-b border-[rgba(19,33,51,0.08)] pb-4">
        <div>
          <p className="text-[10px] uppercase tracking-[0.28em] text-[var(--ink-soft)]">{eyebrow}</p>
          <h2 className="mt-2 font-serif text-[2.15rem] leading-tight text-[var(--foreground)]">{title}</h2>
        </div>
      </div>
      <div className="mt-6">{children}</div>
    </section>
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
  onChange,
}: {
  label: string;
  value: string;
  placeholder: string;
  multiline: boolean;
  onChange: (value: string) => void;
}) {
  return (
    <label className="grid gap-2 rounded-[24px] border border-[rgba(19,33,51,0.08)] bg-[rgba(255,255,255,0.72)] p-4 transition hover:border-[rgba(19,33,51,0.16)]">
      <span className="text-xs uppercase tracking-[0.24em] text-[var(--ink-soft)]">{label}</span>
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
  onChange,
}: {
  title: string;
  body: string;
  hint: string;
  onChange: (files: FileList | null) => void;
}) {
  return (
    <label className="group relative cursor-pointer overflow-hidden rounded-[28px] border border-dashed border-[rgba(19,33,51,0.18)] bg-[linear-gradient(180deg,rgba(255,255,255,0.8),rgba(247,241,233,0.74))] p-5 transition hover:border-[var(--accent)]">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-16 bg-[linear-gradient(180deg,rgba(240,133,52,0.08),transparent)] opacity-0 transition group-hover:opacity-100" />
      <div className="relative">
        <p className="font-serif text-2xl text-[var(--foreground)]">{title}</p>
        <p className="mt-2 text-sm leading-7 text-[var(--ink-soft)]">{body}</p>
        <div className="mt-4 flex items-center justify-between gap-4">
          <span className="rounded-full bg-[rgba(240,133,52,0.1)] px-3 py-1 text-[11px] uppercase tracking-[0.2em] text-[var(--accent)]">
            选择文件
          </span>
          <span className="text-xs text-[var(--ink-soft)]">{hint}</span>
        </div>
      </div>
      <input type="file" multiple className="hidden" onChange={(event) => onChange(event.target.files)} />
    </label>
  );
}

function LedgerRow({
  title,
  subtitle,
  meta,
  status,
  bordered,
}: {
  title: string;
  subtitle: string;
  meta: string;
  status: "conflict" | "confirmed" | "draft";
  bordered: boolean;
}) {
  return (
    <div className={`flex gap-4 px-4 py-4 ${bordered ? "border-b border-[rgba(19,33,51,0.08)]" : ""}`}>
      <div
        className={`mt-1 h-3 w-3 rounded-full ${
          status === "conflict"
            ? "bg-[var(--danger)]"
            : status === "confirmed"
              ? "bg-[var(--success)]"
              : "bg-[rgba(19,33,51,0.22)]"
        }`}
      />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <p className="font-medium text-[var(--foreground)]">{title}</p>
          <TonePill tone={status === "conflict" ? "danger" : status === "confirmed" ? "success" : "muted"}>
            {status === "conflict" ? "冲突" : status === "confirmed" ? "确认" : "待确认"}
          </TonePill>
        </div>
        <p className="mt-1 text-sm leading-7 text-[var(--foreground)]">{subtitle}</p>
        <p className="mt-1 text-xs leading-6 text-[var(--ink-soft)]">{meta}</p>
      </div>
    </div>
  );
}

function EvidenceLedgerRow({
  item,
  bordered,
}: {
  item: EvidenceItem;
  bordered: boolean;
}) {
  return (
    <div className={`flex gap-4 px-4 py-4 ${bordered ? "border-b border-[rgba(19,33,51,0.08)]" : ""}`}>
      <div className="mt-1 w-[92px] shrink-0">
        <TonePill tone={item.grade === "A" ? "success" : item.grade === "B" ? "warning" : "muted"}>
          {item.grade}级
        </TonePill>
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <p className="font-medium text-[var(--foreground)]">{item.title}</p>
          <TonePill tone={item.status === "verified" ? "success" : item.status === "blocked" ? "danger" : "warning"}>
            {getEvidenceStatusLabel(item.status)}
          </TonePill>
        </div>
        <p className="mt-1 text-sm leading-7 text-[var(--ink-soft)]">{item.summary}</p>
        <div className="mt-2 flex flex-wrap gap-2 text-[11px] uppercase tracking-[0.16em] text-[var(--ink-soft)]">
          <span>{getEvidenceTypeLabel(item.evidence_type)}</span>
          <span>·</span>
          <span>{item.source_label}</span>
        </div>
        {item.source_uri ? (
          <p className="mt-2 truncate text-xs leading-6 text-[var(--ink-soft)]">{item.source_uri}</p>
        ) : null}
      </div>
    </div>
  );
}

function ProgressTile({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint: string;
}) {
  return (
    <div className="rounded-[22px] border border-[rgba(19,33,51,0.08)] bg-[rgba(255,255,255,0.66)] px-4 py-4">
      <p className="text-[10px] uppercase tracking-[0.22em] text-[var(--ink-soft)]">{label}</p>
      <p className="mt-2 text-2xl text-[var(--foreground)]">{value}</p>
      <p className="mt-2 text-sm leading-6 text-[var(--ink-soft)]">{hint}</p>
    </div>
  );
}

function StageRow({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint: string;
}) {
  return (
    <div className="rounded-[20px] border border-[rgba(19,33,51,0.08)] bg-[rgba(255,255,255,0.62)] px-4 py-4">
      <div className="flex items-center justify-between gap-3">
        <span className="text-sm font-medium text-[var(--foreground)]">{label}</span>
        <span className="text-sm text-[var(--foreground-soft)]">{value}</span>
      </div>
      <p className="mt-2 text-sm leading-6 text-[var(--ink-soft)]">{hint}</p>
    </div>
  );
}

function WorkspaceNavButton({
  active,
  label,
  hint,
  onClick,
}: {
  active: boolean;
  label: string;
  hint: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-[24px] border px-4 py-4 text-left transition ${
        active
          ? "border-[rgba(240,133,52,0.38)] bg-[rgba(240,133,52,0.12)] shadow-[0_18px_36px_rgba(240,133,52,0.08)]"
          : "border-[rgba(19,33,51,0.08)] bg-[rgba(255,255,255,0.68)] hover:border-[rgba(19,33,51,0.16)]"
      }`}
    >
      <p className="font-medium text-[var(--foreground)]">{label}</p>
      <p className="mt-2 text-sm leading-6 text-[var(--ink-soft)]">{hint}</p>
    </button>
  );
}

function TitleBoardRow({
  candidate,
  onSelect,
}: {
  candidate: TitleCandidate;
  onSelect: () => void;
}) {
  return (
    <div
      className={`w-full rounded-[24px] border px-4 py-4 text-left transition ${
        candidate.selected
          ? "border-[rgba(240,133,52,0.42)] bg-[rgba(240,133,52,0.1)] shadow-[0_18px_32px_rgba(240,133,52,0.08)]"
          : "border-[rgba(19,33,51,0.08)] bg-[rgba(255,255,255,0.7)] hover:border-[rgba(19,33,51,0.18)]"
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <p className="font-serif text-xl leading-8 text-[var(--foreground)]">{candidate.title}</p>
        <div className="shrink-0 text-right">
          <p className="font-mono text-2xl text-[var(--foreground)]">{candidate.total_score}</p>
          <p className="text-[10px] uppercase tracking-[0.2em] text-[var(--ink-soft)]">推荐度</p>
        </div>
      </div>
      <p className="mt-3 text-sm leading-7 text-[var(--ink-soft)]">{candidate.recommendation}</p>
      {candidate.reasons.length ? (
        <ul className="mt-4 space-y-2 text-sm leading-6 text-[var(--foreground-soft)]">
          {candidate.reasons.slice(0, 2).map((reason) => (
            <li key={reason} className="flex gap-3">
              <span className="mt-2 h-1.5 w-1.5 rounded-full bg-[var(--accent)]" />
              <span>{prettifyCopy(reason)}</span>
            </li>
          ))}
        </ul>
      ) : null}
      {candidate.caution ? (
        <p className="mt-4 rounded-[18px] bg-[rgba(157,60,51,0.06)] px-3 py-3 text-sm leading-6 text-[var(--danger)]">
          需要注意：{prettifyCopy(candidate.caution)}
        </p>
      ) : null}
      <details className="mt-4 rounded-[18px] border border-[rgba(19,33,51,0.08)] bg-[rgba(255,255,255,0.52)] px-3 py-3">
        <summary className="cursor-pointer list-none text-xs uppercase tracking-[0.2em] text-[var(--ink-soft)]">
          查看匹配度细节
        </summary>
        <div className="mt-4 grid grid-cols-5 gap-2">
          <MiniScore label={scoreLabels[0]} value={candidate.school_fit} />
          <MiniScore label={scoreLabels[1]} value={candidate.mentor_fit} />
          <MiniScore label={scoreLabels[2]} value={candidate.role_fit} />
          <MiniScore label={scoreLabels[3]} value={candidate.evidence_fit} />
          <MiniScore label={scoreLabels[4]} value={candidate.confidentiality_fit} />
        </div>
        {candidate.risk_tags.length ? (
          <div className="mt-4 flex flex-wrap gap-2">
            {candidate.risk_tags.map((tag) => (
              <TonePill key={tag} tone={tag.includes("不建议") ? "danger" : "warning"}>
                {prettifyCopy(tag)}
              </TonePill>
            ))}
          </div>
        ) : null}
      </details>
      <div className="mt-4">
        {candidate.selected ? (
          <TonePill tone="success">已选定这个题目</TonePill>
        ) : (
          <SecondaryButton onClick={onSelect}>选择这个题目</SecondaryButton>
        )}
      </div>
    </div>
  );
}

function MiniScore({
  label,
  value,
}: {
  label: string;
  value: number;
}) {
  return (
    <div className="rounded-[14px] bg-[rgba(19,33,51,0.06)] px-2 py-2">
      <div className="h-1.5 rounded-full bg-[rgba(19,33,51,0.08)]">
        <div
          className="h-1.5 rounded-full bg-[linear-gradient(90deg,var(--accent),var(--foreground))] transition-all duration-500"
          style={{ width: `${Math.max(10, Math.min(100, value))}%` }}
        />
      </div>
      <p className="mt-2 text-center text-[10px] uppercase tracking-[0.14em] text-[var(--ink-soft)]">{label}</p>
      <p className="mt-2 text-center font-mono text-[11px] text-[var(--foreground)]">{value.toFixed(0)}</p>
    </div>
  );
}

function RiskRow({
  risk,
}: {
  risk: { id: string; title: string; body: string; priority: number };
}) {
  return (
    <div className="rounded-[22px] border border-[rgba(19,33,51,0.08)] bg-[rgba(255,255,255,0.68)] px-4 py-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-medium text-[var(--foreground)]">{prettifyCopy(risk.title)}</p>
          <p className="mt-2 text-sm leading-7 text-[var(--ink-soft)]">{prettifyCopy(risk.body)}</p>
        </div>
        <TonePill tone={getRiskTone(risk.priority)}>
          {getRiskPriorityLabel(risk.priority)} · P{risk.priority}
        </TonePill>
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
      className={`inline-flex w-full items-center justify-center rounded-full px-4 py-3 text-sm font-semibold transition ${
        accent
          ? "bg-[var(--accent)] text-[var(--canvas)] hover:bg-[var(--accent-strong)]"
          : "bg-[var(--foreground)] text-[var(--canvas)] hover:bg-[var(--foreground-soft)]"
      } disabled:cursor-not-allowed disabled:opacity-50`}
    >
      {children}
    </button>
  );
}

function SecondaryButton({
  children,
  onClick,
  disabled,
}: {
  children: ReactNode;
  onClick: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className="inline-flex w-full items-center justify-center rounded-full border border-[rgba(19,33,51,0.12)] bg-[rgba(255,255,255,0.72)] px-4 py-3 text-sm font-semibold text-[var(--foreground)] transition hover:border-[rgba(240,133,52,0.36)] hover:bg-[rgba(255,255,255,0.9)] disabled:cursor-not-allowed disabled:opacity-50"
    >
      {children}
    </button>
  );
}

function ArtifactLink({ href, label }: { href: string; label: string }) {
  return (
    <a
      href={href}
      className="rounded-[18px] border border-[rgba(19,33,51,0.08)] bg-[rgba(255,255,255,0.68)] px-4 py-3 text-sm text-[var(--foreground)] transition hover:border-[rgba(240,133,52,0.36)] hover:bg-[rgba(255,255,255,0.86)]"
      target="_blank"
      rel="noreferrer"
    >
      {label}
    </a>
  );
}

function DeliverableCard({
  label,
  hint,
  ready,
  href,
}: {
  label: string;
  hint: string;
  ready: boolean;
  href?: string;
}) {
  return (
    <div className="rounded-[24px] border border-[rgba(19,33,51,0.08)] bg-[rgba(255,255,255,0.72)] p-4">
      <div className="flex items-center justify-between gap-3">
        <p className="font-medium text-[var(--foreground)]">{label}</p>
        <TonePill tone={ready ? "success" : "muted"}>{ready ? "可下载" : "待生成"}</TonePill>
      </div>
      <p className="mt-3 text-sm leading-6 text-[var(--ink-soft)]">{hint}</p>
      <div className="mt-4">
        {ready && href ? (
          <ArtifactLink href={href} label="下载文件" />
        ) : (
          <MutedBlock text="冻结导出后会在这里提供下载。" />
        )}
      </div>
    </div>
  );
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
