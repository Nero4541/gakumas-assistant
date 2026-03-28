from __future__ import annotations

import argparse
import json
import keyword
import re
from collections import OrderedDict, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

import yaml


CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")


@dataclass
class FieldDef:
    name: str
    annotation: str
    default_kind: str  # "list" | "none"


@dataclass
class ClassDef:
    name: str
    fields: List[FieldDef]


def pascal_case(name: str) -> str:
    if not name:
        return "Unnamed"
    if "_" in name or "-" in name or " " in name:
        parts = re.split(r"[^0-9A-Za-z]+", name)
        return "".join(p[:1].upper() + p[1:] for p in parts if p) or "Unnamed"
    return name[:1].upper() + name[1:]


def sanitize_field_name(name: str) -> str:
    # Source keys are already valid identifiers in current dataset.
    if not name:
        return "field_"
    if keyword.iskeyword(name):
        return f"{name}_"
    return name


def preprocess_yaml_text(text: str) -> str:
    text = CONTROL_CHAR_RE.sub("", text)
    return text.replace("\t", "    ")


def load_yaml_rows(path: Path) -> List[Dict[str, Any]]:
    text = preprocess_yaml_text(path.read_text(encoding="utf-8"))
    data = yaml.load(text, Loader=yaml.CSafeLoader)
    if data is None:
        return []
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    return []


