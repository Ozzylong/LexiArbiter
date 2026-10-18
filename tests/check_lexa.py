""".lexa 檢查：確認存出來的標註符合 guide.md「目標：要存進去的資料」的格式，並可和任務單比對。

用法（在專案根目錄）：
    python tests/check_lexa.py 你的檔案.lexa
    python tests/check_lexa.py 你的檔案.lexa --task tests/tasks/範例任務.json
    python tests/check_lexa.py 作業資料夾/ --task tests/tasks/範例任務.json   ← 資料夾內每個 .lexa 都檢查，最後印總表

只讀 .lexa 的 JSON，不會 import 也不會執行 lexiarbiter 的程式碼。
比對任務單時以「文字內容」與「概念名稱」比對，亂數產生的 id 不影響結果。
有任何 FAIL 時 exit code 為 1。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

TERM_LABELS = {"entity": "term"}
CONCEPT_ID_RE = re.compile(r"^C_[0-9a-f]{8}$")
# 比對範圍時，只差頭尾這些字元算 WARN（手動選取常多選或少選）
EDGE_CHARS = " \t\r\n　，。、；：！？「」『』（）()[]【】…,.;:!?\"'"


# ---------------------------------------------------------------------------
# 共用工具（make_answer.py 也會用到）
# ---------------------------------------------------------------------------

def text_sha1(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def find_occurrences(text: str, needle: str) -> list[int]:
    out: list[int] = []
    i = text.find(needle)
    while i != -1:
        out.append(i)
        i = text.find(needle, i + 1)
    return out


def locate(text: str, needle: str, occurrence: int) -> tuple[int, int] | None:
    """needle 在 text 中第 occurrence 次（從 1 開始）出現的 (start, end)。"""
    occ = find_occurrences(text, needle)
    if not needle or occurrence < 1 or occurrence > len(occ):
        return None
    s = occ[occurrence - 1]
    return s, s + len(needle)


def preview(text: str, limit: int = 40) -> str:
    """印出用：換行改成可見符號、過長截斷。"""
    t = text.replace("\r", "").replace("\n", "↵").replace("\t", "⇥")
    return t if len(t) <= limit else t[:limit] + "…"


# ---------------------------------------------------------------------------

class Report:
    def __init__(self) -> None:
        self.counts = {"PASS": 0, "WARN": 0, "FAIL": 0}

    def add(self, status: str, msg: str, detail: str = "") -> None:
        self.counts[status] += 1
        print(f"[{status}] {msg}")
        if detail:
            for line in detail.splitlines():
                print(f"       {line}")

    def ok(self, msg: str, detail: str = "") -> None:
        self.add("PASS", msg, detail)

    def warn(self, msg: str, detail: str = "") -> None:
        self.add("WARN", msg, detail)

    def fail(self, msg: str, detail: str = "") -> None:
        self.add("FAIL", msg, detail)


def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _span_text(text: str, s, e) -> str:
    return text[s:e] if _is_int(s) and _is_int(e) else ""


def _ann_name(text: str, a: dict) -> str:
    return f"標註「{preview(_span_text(text, a.get('start'), a.get('end')))}」(start={a.get('start')})"


# ---------------------------------------------------------------------------
# 規則檢查
# ---------------------------------------------------------------------------

def check_rules(data: dict, rep: Report) -> list[dict]:
    """回傳範圍合法、可以拿去和任務單比對的標註。"""
    print("\n-- 格式規則 --")
    text = data.get("text", "")
    concepts = data.get("concepts") or {}
    anns = data.get("annotations") or []
    n = len(text)

    if not anns:
        rep.fail("檔案裡沒有任何標註")
        return []
    rep.ok(f"共 {len(anns)} 條標註、{len(concepts)} 個概念")

    valid: list[dict] = []
    bad_range, bad_label, bad_exp, bad_cid = [], [], [], []
    warn_cid_fmt, warn_same = [], []
    for a in anns:
        name = _ann_name(text, a)
        s, e = a.get("start"), a.get("end")
        if not (_is_int(s) and _is_int(e) and 0 <= s < e <= n):
            bad_range.append(f"{name}：start={s}, end={e}（文件長度 {n}）")
            continue
        valid.append(a)

        if a.get("labels") != TERM_LABELS:
            bad_label.append(f"{name}：labels={a.get('labels')}")

        es, ee = a.get("explanation_start"), a.get("explanation_end")
        if es is None and ee is None:
            bad_exp.append(f"{name}：沒有解釋段落")
        elif not (_is_int(es) and _is_int(ee) and 0 <= es < ee <= n):
            bad_exp.append(f"{name}：explanation_start={es}, explanation_end={ee}")

        for key, label in (("concept_id", "概念"), ("broader_concept_id", "上位概念")):
            cid = a.get(key)
            if cid is None:
                bad_cid.append(f"{name}：沒有{label}（{key} 是 null）")
            elif not isinstance(cid, str) or cid not in concepts:
                bad_cid.append(f"{name}：{key}={cid!r} 不在 concepts 裡")
            elif not CONCEPT_ID_RE.match(str(cid)):
                warn_cid_fmt.append(f"{name}：{key}={cid!r}")
        if a.get("concept_id") is not None and a.get("concept_id") == a.get("broader_concept_id"):
            warn_same.append(name)

    def emit(items: list[str], ok_msg: str, bad_msg: str, warn_only: bool = False) -> None:
        if not items:
            rep.ok(ok_msg)
        elif warn_only:
            rep.warn(bad_msg, "\n".join(items))
        else:
            rep.fail(bad_msg, "\n".join(items))

    emit(bad_range, "所有標註的範圍都在文件內", "標註範圍不合法")
    emit(bad_label, 'labels 都是 {"entity": "term"}', 'labels 不是 {"entity": "term"}')
    emit(bad_exp, "每條標註都有合法的解釋範圍", "解釋範圍缺少或不合法")
    emit(bad_cid, "concept_id、broader_concept_id 都存在於 concepts", "概念 id 缺少或找不到")
    emit(warn_cid_fmt, "概念 id 格式為 C_ + 8 碼", '概念 id 不是 "C_" + uuid.uuid4().hex[:8] 的格式', warn_only=True)
    emit(warn_same, "概念與上位概念不是同一個", "概念與上位概念是同一個", warn_only=True)

    # concepts 名稱重複 → 選既有概念時又建了一個新的
    by_name: dict[str, list[str]] = {}
    for cid, cname in concepts.items():
        by_name.setdefault(str(cname).strip(), []).append(cid)
    dup = [f"「{k}」：{v}" for k, v in by_name.items() if len(v) > 1]
    emit(dup, "concepts 沒有重複的名稱", "concepts 有重複的名稱（選擇既有概念時重複建立了）")

    # 任兩條標註不重疊
    ordered = sorted(valid, key=lambda a: (a["start"], a["end"]))
    overlaps = []
    for i, a in enumerate(ordered):
        for b in ordered[i + 1:]:
            if b["start"] >= a["end"]:
                break
            overlaps.append(f"{_ann_name(text, a)} 與 {_ann_name(text, b)}")
    emit(overlaps, "標註之間沒有重疊", "有標註互相重疊")

    # 解釋不應另外存成一條標註
    exp_spans = {(a.get("explanation_start"), a.get("explanation_end")) for a in valid}
    exp_only = [_ann_name(text, a) for a in valid if (a["start"], a["end"]) in exp_spans]
    emit(exp_only, "沒有「只代表解釋」的標註", "有標註的範圍等於某個解釋段落（解釋應存在術語標註的欄位裡）")

    return valid


# ---------------------------------------------------------------------------
# 任務單比對
# ---------------------------------------------------------------------------

def _compare_span(rep: Report, what: str, text: str, got: tuple, expected: tuple) -> None:
    exp_text = text[expected[0]:expected[1]]
    if got == expected:
        rep.ok(f"{what}範圍正確")
        return
    got_text = _span_text(text, *got)
    detail = f"你的範圍：{got}「{preview(got_text, 60)}」\n答案範圍：{expected}「{preview(exp_text, 60)}」"
    if got_text and got_text.strip(EDGE_CHARS) == exp_text.strip(EDGE_CHARS):
        rep.warn(f"{what}範圍只差頭尾的空白或標點", detail)
    else:
        rep.fail(f"{what}範圍不正確", detail)


def check_task(data: dict, valid: list[dict], task: dict, rep: Report) -> None:
    print("\n-- 任務單比對 --")
    text = data.get("text", "")
    concepts = data.get("concepts") or {}

    want_len, want_sha = task.get("text_length"), task.get("text_sha1")
    if not want_sha:
        rep.warn("任務單還沒記錄原文 hash，略過原文比對（請先執行 make_answer.py）")
    elif text_sha1(text) == want_sha:
        rep.ok("原文和任務單的文件一致")
    else:
        rep.fail("原文和任務單的文件不一致，以下的範圍比對可能不準",
                 f"你的原文長度 {len(text)}，任務單 {want_len}。"
                 f"是否開錯檔案，或改過 io.py 的 load_docx？")

    used: set[int] = set()
    for i, item in enumerate(task.get("items", []), 1):
        term = item["term"]
        print(f"\n  第 {i} 項：術語「{term}」")
        span = locate(text, term, item.get("term_occurrence", 1))
        if span is None:
            rep.fail(f"[{i}] 在原文找不到任務單指定的術語位置（任務單寫錯，或原文不一致）")
            continue

        # 先找範圍完全相同的；沒有就找重疊最多的
        cands = [a for a in valid if a["start"] < span[1] and span[0] < a["end"] and id(a) not in used]
        if not cands:
            rep.fail(f"[{i}] 沒有標註這個術語",
                     f"答案範圍：{span}「{preview(text[span[0]:span[1]])}」")
            continue
        ann = next((a for a in cands if (a["start"], a["end"]) == span), None)
        if ann is None:
            ann = max(cands, key=lambda a: min(a["end"], span[1]) - max(a["start"], span[0]))
        used.add(id(ann))

        _compare_span(rep, f"[{i}] 術語", text, (ann["start"], ann["end"]), span)

        exp = item.get("explanation")
        if exp:
            exp_span = locate(text, exp, item.get("explanation_occurrence", 1))
            if exp_span is None:
                rep.fail(f"[{i}] 在原文找不到任務單指定的解釋位置（任務單寫錯，或原文不一致）")
            elif ann.get("explanation_start") is None:
                rep.fail(f"[{i}] 沒有標註解釋",
                         f"答案範圍：{exp_span}「{preview(exp, 60)}」")
            else:
                _compare_span(rep, f"[{i}] 解釋", text,
                              (ann.get("explanation_start"), ann.get("explanation_end")), exp_span)

        for key, field, label in (("concept_id", "concept", "概念"),
                                  ("broader_concept_id", "broader_concept", "上位概念")):
            want = item.get(field)
            if not want:
                continue
            cid = ann.get(key)
            got = concepts.get(cid) if isinstance(cid, str) else None
            if got == want:
                rep.ok(f"[{i}] {label}「{want}」正確")
            else:
                rep.fail(f"[{i}] {label}不正確", f"你的：{got!r}　答案：{want!r}")

    extra = [a for a in valid if id(a) not in used]
    if extra:
        rep.fail("有任務單裡沒有的標註", "\n".join(_ann_name(text, a) for a in extra))
    else:
        rep.ok("沒有多餘的標註")


# ---------------------------------------------------------------------------

def check_file(path: Path, task: dict | None) -> Report:
    rep = Report()
    print(f"\n========== {path} ==========")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as ex:
        rep.fail("無法讀取檔案", repr(ex))
        return rep
    if not isinstance(data, dict) or data.get("format") != "lexa":
        rep.fail('不是 .lexa 格式（缺少 "format": "lexa"）')
        return rep

    valid = check_rules(data, rep)
    if task is not None:
        check_task(data, valid, task, rep)
    c = rep.counts
    print(f"\n小計：PASS {c['PASS']}　WARN {c['WARN']}　FAIL {c['FAIL']}")
    return rep


def main() -> int:
    ap = argparse.ArgumentParser(description="檢查 .lexa 標註是否符合格式，並可和任務單比對。")
    ap.add_argument("path", type=Path, help=".lexa 檔案，或放了多個 .lexa 的資料夾")
    ap.add_argument("--task", type=Path, help="任務單 JSON（例如 tests/tasks/範例任務.json）")
    args = ap.parse_args()

    task = None
    if args.task:
        with open(args.task, "r", encoding="utf-8") as f:
            task = json.load(f)

    if args.path.is_dir():
        files = sorted(args.path.rglob("*.lexa"))
        if not files:
            print(f"{args.path} 裡沒有 .lexa 檔")
            return 1
    else:
        files = [args.path]

    reports = [(p, check_file(p, task)) for p in files]

    if len(reports) > 1:
        print("\n========== 總表 ==========")
        print("PASS  WARN  FAIL  檔案")
        for p, rep in reports:
            c = rep.counts
            print(f"{c['PASS']:>4}  {c['WARN']:>4}  {c['FAIL']:>4}  {p.relative_to(args.path)}")

    return 1 if any(rep.counts["FAIL"] for _, rep in reports) else 0


if __name__ == "__main__":
    sys.exit(main())
