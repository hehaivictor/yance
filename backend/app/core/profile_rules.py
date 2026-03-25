from __future__ import annotations

import re
from typing import Any


CORPORATE_SUFFIXES = (
    "股份有限公司",
    "有限责任公司",
    "有限公司",
    "集团公司",
    "集团",
    "公司",
)

NON_COMPANY_HINTS = (
    "大学",
    "学院",
    "研究院",
    "医院",
    "实验室",
    "中心",
    "事务所",
    "协会",
    "委员会",
    "政府",
    "机关",
    "学校",
)

LOCATION_PREFIXES = (
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
)

BUSINESS_SUFFIXES = (
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
)

PINYIN_INITIALS = (
    (-20319, "A"),
    (-20284, "B"),
    (-19776, "C"),
    (-19219, "D"),
    (-18711, "E"),
    (-18527, "F"),
    (-18240, "G"),
    (-17923, "H"),
    (-17418, "J"),
    (-16475, "K"),
    (-16213, "L"),
    (-15641, "M"),
    (-15166, "N"),
    (-14923, "O"),
    (-14915, "P"),
    (-14631, "Q"),
    (-14150, "R"),
    (-14091, "S"),
    (-13319, "T"),
    (-12839, "W"),
    (-12557, "X"),
    (-11848, "Y"),
    (-11056, "Z"),
)


def has_builtin_guide(profile: dict[str, Any]) -> bool:
    guide = profile.get("guide") or {}
    return bool(guide.get("title"))


def shorten_subject_name(name: str, max_length: int = 10) -> str:
    normalized = str(name or "").strip()
    if not normalized:
        return "研究对象"
    if len(normalized) <= max_length:
        return normalized
    stripped = normalized
    for suffix in CORPORATE_SUFFIXES:
        if stripped.endswith(suffix):
            stripped = stripped[: -len(suffix)].strip()
            break
    if stripped and len(stripped) <= max_length:
        return stripped
    compact = stripped or normalized
    return compact[:max_length]


def anonymized_subject_name(name: str, confidentiality: str = "") -> str:
    normalized = str(name or "").strip()
    if not normalized:
        return "研究对象"
    confidential = any(keyword in str(confidentiality or "") for keyword in ["匿名", "保密", "不便披露", "化名"])
    is_company = _looks_like_company(normalized)
    if confidential:
        return "K公司" if is_company else "K单位"
    initial = _subject_alias_initial(normalized) or "K"
    return f"{initial}公司" if is_company else f"{initial}单位"


def privacy_safe_report_title(title: str, company_name: str = "", confidentiality: str = "") -> str:
    normalized = str(title or "").strip()
    subject_name = str(company_name or "").strip()
    if not normalized or not subject_name:
        return normalized
    alias = anonymized_subject_name(subject_name, confidentiality)
    normalized = _normalize_legacy_alias(normalized, alias, subject_name)
    replacements = {
        subject_name,
        shorten_subject_name(subject_name),
    }
    stripped = subject_name
    for suffix in CORPORATE_SUFFIXES:
        if stripped.endswith(suffix):
            stripped = stripped[: -len(suffix)].strip()
            break
    if stripped:
        replacements.add(stripped)
    for candidate in sorted({item for item in replacements if item}, key=len, reverse=True):
        normalized = normalized.replace(candidate, alias)
    return normalized


def privacy_safe_text(text: str, company_name: str = "", confidentiality: str = "") -> str:
    normalized = str(text or "")
    subject_name = str(company_name or "").strip()
    if not normalized or not subject_name:
        return normalized
    alias = anonymized_subject_name(subject_name, confidentiality)
    normalized = _normalize_legacy_alias(normalized, alias, subject_name)
    replacements = {
        subject_name,
        shorten_subject_name(subject_name),
    }
    stripped = subject_name
    for suffix in CORPORATE_SUFFIXES:
        if stripped.endswith(suffix):
            stripped = stripped[: -len(suffix)].strip()
            break
    if stripped:
        replacements.add(stripped)
    for candidate in sorted({item for item in replacements if item}, key=len, reverse=True):
        normalized = normalized.replace(candidate, alias)
    return normalized


