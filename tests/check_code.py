"""程式自我檢查：不開 GUI，直接測試 core 裡需要你完成或修正的函式。

用法（在專案根目錄）：
    python tests/check_code.py

檢查項目：
1. models.py → Document.annotations_in_range_for_group 的 TODO
2. io.py → export_txt（含 guide.md 附錄的已知問題、解釋欄位不影響匯出）

有任何 FAIL 時 exit code 為 1。
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

MODE_PATH = ROOT / "configs" / "annotation_modes" / "term_definition.json"

results: list[tuple[str, str, str]] = []  # (status, 項目, 說明)


def report(status: str, name: str, detail: str = "") -> None:
    results.append((status, name, detail))
    line = f"[{status}] {name}"
    if detail:
        line += f"\n       {detail}"
    print(line)


# ---------------------------------------------------------------------------
# 1. annotations_in_range_for_group
# ---------------------------------------------------------------------------

def check_overlap(models) -> None:
    print("\n== models.py：Document.annotations_in_range_for_group ==")
    Annotation, Document = models.Annotation, models.Document

    target = Annotation(start=10, end=20, labels={"entity": "term"}, id="target")
    other_group = Annotation(start=10, end=20, labels={"other": "x"}, id="other_group")
    doc = Document(text="x" * 40, annotations=[target, other_group])

    # (說明, 查詢範圍, 應回傳的 id)
    cases = [
        ("部分重疊（左）", (5, 15), {"target"}),
        ("部分重疊（右）", (15, 25), {"target"}),
        ("查詢範圍在標註裡面", (12, 18), {"target"}),
        ("查詢範圍包住標註", (5, 25), {"target"}),
        ("範圍完全相同", (10, 20), {"target"}),
        ("相鄰（左）：查詢的 end == 標註的 start，不算重疊", (0, 10), set()),
        ("相鄰（右）：查詢的 start == 標註的 end，不算重疊", (20, 30), set()),
        ("完全不相交", (0, 5), set()),
    ]
    for name, (s, e), expected in cases:
        try:
            got = {a.id for a in doc.annotations_in_range_for_group(s, e, "entity")}
        except Exception as ex:
            report("FAIL", name, f"發生例外：{ex!r}")
            continue
        if got == expected:
            report("PASS", name)
        else:
            report("FAIL", name, f"查詢 ({s}, {e})：應回傳 {sorted(expected)}，實際回傳 {sorted(got)}")

    try:
        got = doc.annotations_in_range_for_group(10, 20, "entity")
        if any(a.id == "other_group" for a in got):
            report("FAIL", "不同群組的標註不應回傳", "回傳了 group 為 other 的標註")
        else:
            report("PASS", "不同群組的標註不應回傳")
    except Exception as ex:
        report("FAIL", "不同群組的標註不應回傳", f"發生例外：{ex!r}")

    try:
        got = Document(text="x" * 40).annotations_in_range_for_group(0, 40, "entity")
        if got == []:
            report("PASS", "沒有任何標註時回傳空 list")
        else:
            report("FAIL", "沒有任何標註時回傳空 list", f"實際回傳 {got!r}")
    except Exception as ex:
        report("FAIL", "沒有任何標註時回傳空 list", f"發生例外：{ex!r}")


# ---------------------------------------------------------------------------
# 2. export_txt
# ---------------------------------------------------------------------------

def _export(io, mode, doc) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "out.txt"
        io.export_txt(doc, out, mode)
        return out.read_bytes().decode("utf-8")


def check_export(models, io, config) -> None:
    print("\n== io.py：export_txt ==")
    Annotation, Document = models.Annotation, models.Document
    try:
        mode = config.load_annotation_mode(MODE_PATH)
    except Exception as ex:
        report("FAIL", "讀取標註模式設定檔", f"{MODE_PATH} 讀取失敗：{ex!r}")
        return

    text = "前言。術語A的說明。中間文字。術語B的說明。"
    a_start = text.index("術語A")
    b_start = text.index("術語B")

    def make_doc(with_extra_fields: bool) -> Document:
        a = Annotation(start=a_start, end=a_start + 3, labels={"entity": "term"},
                       id="a", concept_id="C_00000001")
        b = Annotation(start=b_start, end=b_start + 3, labels={"entity": "term"}, id="b")
        if with_extra_fields:
            a.explanation_start, a.explanation_end = a_start + 4, a_start + 8
            a.broader_concept_id = "C_00000002"
            b.explanation_start, b.explanation_end = b_start + 4, b_start + 8
        return Document(text=text, annotations=[a, b],
                        concepts={"C_00000001": "概念一", "C_00000002": "上位概念"})

    # 文件開頭沒有標註 → 已知問題會在這裡丟 UnboundLocalError
    name = "文件開頭不是標註時可以匯出（guide.md 附錄的已知問題）"
    try:
        plain = _export(io, mode, make_doc(False))
        report("PASS", name)
    except Exception as ex:
        report("FAIL", name, f"發生例外：{ex!r}（見 io.py → export_txt 第 2 步的 seg_concept_id）")
        plain = None

    if plain is not None:
        name = "沒有綁概念的標註不會沿用上一段的概念"
        expected = "<P>Term=概念一|術語A</P>\r\n<P>Term|術語B</P>"
        if plain == expected:
            report("PASS", name)
        else:
            report("FAIL", name, f"應輸出 {expected!r}\n       實際輸出 {plain!r}")

    name = "加了解釋與上位概念後，匯出的 .txt 和只標術語時完全一樣"
    try:
        extra = _export(io, mode, make_doc(True))
    except Exception as ex:
        report("FAIL", name, f"發生例外：{ex!r}")
        return
    if plain is None:
        report("FAIL", name, "無法比較：只標術語的版本匯出失敗")
    elif extra == plain:
        report("PASS", name)
    else:
        report("FAIL", name, f"只標術語：{plain!r}\n       加了解釋：{extra!r}")


# ---------------------------------------------------------------------------

def main() -> int:
    print(f"檢查專案：{ROOT}")
    try:
        from lexiarbiter.core import config, io, models
    except Exception as ex:
        report("FAIL", "import lexiarbiter.core", f"{ex!r}（是否在專案根目錄、裝好 requirements.txt？）")
        return 1

    check_overlap(models)
    check_export(models, io, config)

    n_fail = sum(1 for s, _, _ in results if s == "FAIL")
    n_pass = sum(1 for s, _, _ in results if s == "PASS")
    print(f"\n結果：PASS {n_pass}　FAIL {n_fail}")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
