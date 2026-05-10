"""File I/O for LexiArbiter.

Three file types:

* `.json`  - Raw judicial open-data file. We read the `JFULL` field for the
             full judgment text plus a few metadata fields.
* `.lexa`  - LexiArbiter's own work-in-progress format. JSON content but with
             a distinct extension so it is easy to tell apart from raw data.
             Holds the full original text + structured annotation list, so
             another annotator can pick up where you left off.
* `.txt`   - Final model-ready export, matching the wrapper format used by
             the user's MTL pipeline (e.g. ``<P>大前提,非第一人稱|...</P>``).
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Optional

from .config import AnnotationMode, ExportConfig
from .models import Annotation, Document

log = logging.getLogger(__name__)


LEXA_VERSION = 1


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_judicial_json(path: Path | str) -> Document:
    """Load a raw judicial open-data .json file (JFULL inside).

    Some judicial open-data files have a top-level dict; some have a list with
    one record. Try both.
    """
    path = Path(path)
    log.info("載入 judicial JSON：%s", path)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        if not data:
            raise ValueError("JSON 內容為空陣列")
        data = data[0]
    if not isinstance(data, dict):
        raise ValueError("無法辨識 JSON 結構")

    text = data.get("JFULL") or data.get("jfull") or ""
    if not text:
        raise ValueError("JSON 中找不到 JFULL 欄位")

    meta = {k: v for k, v in data.items() if k not in ("JFULL", "jfull")}
    return Document(
        text=text,
        annotations=[],
        schema_id="",
        source_filename=path.name,
        source_meta=meta,
        file_path=str(path),
        dirty=False,
    )


def load_lexa(path: Path | str) -> Document:
    """Load a LexiArbiter work-in-progress file."""
    path = Path(path)
    log.info("載入 lexa：%s", path)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if data.get("format") != "lexa":
        raise ValueError("檔案不是 LexiArbiter 的 .lexa 格式")

    text = data.get("text", "")
    anns = [Annotation.from_dict(a) for a in data.get("annotations", [])]

    src = data.get("source", {}) or {}
    return Document(
        text=text,
        annotations=anns,
        schema_id=data.get("schema", ""),
        source_filename=src.get("filename", path.name),
        source_meta=src.get("meta", {}),
        file_path=str(path),
        dirty=False,
    )


def load_any(path: Path | str) -> Document:
    """Dispatch on extension."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".lexa":
        return load_lexa(path)
    if suffix == ".json":
        return load_judicial_json(path)
    raise ValueError(f"不支援的檔案類型：{suffix}")


# ---------------------------------------------------------------------------
# Save .lexa
# ---------------------------------------------------------------------------