def validate_title(title: str, profile: dict[str, Any]) -> list[str]:
    normalized = str(title or "").strip()
    issues: list[str] = []
    if not normalized:
        return ["题目不能为空。"]
    rules = profile.get("title_style_rules") or {}
    max_length = int(rules.get("max_length", 25))
    if len(normalized) > max_length:
        issues.append(f"题目长度超过 {max_length} 字。")
    for pattern in rules.get("forbidden_patterns", []):
        if pattern and pattern in normalized:
            issues.append(f"题目包含不建议使用的表达“{pattern}”。")
    return issues


def filter_title_candidates(titles: list[str], profile: dict[str, Any]) -> list[str]:
    valid_titles: list[str] = []
    for raw in titles:
        normalized = str(raw or "").strip().replace("《", "").replace("》", "")
        if not normalized or normalized in valid_titles:
            continue
        if validate_title(normalized, profile):
            continue
        valid_titles.append(normalized)
    return valid_titles


def fallback_title(subject_name: str, profile: dict[str, Any]) -> str:
    max_length = int((profile.get("title_style_rules") or {}).get("max_length", 25))
    subject = shorten_subject_name(subject_name, max_length=max(2, max_length - 6))
    candidate = f"{subject}管理优化研究"
    if len(candidate) <= max_length:
        return candidate
    return "管理优化研究"


def candidate_recommendation_copy(
    title: str,
    current: dict[str, Any],
    grounding: dict[str, Any],
    *,
    is_top: bool = False,
) -> str:
    normalized = str(title or "").strip()
    prefix = "优先推荐。" if is_top else ""
    anchor_suffix = _recommendation_anchor_suffix(current, grounding)
    if "项目落地" in normalized or "落地机制" in normalized:
        return (
            prefix
            + "围绕从立项、试点、部署到推广复盘的全过程，诊断落地卡点并提出机制优化方案；"
            + _merge_reason_clauses("最符合经管类专题研究常用的“问题诊断-成因分析-方案设计”写法", anchor_suffix)
        )
    if "产品化" in normalized or "平台能力" in normalized:
        return (
            prefix
            + "聚焦能力如何从项目型交付沉淀为可复制的产品或平台机制；"
            + _merge_reason_clauses("既贴近业务升级场景，也便于从岗位实践中提炼问题与方案", anchor_suffix)
        )
    if "组织协同" in normalized or "协同机制" in normalized:
        return (
            prefix
            + "聚焦部门协同断点、职责边界与流程衔接问题；"
            + _merge_reason_clauses("现实价值强，访谈和内部资料都更容易做深", anchor_suffix)
        )
    if "知识库" in normalized or "知识管理" in normalized or "交付机制" in normalized:
        return (
            prefix
            + "聚焦知识沉淀、复用与交付质量之间的关系；"
            + _merge_reason_clauses("适合结合现有资料、流程经验和管理改进口径来展开", anchor_suffix)
        )
    if "数据准备" in normalized or "数据治理" in normalized:
        return (
            prefix
            + "聚焦落地前的数据准备、接口衔接和治理问题；"
            + _merge_reason_clauses("问题边界清晰，适合用内部资料和公开材料交叉验证", anchor_suffix)
        )
    if "价值评估" in normalized or "评估体系" in normalized:
        return (
            prefix
            + "聚焦项目的业务价值、组织价值与推广价值如何评价；"
            + _merge_reason_clauses("适合案例较多但技术细节不便展开的管理场景", anchor_suffix)
        )
    if "组织协同优化" in normalized:
        return (
            prefix
            + "围绕跨部门协同、职责边界和流程衔接来做专题研究；"
            + _merge_reason_clauses("既贴近岗位场景，也更容易通过访谈把证据做实", anchor_suffix)
        )
    if "管理问题诊断与优化" in normalized:
        return (
            prefix
            + "先做现状诊断，再提出优化方案，结构稳、容错高；"
            + _merge_reason_clauses("适合当前资料还在逐步补充、但已能锁定研究对象的阶段", anchor_suffix)
        )
    if "管理机制优化" in normalized:
        return (
            prefix
            + "围绕当前组织运行中的关键机制问题展开；"
            + _merge_reason_clauses("便于从制度、流程与执行卡点切入，按专题研究逻辑展开", anchor_suffix)
        )
    return prefix + _merge_reason_clauses(
        "题目边界相对稳，便于围绕真实管理问题做诊断、解释与方案设计",
        anchor_suffix,
    )


