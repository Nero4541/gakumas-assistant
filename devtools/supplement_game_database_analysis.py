from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml


CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")


def preprocess_yaml_text(text: str) -> str:
    text = CONTROL_CHAR_RE.sub("", text)
    return text.replace("\t", "    ")


def load_yaml_rows(path: Path) -> List[Dict[str, Any]]:
    text = preprocess_yaml_text(path.read_text(encoding="utf-8"))
    data = yaml.load(text, Loader=yaml.CSafeLoader)
    if not isinstance(data, list):
        return []
    return [row for row in data if isinstance(row, dict)]


def field_type_name(value: Any) -> str:
    if isinstance(value, list):
        if not value:
            return "list(empty)"
        first = value[0]
        return f"list({type(first).__name__})"
    if isinstance(value, dict):
        return "dict"
    return type(value).__name__


def field_stats(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    stats: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        for k, v in row.items():
            if k not in stats:
                stats[k] = {"count": 0, "types": Counter()}
            stats[k]["count"] += 1
            stats[k]["types"][field_type_name(v)] += 1
    return stats


def extract_relation_field(field_name: str) -> Optional[Tuple[str, bool]]:
    if field_name == "id":
        return None

    m = re.match(r"^(.+?)Ids\d+$", field_name)
    if m:
        return m.group(1), True

    if field_name.endswith("Ids"):
        stem = field_name[:-3]
        if stem:
            return stem, True

    m = re.match(r"^(.+?)Id\d+$", field_name)
    if m:
        return m.group(1), False

    if field_name.endswith("Id"):
        stem = field_name[:-2]
        if stem:
            return stem, False

    return None


def split_camel_tokens(name: str) -> List[str]:
    return re.findall(r"[A-Z]+(?=[A-Z][a-z]|[0-9]|$)|[A-Z]?[a-z0-9]+", name)


def candidate_tables_from_stem(stem: str, table_set: set[str]) -> List[str]:
    tokens = split_camel_tokens(stem)
    if not tokens:
        return []
    candidates: List[str] = []
    for i in range(len(tokens)):
        candidate = "".join(t[:1].upper() + t[1:] for t in tokens[i:])
        if candidate in table_set and candidate not in candidates:
            candidates.append(candidate)
    return candidates


def iter_relation_values(row: Dict[str, Any], field_name: str, is_list: bool) -> List[str]:
    value = row.get(field_name)
    if value is None:
        return []
    if is_list:
        if not isinstance(value, list):
            return []
        return [v for v in value if isinstance(v, str) and v]
    if isinstance(value, str) and value:
        return [value]
    return []


def pick_relation_target(
    rows: List[Dict[str, Any]],
    field_name: str,
    is_list: bool,
    candidates: List[str],
    id_sets: Dict[str, set[str]],
) -> Optional[Tuple[str, int, int, float, str]]:
    values: List[str] = []
    for row in rows:
        values.extend(iter_relation_values(row, field_name, is_list))
        if len(values) >= 1000:
            break
    if not values:
        return None

    best: Optional[Tuple[str, int, int, float, str]] = None
    for table in candidates:
        target_ids = id_sets.get(table, set())
        if not target_ids:
            continue
        hits = sum(1 for v in values if v in target_ids)
        if hits == 0:
            continue
        total = len(values)
        ratio = hits / total if total else 0.0
        if ratio >= 0.9 and hits >= 20:
            confidence = "high"
        elif ratio >= 0.5 and hits >= 10:
            confidence = "medium"
        elif ratio >= 0.2 and hits >= 5:
            confidence = "low"
        else:
            continue

        candidate = (table, hits, total, ratio, confidence)
        if best is None:
            best = candidate
            continue
        if (hits, ratio) > (best[1], best[3]):
            best = candidate
    return best


def infer_field_usage(
    field_name: str,
    type_dist: Counter,
    relation: Optional[Tuple[str, int, int, float, str]],
) -> Tuple[str, str, str]:
    dominant_type = type_dist.most_common(1)[0][0] if type_dist else "unknown"

    if relation is not None:
        target, hits, total, ratio, conf = relation
        return (
            "关系键",
            f"外键，指向 `{target}`",
            f"命中 {hits}/{total} ({ratio:.1%}), {conf}",
        )

    lower = field_name.lower()

    if field_name == "id":
        return ("主键", "业务主标识（部分表非唯一）", "命名规则")
    if field_name in ("name", "title", "firstName", "lastName"):
        return ("显示文本", "展示名称/标题", "命名规则")
    if "description" in lower:
        return ("显示文本", "描述文本（UI/提示/条目说明）", "命名规则")
    if "assetid" in lower:
        return ("资源键", "客户端资源ID（图像/音频/动作/3D）", "命名规则")
    if lower.endswith("type") or lower.endswith("types"):
        return ("枚举", "类型枚举/分类标签", "命名规则")
    if lower.endswith("conditionsetid"):
        return ("条件键", "条件集合ID（解锁/显示/可用）", "命名规则")
    if lower.endswith("starttime") or lower.endswith("endtime") or lower.endswith("time"):
        return ("时间", "时间点/生效区间", "命名规则")
    if lower.startswith("is") or lower.startswith("has"):
        return ("开关", "布尔开关（功能/状态/限制）", "命名规则")
    if "permil" in lower or "rate" in lower:
        return ("数值参数", "比例/概率参数", "命名规则")
    if "count" in lower or "quantity" in lower:
        return ("数值参数", "次数/数量参数", "命名规则")
    if "level" in lower or "rank" in lower or "step" in lower or "phase" in lower:
        return ("进度参数", "等级/阶段/流程节点", "命名规则")
    if "order" == lower or lower.endswith("order"):
        return ("排序", "展示或处理排序", "命名规则")
    if dominant_type.startswith("list("):
        return ("集合", "列表字段（复数值/子结构）", "类型分布")
    if dominant_type == "dict":
        return ("结构体", "嵌套结构字段", "类型分布")
    if dominant_type in ("int", "float", "bool"):
        return ("数值参数", "数值/状态参数", "类型分布")
    return ("未分类", "用途不明，需结合玩法验证", "弱规则推断")


def build_supplement_markdown(
    table_rows: Dict[str, List[Dict[str, Any]]],
    all_field_stats: Dict[str, Dict[str, Dict[str, Any]]],
) -> str:
    table_set = set(table_rows.keys())
    id_sets: Dict[str, set[str]] = {}
    for table, rows in table_rows.items():
        ids = {str(row["id"]) for row in rows if isinstance(row.get("id"), str) and row.get("id")}
        id_sets[table] = ids

    relation_map: Dict[Tuple[str, str], Tuple[str, int, int, float, str]] = {}
    relation_rows: List[Tuple[str, str, str, int, int, float, str]] = []
    edge_agg: Dict[Tuple[str, str], Dict[str, Any]] = {}

    for table, rows in table_rows.items():
        stats = all_field_stats.get(table, {})
        for field_name in stats.keys():
            rel_field = extract_relation_field(field_name)
            if rel_field is None:
                continue
            stem, is_list = rel_field
            candidates = candidate_tables_from_stem(stem, table_set)
            if not candidates:
                continue
            picked = pick_relation_target(rows, field_name, is_list, candidates, id_sets)
            if picked is None:
                continue
            target, hits, total, ratio, conf = picked
            relation_map[(table, field_name)] = picked
            relation_rows.append((table, field_name, target, hits, total, ratio, conf))
            edge = edge_agg.setdefault((table, target), {"score": 0, "fields": []})
            edge["score"] += hits
            edge["fields"].append(field_name)

    # Build a compact core graph from highest-score relations.
    sorted_edges = sorted(edge_agg.items(), key=lambda x: x[1]["score"], reverse=True)
    graph_edges = sorted_edges[:80]

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines: List[str] = []
    lines.append("## 字段用途解析与关系图（推测）")
    lines.append("")
    lines.append(f"- 生成时间: `{now}`")
    lines.append("- 本节基于字段命名、类型分布、跨表ID命中率自动推断。")
    lines.append("- 结论属于工程推测，不等同于官方字段文档。")
    lines.append("")
    lines.append("### 外部术语锚点（互联网资料）")
    lines.append("")
    lines.append("- 官方站 `Road to A+` 明确出现 `PLv`、`SPレッスン`、`Pドリンク`、`最終試験スコア`，用于解释 `ProducerLevel / ProduceDrink / Exam*` 相关表。")
    lines.append("- App Store 介绍明确描述“通过反复 `プロデュース` 提升能力并通过 `試験`”，用于解释 `Produce*` / `Exam*` 主链路。")
    lines.append("- CEDEC2024 官方会话说明本作存在“卡牌与卡组平衡”及“最新 `マスターデータ` 适配”，用于解释 `ProduceCard*` / `Effect*` / `Trigger*` 表的系统性。")
    lines.append("- 参考链接：")
    lines.append("  - https://gakuen.idolmaster-official.jp/road-to-a-plus/")
    lines.append("  - https://apps.apple.com/jp/app/id6446659989")
    lines.append("  - https://cedec.cesa.or.jp/2024/session/detail/s66040e2aeca6e/")
    lines.append("")
    lines.append("### 关系图（Mermaid，Top 80 边）")
    lines.append("")
    lines.append("```mermaid")
    lines.append("graph LR")
    for (src, dst), payload in graph_edges:
        fields = payload["fields"][:3]
        label = ", ".join(fields)
        if len(payload["fields"]) > 3:
            label += ", ..."
        label = label.replace('"', "'")
        lines.append(f'  {src} -->|"{label}"| {dst}')
    lines.append("```")
    lines.append("")
    lines.append("### 关系清单（高/中置信）")
    lines.append("")
    lines.append("| 源表 | 字段 | 目标表 | 命中 | 命中率 | 置信度 |")
    lines.append("| --- | --- | --- | ---: | ---: | --- |")
    for src, field, dst, hits, total, ratio, conf in sorted(
        [r for r in relation_rows if r[6] in ("high", "medium")],
        key=lambda x: (x[0], x[1]),
    ):
        lines.append(f"| {src} | {field} | {dst} | {hits}/{total} | {ratio:.1%} | {conf} |")
    lines.append("")
    lines.append("### 字段用途推测（按表）")
    lines.append("")

    for table in sorted(table_rows.keys()):
        stats = all_field_stats.get(table, {})
        if not stats:
            continue
        lines.append(f"#### {table}")
        lines.append("")
        lines.append("| 字段 | 主类型 | 分类 | 用途推测 | 关系目标 | 依据 |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for field_name, payload in stats.items():
            type_dist: Counter = payload["types"]
            dominant_type = type_dist.most_common(1)[0][0] if type_dist else "unknown"
            relation = relation_map.get((table, field_name))
            category, usage, evidence = infer_field_usage(field_name, type_dist, relation)
            relation_target = relation[0] if relation else ""
            lines.append(
                f"| {field_name} | {dominant_type} | {category} | {usage} | {relation_target} | {evidence} |"
            )
        lines.append("")

    return "\n".join(lines) + "\n"


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    yaml_dir = root / "assets" / "gakumasu-diff"
    doc_file = root / "docs" / "game_database_format_analysis.md"

    table_rows: Dict[str, List[Dict[str, Any]]] = {}
    all_stats: Dict[str, Dict[str, Dict[str, Any]]] = {}

    for yaml_file in sorted(yaml_dir.glob("*.yaml")):
        table = yaml_file.stem
        rows = load_yaml_rows(yaml_file)
        table_rows[table] = rows
        all_stats[table] = field_stats(rows)

    supplement = build_supplement_markdown(table_rows, all_stats)
    content = doc_file.read_text(encoding="utf-8")

    marker = "## 字段详情"
    insert_pos = content.find(marker)
    if insert_pos == -1:
        raise RuntimeError("Cannot find marker '## 字段详情' in analysis doc.")

    start_marker = "## 字段用途解析与关系图（推测）"
    old_start = content.find(start_marker)
    if old_start != -1 and old_start < insert_pos:
        content = content[:old_start] + content[insert_pos:]
        insert_pos = content.find(marker)

    new_content = content[:insert_pos] + supplement + "\n" + content[insert_pos:]
    doc_file.write_text(new_content, encoding="utf-8")
    print("supplemented docs/game_database_format_analysis.md")


if __name__ == "__main__":
    main()
