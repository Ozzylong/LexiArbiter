"""把答案 .lexa 轉成任務單（出題用）。

用法（在專案根目錄）：
    python tests/lexa_to_task.py 答案.lexa
    python tests/lexa_to_task.py 答案.lexa -o 輸出資料夾        ← 預設輸出到 tests/tasks/

會產生兩個檔案（檔名和 .lexa 相同）：
- <名稱>.md   ：給學生看的文字任務單，逐筆寫明選取範圍、邊界、概念要新建還是選既有
- <名稱>.json ：給 check_lexa.py --task 比對用
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from check_lexa import find_occurrences, preview, text_sha1

TASKS_DIR = Path(__file__).resolve().parent / "tasks"

RULES = """\
## 標註規則

1. 術語附近沒有解釋 → **解釋範圍填術語本身**（選取和術語完全相同的範圍）。
2. 最上層的概念沒有更上層 → **上位概念填自己**（選這筆自己的概念）。
3. 以上兩種情況都**不能留空**，也**不能**另外建立「無」「沒有」這類的假概念。
4. 選取範圍要和任務單**完全一致**。頭尾的空白、標點要不要選進去，請看每筆寫的「前一個字／後一個字」。
"""


def char_name(text: str, pos: int) -> str:
    """text[pos] 的可讀名稱，用來說明選取邊界外的那個字。"""
    if pos < 0 or pos >= len(text):
        return "（文件邊界）"
    ch = text[pos]
    names = {"\n": "換行", "\r": "換行", "\t": "Tab", " ": "半形空白", "　": "全形空白"}
    return names.get(ch, f"`{ch}`")


def context(text: str, s: int, e: int, width: int = 12) -> str:
    before = preview(text[max(0, s - width):s], width)
    after = preview(text[e:e + width], width)
    inner = preview(text[s:e], 30)
    return f"`…{before}【{inner}】{after}…`"


def occurrence_of(text: str, s: int, e: int) -> tuple[int, int]:
    """text[s:e] 是那段文字第幾次出現、總共出現幾次。"""
    occ = find_occurrences(text, text[s:e])
    return occ.index(s) + 1, len(occ)


def convert(data: dict, task_json_name: str) -> tuple[dict, str]:
    text = data["text"]
    concepts = data.get("concepts") or {}
    anns = sorted(data.get("annotations") or [], key=lambda a: (a["start"], a["end"]))
    doc_name = (data.get("source") or {}).get("filename", "")

    items: list[dict] = []
    md: list[str] = [
        f"# 標註任務單：{Path(doc_name).stem or task_json_name}",
        "",
        f"- 文件：用你的程式開啟 `{doc_name}`（原文共 {len(text)} 字）。",
        f"- 共 {len(anns)} 筆，請**依順序**標註；概念要「新建」還是「選擇既有」，是依這個順序判斷的。",
        "- 「第 k 次出現」是指這段文字從原文開頭數起第幾次出現（表格文字解析等段落也算）。",
        "- 前後文中 `【】` 框起來的就是要選取的範圍（`【】` 本身不在原文裡）；`↵` 表示換行、`⇥` 表示 Tab。",
        "",
        RULES,
        "## 做完之後",
        "",
        "存檔後在專案根目錄執行，確認結果沒有 FAIL：",
        "",
        "```bash",
        f"python tests/check_lexa.py 你的檔案.lexa --task tests/tasks/{task_json_name}.json",
        "```",
        "",
        "---",
    ]

    created: dict[str, int] = {}  # 概念名稱 → 在第幾筆建立

    def concept_note(name: str, i: int) -> str:
        if name in created:
            return f"選擇既有，第 {created[name]} 筆建立的"
        created[name] = i
        return "新建"

    for i, a in enumerate(anns, 1):
        s, e = a["start"], a["end"]
        term = text[s:e]
        t_occ, t_total = occurrence_of(text, s, e)
        item = {"term": term, "term_occurrence": t_occ}

        md += ["", f"## 第 {i} 筆：「{preview(term)}」", ""]
        md.append(f"- **術語**：「{term}」，第 {t_occ} 次出現（共 {t_total} 次）")
        md.append(f"  - 前後文：{context(text, s, e)}")

        es, ee = a.get("explanation_start"), a.get("explanation_end")
        if es is None or ee is None:
            md.append("- **解釋**：（答案檔沒有解釋）")
        else:
            item["explanation"] = text[es:ee]
            item["explanation_occurrence"] = occurrence_of(text, es, ee)[0]
            if (es, ee) == (s, e):
                md.append("- **解釋**：與術語相同（附近沒有解釋 → 填術語本身）")
            else:
                exp = text[es:ee]
                head, tail = preview(exp[:4], 4), preview(exp[-4:], 4)
                md.append(f"- **解釋**：共 {ee - es} 字，從 `{head}` 開始、到 `{tail}` 結束；"
                          f"前一個字是{char_name(text, es - 1)}，後一個字是{char_name(text, ee)}")
                md.append(f"  - 前後文：{context(text, es, ee)}")
                md.append(f"  > {preview(exp, len(exp))}")

        cname = concepts.get(a.get("concept_id"))
        bname = concepts.get(a.get("broader_concept_id"))
        if cname is None:
            md.append("- **概念**：（答案檔沒有概念）")
        else:
            item["concept"] = cname
            md.append(f"- **概念**：「{cname}」（{concept_note(cname, i)}）")
        if bname is None:
            md.append("- **上位概念**：（答案檔沒有上位概念）")
        else:
            item["broader_concept"] = bname
            if a.get("broader_concept_id") == a.get("concept_id"):
                md.append(f"- **上位概念**：「{bname}」（最上層概念 → 填自己，選這筆自己的概念）")
            else:
                md.append(f"- **上位概念**：「{bname}」（{concept_note(bname, i)}）")

        items.append(item)

    task = {
        "document": doc_name,
        "text_length": len(text),
        "text_sha1": text_sha1(text),
        "items": items,
    }
    return task, "\n".join(md) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="把答案 .lexa 轉成任務單（.md 給學生、.json 給 check_lexa.py）。")
    ap.add_argument("lexa", type=Path, help="答案 .lexa")
    ap.add_argument("-o", "--output-dir", type=Path, default=TASKS_DIR, help="輸出資料夾（預設 tests/tasks/）")
    args = ap.parse_args()

    with open(args.lexa, "r", encoding="utf-8") as f:
        data = json.load(f)
    if data.get("format") != "lexa":
        print(f"{args.lexa} 不是 .lexa 格式")
        return 1

    name = args.lexa.stem
    task, md = convert(data, name)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / f"{name}.json"
    md_path = args.output_dir / f"{name}.md"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(task, f, ensure_ascii=False, indent=2)
        f.write("\n")
    md_path.write_text(md, encoding="utf-8")
    print(f"已產生 {len(task['items'])} 筆任務：\n  {md_path}\n  {json_path}")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(main())