def validate_section_map(section_map: dict[str, str], profile: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    expected_order = list(profile.get("section_order") or profile.get("required_sections") or [])
    actual_order = list(section_map.keys())
    if expected_order and actual_order != expected_order:
        issues.append("开题报告章节顺序与学校规则不一致。")
    for section_name in expected_order:
        content = str(section_map.get(section_name) or "").strip()
        if not content:
            issues.append(f"缺少章节：{section_name}。")
    return issues


def _subject_alias_initial(name: str) -> str:
    core = _company_core_name(name)
    if not core:
        return ""
    first_char = core[0]
    if first_char.isascii() and first_char.isalpha():
        return first_char.upper()
    return _chinese_initial(first_char)


def _company_core_name(name: str) -> str:
    normalized = re.sub(r"[\s·•()（）\-_/]+", "", str(name or "").strip())
    if not normalized:
        return ""
    stripped = normalized
    for suffix in CORPORATE_SUFFIXES:
        if stripped.endswith(suffix):
            stripped = stripped[: -len(suffix)].strip()
            break
    core = stripped or normalized
    for prefix in LOCATION_PREFIXES:
        if core.startswith(prefix) and len(core) > len(prefix) + 1:
            core = core[len(prefix) :].strip()
            break
    for suffix in BUSINESS_SUFFIXES:
        if core.endswith(suffix) and len(core) > len(suffix) + 1:
            core = core[: -len(suffix)].strip()
            break
    return core or stripped or normalized


def _chinese_initial(char: str) -> str:
    if not char:
        return ""
    try:
        gbk = char.encode("gbk")
    except UnicodeEncodeError:
        return ""
    if len(gbk) < 2:
        return ""
    code = gbk[0] * 256 + gbk[1] - 65536
    for boundary, initial in reversed(PINYIN_INITIALS):
        if code >= boundary:
            return initial
    return ""


def _recommendation_anchor_suffix(current: dict[str, Any], grounding: dict[str, Any]) -> str:
    role_anchor = _clip_text(str(grounding.get("role_focus") or current.get("work_scope") or current.get("role_title") or ""))
    mentor_anchor = _clip_text(
        _join_list(grounding.get("mentor_research_fields")) or str(current.get("research_direction") or "")
    )
    company_anchor = _clip_text(str(grounding.get("company_business") or ""))
    clauses: list[str] = []
    if role_anchor:
        clauses.append(f"也贴合当前的“{role_anchor}”工作场景")
    elif company_anchor:
        clauses.append(f"研究对象边界可落到“{company_anchor}”这一业务场景")
    if mentor_anchor and mentor_anchor not in {"待补充", "专业学位论文选题方向仍需进一步聚焦。"}:
        clauses.append(f"同时能与导师“{mentor_anchor}”方向形成衔接")
    return "；".join(clauses)


def _merge_reason_clauses(base: str, suffix: str) -> str:
    normalized_base = str(base or "").strip().rstrip("；。")
    normalized_suffix = str(suffix or "").strip().rstrip("；。")
    if normalized_suffix:
        return f"{normalized_base}；{normalized_suffix}。"
    return f"{normalized_base}。"


def _join_list(values: Any) -> str:
    if isinstance(values, list):
        cleaned = [str(item).strip() for item in values if str(item).strip()]
        return "、".join(cleaned[:3])
    return str(values or "").strip()


def _clip_text(text: str, limit: int = 18) -> str:
    normalized = str(text or "").strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[:limit].rstrip("，；。、 ") + "..."


def _looks_like_company(name: str) -> bool:
    normalized = str(name or "").strip()
    if not normalized:
        return False
    if any(hint in normalized for hint in NON_COMPANY_HINTS):
        return False
    return True


def _normalize_legacy_alias(text: str, alias: str, subject_name: str) -> str:
    normalized = str(text or "")
    if not normalized:
        return normalized
    if _looks_like_company(subject_name):
        return re.sub(r"([A-Z])单位", r"\1公司", normalized)
    return re.sub(r"([A-Z])公司", r"\1单位", normalized)