def save_lexa(doc: Document, path: Path | str, schema: AnnotationMode,
              update_doc_state: bool = True) -> None:
    """寫入 .lexa。

    update_doc_state=False 時不更動 doc.file_path / dirty / schema_id，
    供 autosave、emergency 之類的「旁路存檔」使用——這些寫法不應該讓
    使用者看到的「未儲存」狀態消失。
    """
    path = Path(path)
    log.info("儲存 lexa：%s（標註數：%d）", path, len(doc.annotations))
    payload = {
        "format": "lexa",
        "version": LEXA_VERSION,
        "schema": schema.id,
        "source": {
            "filename": doc.source_filename,
            "meta": doc.source_meta,
        },
        "text": doc.text,
        "annotations": [a.to_dict() for a in doc.sorted_annotations()],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    if update_doc_state:
        doc.file_path = str(path)
        doc.schema_id = schema.id
        doc.dirty = False


# ---------------------------------------------------------------------------
# Export model-ready .txt
# ---------------------------------------------------------------------------

def _format_p_line(text: str, labels: dict[str, str], schema: AnnotationMode,
                   exp: ExportConfig) -> str:
    parts: list[str] = []
    for gid in exp.tag_order:
        lid = labels.get(gid)
        if not lid:
            continue
        lb = schema.label(gid, lid)
        if lb is not None:
            parts.append(lb.tag)
    tag_blob = exp.tag_separator.join(parts)
    # In the user's example, \r\n inside the original text is preserved as the
    # raw text (the model's preprocessing strips it later).
    return f"{exp.wrapper_open}{tag_blob}{exp.field_separator}{text}{exp.wrapper_close}"


def export_txt(doc: Document, path: Path | str, schema: AnnotationMode) -> dict:
    """Write a model-ready .txt file. Returns a dict with summary info.

    Summary keys: ``written`` (int), ``unannotated_chars`` (int),
    ``partial_count`` (int), ``warnings`` (list[str]).

    演算法以「字元 segment」為單位：先把所有 annotation 的 start/end
    切成不重疊區段，再對每個區段合併所有覆蓋該區段的 annotation labels。
    這讓「同範圍多群組」（無論在 .lexa 是用一條多群組 annotation 或多條
    同 span 各帶一群組來表達）匯出結果一致，達到冪等性。
    """
    path = Path(path)
    log.info("匯出 txt：%s", path)
    exp = schema.export

    text = doc.text
    n = len(text)

    # 1) 收集 boundary points。
    points: set[int] = {0, n}
    for a in doc.annotations:
        if 0 <= a.start <= n:
            points.add(a.start)
        if 0 <= a.end <= n:
            points.add(a.end)
    sorted_points = sorted(points)

    warnings: list[str] = []

    # 2) 對每個 segment 合併所有覆蓋它的 annotation labels。
    raw_segments: list[tuple[int, int, dict[str, str]]] = []
    for i in range(len(sorted_points) - 1):
        s, e = sorted_points[i], sorted_points[i + 1]
        if s >= e:
            continue
        seg_labels: dict[str, str] = {}
        for a in doc.annotations:
            if a.start <= s and e <= a.end:
                for gid, lid in a.labels.items():
                    if gid in seg_labels and seg_labels[gid] != lid:
                        # 同群組衝突理論上不會發生（apply_label 已禁止），
                        # 但讀入舊 .lexa 仍可能遇到；採「先到先得」並記警告。
                        warnings.append(
                            f"段落 {s}-{e} 同群組 {gid} 出現多個 label "
                            f"（{seg_labels[gid]} vs {lid}），採用先標註的版本。"
                        )
                    else:
                        seg_labels[gid] = lid
        raw_segments.append((s, e, seg_labels))

    # 3) 合併相鄰且 labels 完全相同的 segments，避免 boundary 切碎輸出。
    merged: list[tuple[int, int, dict[str, str]]] = []
    for s, e, lbls in raw_segments:
        if merged and merged[-1][1] == s and merged[-1][2] == lbls:
            ps, _pe, plbls = merged[-1]
            merged[-1] = (ps, e, plbls)
        else:
            merged.append((s, e, lbls))

    # 4) 逐段輸出。
    lines: list[str] = []
    partial_count = 0
    unannotated_chars = 0
    written = 0

    for s, e, lbls in merged:
        seg_text = text[s:e]
        if not seg_text:
            continue
        if lbls:
            missing = [
                schema.group(gid).name
                for gid in exp.tag_order
                if gid not in lbls and schema.group(gid) is not None
            ]
            if missing:
                partial_count += 1
                if exp.require_all_groups:
                    warnings.append(
                        f"段落「{seg_text[:15]}…」缺少必填群組：{', '.join(missing)}"
                    )
            lines.append(_format_p_line(seg_text, lbls, schema, exp))
            written += 1
        else:
            if exp.include_unannotated and seg_text.strip():
                lines.append(seg_text)
                written += 1
            else:
                unannotated_chars += len(seg_text)

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return {
        "written": written,
        "unannotated_chars": unannotated_chars,
        "partial_count": partial_count,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Optional: parse a legacy .txt back into a Document (best-effort).
# ---------------------------------------------------------------------------

_P_RE = re.compile(r"<P>(?P<tags>[^|<>]*)\|(?P<text>.*?)</P>", re.DOTALL)


def parse_legacy_txt(path: Path | str, schema: AnnotationMode) -> Document:
    """Best-effort import of a model-ready .txt back into a Document.

    Each ``<P>tag1,tag2|text</P>`` segment becomes an Annotation. Tags that the
    schema does not recognise are dropped (with a warning attached to note).
    """
    path = Path(path)
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()

    text_parts: list[str] = []
    annotations: list[Annotation] = []
    cursor = 0

    for m in _P_RE.finditer(raw):
        tags = [t.strip() for t in m.group("tags").split(",") if t.strip()]
        seg = m.group("text")
        labels: dict[str, str] = {}
        unknown: list[str] = []
        for t in tags:
            lb = schema.find_label_by_tag(t)
            if lb is None:
                unknown.append(t)
            else:
                labels[lb.group_id] = lb.id

        start = sum(len(p) for p in text_parts) + (len(text_parts))  # joined with \n
        # Build simple flat text (one segment per line).
        if text_parts:
            text_parts.append("\n")
        text_parts.append(seg)
        end = sum(len(p) for p in text_parts)
        # adjust start accordingly
        start = end - len(seg)

        ann = Annotation(start=start, end=end, labels=labels)
        if unknown:
            ann.note = f"未知標籤：{','.join(unknown)}"
        annotations.append(ann)
        cursor = m.end()

    text = "".join(text_parts)
    return Document(
        text=text,
        annotations=annotations,
        schema_id=schema.id,
        source_filename=path.name,
        file_path=str(path),
        dirty=False,
    )
