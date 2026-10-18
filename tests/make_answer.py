"""依任務單產生答案 .lexa（出題用）。

用法（在專案根目錄）：
    python tests/make_answer.py tests/tasks/民法債編總論_純文字_簡易測資.json documents/民法債編總論_純文字_簡易測資.docx
    python tests/make_answer.py --find 無因管理 documents/民法債編總論_純文字_簡易測資.docx   ← 列出某段文字每次出現的位置

會做三件事：
1. 用 io.load_docx 讀 .docx，依任務單的「文字 + 第幾次出現」算出 offset
2. 存成答案 .lexa（預設和任務單同資料夾，檔名為 <任務單>.answer.lexa），可以用程式開起來看高亮
3. 把原文長度與 hash 寫回任務單，讓 check_lexa.py 能確認學生開的是同一份文件
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from check_lexa import find_occurrences, locate, preview, text_sha1  # noqa: E402

MODE_PATH = ROOT / "configs" / "annotation_modes" / "term_definition.json"


def show_occurrences(text: str, needle: str) -> None:
    occ = find_occurrences(text, needle)
    print(f"「{needle}」共出現 {len(occ)} 次：")
    for i, s in enumerate(occ, 1):
        before = preview(text[max(0, s - 15):s], 15)
        after = preview(text[s + len(needle):s + len(needle) + 15], 15)
        print(f"  第 {i:>2} 次  offset {s:>6}：…{before}【{needle}】{after}…")


def main() -> int:
    ap = argparse.ArgumentParser(description="依任務單產生答案 .lexa。")
    ap.add_argument("task", nargs="?", type=Path, help="任務單 JSON")
    ap.add_argument("docx", type=Path, help="要標註的 .docx")
    ap.add_argument("-o", "--output", type=Path, help="答案 .lexa 的輸出路徑")
    ap.add_argument("--find", metavar="文字", help="只列出這段文字在 .docx 原文中每次出現的位置")
    args = ap.parse_args()

    from lexiarbiter.core import config, io
    from lexiarbiter.core.models import Annotation

    doc = io.load_docx(args.docx)
    text = doc.text
    if args.find:
        show_occurrences(text, args.find)
        return 0
    if args.task is None:
        ap.error("需要任務單路徑")

    with open(args.task, "r", encoding="utf-8") as f:
        task = json.load(f)

    concept_ids: dict[str, str] = {}

    def concept(name: str) -> str:
        if name not in concept_ids:
            cid = "C_" + uuid.uuid4().hex[:8]
            concept_ids[name] = cid
            doc.concepts[cid] = name
        return concept_ids[name]

    errors: list[str] = []
    for i, item in enumerate(task.get("items", []), 1):
        spans = {}
        for key in ("term", "explanation"):
            needle = item.get(key)
            if not needle:
                errors.append(f"第 {i} 項缺少 {key}")
                continue
            occ = item.get(f"{key}_occurrence", 1)
            span = locate(text, needle, occ)
            if span is None:
                errors.append(f"第 {i} 項：「{preview(needle)}」找不到第 {occ} 次出現")
                show_occurrences(text, needle)
                continue
            spans[key] = span
            s = span[0]
            print(f"第 {i} 項 {key:<11} offset {s:>6}：…{preview(text[max(0, s - 10):s], 10)}"
                  f"【{preview(needle, 30)}】")
        if len(spans) < 2:
            continue
        (ts, te), (es, ee) = spans["term"], spans["explanation"]
        doc.add_annotation(Annotation(
            start=ts, end=te, labels={"entity": "term"},
            concept_id=concept(item["concept"]),
            explanation_start=es, explanation_end=ee,
            broader_concept_id=concept(item["broader_concept"]),
        ))

    ordered = doc.sorted_annotations()
    for a, b in zip(ordered, ordered[1:]):
        if b.start < a.end:
            errors.append(f"術語「{text[a.start:a.end]}」與「{text[b.start:b.end]}」範圍重疊")

    if errors:
        print("\n任務單有問題，沒有產生答案：")
        for e in errors:
            print(f"  - {e}")
        return 1

    out = args.output or args.task.with_name(args.task.stem + ".answer.lexa")
    io.save_lexa(doc, out, config.load_annotation_mode(MODE_PATH))
    print(f"\n已產生答案：{out}（{len(doc.annotations)} 條標註、{len(doc.concepts)} 個概念）")

    task["document"] = args.docx.name
    task["text_length"] = len(text)
    task["text_sha1"] = text_sha1(text)
    with open(args.task, "w", encoding="utf-8") as f:
        json.dump(task, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"已更新任務單的原文長度與 hash：{args.task}")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