def load_localization_rows(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get("data", [])
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def infer_primitive_type(values: List[Any]) -> str | None:
    kinds = set(type(v) for v in values if v is not None)
    if not kinds:
        return "Any"
    if kinds == {bool}:
        return "bool"
    if kinds == {int}:
        return "int"
    if kinds in ({int, float}, {float}):
        return "float"
    if kinds == {str}:
        return "str"
    return None


def ensure_unique_name(candidate: str, used_names: set[str]) -> str:
    if candidate not in used_names:
        used_names.add(candidate)
        return candidate
    idx = 2
    while f"{candidate}{idx}" in used_names:
        idx += 1
    unique_name = f"{candidate}{idx}"
    used_names.add(unique_name)
    return unique_name


def infer_object_schema(
    rows: List[Dict[str, Any]],
    class_name: str,
    used_names: set[str],
) -> List[ClassDef]:
    ordered_keys: OrderedDict[str, None] = OrderedDict()
    key_values: Dict[str, List[Any]] = defaultdict(list)

    for row in rows:
        for key, value in row.items():
            if key not in ordered_keys:
                ordered_keys[key] = None
            key_values[key].append(value)

    nested_defs: List[ClassDef] = []
    field_defs: List[FieldDef] = []

    for raw_key in ordered_keys:
        field_name = sanitize_field_name(raw_key)
        values = key_values.get(raw_key, [])
        annotation, field_nested_defs, default_kind = infer_field_type(
            values=values,
            owner_class_name=class_name,
            field_name=field_name,
            used_names=used_names,
        )
        nested_defs.extend(field_nested_defs)
        field_defs.append(
            FieldDef(
                name=field_name,
                annotation=annotation,
                default_kind=default_kind,
            )
        )

    nested_defs.append(ClassDef(name=class_name, fields=field_defs))
    return nested_defs


def infer_field_type(
    values: List[Any],
    owner_class_name: str,
    field_name: str,
    used_names: set[str],
) -> Tuple[str, List[ClassDef], str]:
    non_null = [v for v in values if v is not None]
    if not non_null:
        return "Any", [], "none"

    primitive = infer_primitive_type(non_null)
    if primitive:
        return primitive, [], "none"

    if all(isinstance(v, dict) for v in non_null):
        nested_name = ensure_unique_name(
            f"{owner_class_name}{pascal_case(field_name)}",
            used_names,
        )
        nested_defs = infer_object_schema(non_null, nested_name, used_names)
        return nested_name, nested_defs, "none"

    if all(isinstance(v, list) for v in non_null):
        elements = [item for row in non_null for item in row if item is not None]
        if not elements:
            return "List[Any]", [], "list"

        elem_primitive = infer_primitive_type(elements)
        if elem_primitive:
            return f"List[{elem_primitive}]", [], "list"

        if all(isinstance(item, dict) for item in elements):
            nested_name = ensure_unique_name(
                f"{owner_class_name}{pascal_case(field_name)}Item",
                used_names,
            )
            nested_defs = infer_object_schema(elements, nested_name, used_names)
            return f"List[{nested_name}]", nested_defs, "list"

        return "List[Any]", [], "list"

    return "Any", [], "none"


def render_class_defs(class_defs: List[ClassDef]) -> str:
    lines: List[str] = []
    for class_def in class_defs:
        lines.append("@dataclass")
        lines.append(f"class {class_def.name}:")
        if not class_def.fields:
            lines.append("    pass")
            lines.append("")
            continue
        for field_def in class_def.fields:
            if field_def.default_kind == "list":
                lines.append(
                    f"    {field_def.name}: {field_def.annotation} = field(default_factory=list)"
                )
            else:
                lines.append(f"    {field_def.name}: {field_def.annotation} = None")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def build_module_code(
    table_name: str,
    data_rows: List[Dict[str, Any]],
    loc_rows: List[Dict[str, Any]],
) -> str:
    used_names = {table_name, f"{table_name}Localization"}
    data_defs = infer_object_schema(data_rows, table_name, used_names)

    loc_defs: List[ClassDef] = []
    has_localization = bool(loc_rows)
    if has_localization:
        # Use a separate name pool branch to keep class names stable/readable.
        loc_used = set(used_names)
        loc_defs = infer_object_schema(loc_rows, f"{table_name}Localization", loc_used)
        # Keep only localization-specific names; main class names are already in data_defs.
        existing_data_names = {c.name for c in data_defs}
        loc_defs = [c for c in loc_defs if c.name not in existing_data_names]

    imports = [
        "from __future__ import annotations",
        "",
        "from dataclasses import dataclass, field",
        "from typing import Any, List",
        "",
        "",
    ]
    body = render_class_defs(data_defs + loc_defs)

    if has_localization:
        # Append localization pointer field to main class.
        # We patch textually to avoid rebuilding class objects.
        marker = f"class {table_name}:\n"
        idx = body.find(marker)
        if idx != -1:
            # Insert the pointer at end of class block.
            class_start = idx + len(marker)
            next_dataclass = body.find("\n@dataclass\nclass ", class_start)
            class_block_end = len(body) if next_dataclass == -1 else next_dataclass
            class_block = body[class_start:class_block_end]
            if f"    localization: {table_name}Localization = None\n" not in class_block:
                class_block = (
                    class_block.rstrip("\n")
                    + f"\n    localization: {table_name}Localization = None\n"
                )
                body = body[:class_start] + class_block + body[class_block_end:]

    header = [
        '"""',
        "Auto-generated from assets/gakumasu-diff and localization JSON.",
        "Do not edit manually; regenerate via devtools/generate_game_database_schemas.py.",
        '"""',
        "",
    ]
    return "\n".join(header + imports) + body


def table_analysis(
    table_name: str,
    data_rows: List[Dict[str, Any]],
    loc_rows: List[Dict[str, Any]],
) -> Dict[str, Any]:
    field_stats: OrderedDict[str, Dict[str, Any]] = OrderedDict()
    row_count = len(data_rows)
    for row in data_rows:
        for key, value in row.items():
            if key not in field_stats:
                field_stats[key] = {"count": 0, "types": defaultdict(int)}
            field_stats[key]["count"] += 1
            t = type(value).__name__
            if isinstance(value, list):
                if not value:
                    t = "list(empty)"
                elif isinstance(value[0], dict):
                    t = "list(dict)"
                else:
                    t = f"list({type(value[0]).__name__})"
            elif isinstance(value, dict):
                t = "dict"
            field_stats[key]["types"][t] += 1

    nested_dict_fields = sum(
        1
        for s in field_stats.values()
        if any(t in ("dict", "list(dict)") for t in s["types"].keys())
    )

    id_values = [row.get("id") for row in data_rows if "id" in row]
    id_unique = len(id_values) == len(set(id_values)) if id_values else None
    duplicate_id_count = (
        len(id_values) - len(set(id_values))
        if id_values
        else 0
    )

    return {
        "table": table_name,
        "rows": row_count,
        "fields": len(field_stats),
        "nested_fields": nested_dict_fields,
        "loc_rows": len(loc_rows),
        "id_unique": id_unique,
        "duplicate_id_count": duplicate_id_count,
        "field_stats": field_stats,
    }


def build_analysis_markdown(analysis_rows: List[Dict[str, Any]]) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total_tables = len(analysis_rows)
    total_rows = sum(x["rows"] for x in analysis_rows)
    localized_tables = sum(1 for x in analysis_rows if x["loc_rows"] > 0)
    duplicate_id_tables = sum(
        1 for x in analysis_rows if x["id_unique"] is False
    )

    lines: List[str] = []
    lines.append("# Gakumas 游戏数据库格式分析")
    lines.append("")
    lines.append(f"- 生成时间: `{now}`")
    lines.append(f"- YAML 表总数: `{total_tables}`")
    lines.append(f"- YAML 总记录数: `{total_rows}`")
    lines.append(f"- 含本地化 JSON 的表数: `{localized_tables}`")
    lines.append(f"- `id` 非唯一表数: `{duplicate_id_tables}`")
    lines.append("")
    lines.append("## 总览")
    lines.append("")
    lines.append("| 表名 | 记录数 | 字段数 | 嵌套字段数 | 本地化记录数 | id唯一 | id重复数 |")
    lines.append("| --- | ---: | ---: | ---: | ---: | --- | ---: |")
    for row in sorted(analysis_rows, key=lambda x: x["table"]):
        id_unique = (
            "N/A"
            if row["id_unique"] is None
            else ("Yes" if row["id_unique"] else "No")
        )
        lines.append(
            f"| {row['table']} | {row['rows']} | {row['fields']} | {row['nested_fields']} | "
            f"{row['loc_rows']} | {id_unique} | {row['duplicate_id_count']} |"
        )

    lines.append("")
    lines.append("## 字段详情")
    lines.append("")
    for row in sorted(analysis_rows, key=lambda x: x["table"]):
        lines.append(f"### {row['table']}")
        lines.append("")
        lines.append(
            f"- 记录数: `{row['rows']}`，字段数: `{row['fields']}`，本地化记录: `{row['loc_rows']}`"
        )
        lines.append("")
        lines.append("| 字段 | 出现比例 | 推断类型分布 |")
        lines.append("| --- | ---: | --- |")
        for field, stat in row["field_stats"].items():
            ratio = f"{stat['count']}/{row['rows']}" if row["rows"] else "0/0"
            dist = ", ".join(
                f"{k}:{v}" for k, v in sorted(stat["types"].items(), key=lambda x: x[0])
            )
            lines.append(f"| {field} | {ratio} | {dist} |")
        lines.append("")

    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing dataclass files under src/entity/Game/Database",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    yaml_dir = root / "assets" / "gakumasu-diff"
    loc_dir = root / "assets" / "GakumasTranslationData" / "local-files" / "masterTrans"
    out_dir = root / "src" / "entity" / "Game" / "Database"
    docs_dir = root / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)

    yaml_files = sorted(yaml_dir.glob("*.yaml"))
    generated = 0
    skipped = 0

    analysis_rows: List[Dict[str, Any]] = []

    for yaml_file in yaml_files:
        table_name = yaml_file.stem
        out_file = out_dir / f"{table_name}.py"
        loc_file = loc_dir / f"{table_name}.json"

        data_rows = load_yaml_rows(yaml_file)
        loc_rows = load_localization_rows(loc_file)
        analysis_rows.append(table_analysis(table_name, data_rows, loc_rows))

        if out_file.exists() and not args.overwrite:
            skipped += 1
            continue

        code = build_module_code(table_name, data_rows, loc_rows)
        out_file.write_text(code, encoding="utf-8")
        generated += 1

    md = build_analysis_markdown(analysis_rows)
    (docs_dir / "game_database_format_analysis.md").write_text(md, encoding="utf-8")

    print(
        f"Done. total_yaml={len(yaml_files)}, generated={generated}, skipped={skipped}, "
        "doc=docs/game_database_format_analysis.md"
    )


if __name__ == "__main__":
    main()
