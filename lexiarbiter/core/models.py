"""Core data models: Annotation and Document."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Annotation:
    """A single annotation span on the document.

    `labels` is a mapping from group_id (e.g. "argument_type") to label_id
    (e.g. "major_premise"). A span may have labels from one, several, or all
    groups defined in the active annotation mode (partial annotation is OK).
    """

    start: int
    end: int
    labels: dict[str, str] = field(default_factory=dict)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    note: str = ""

    def overlaps(self, other: "Annotation") -> bool:
        return not (self.end <= other.start or other.end <= self.start)

    def contains(self, pos: int) -> bool:
        return self.start <= pos < self.end

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Annotation":
        return cls(
            id=data.get("id", uuid.uuid4().hex[:12]),
            start=int(data["start"]),
            end=int(data["end"]),
            labels=dict(data.get("labels", {})),
            note=data.get("note", ""),
        )


@dataclass
class Document:
    """In-memory representation of a document being annotated."""

    text: str
    annotations: list[Annotation] = field(default_factory=list)
    schema_id: str = ""
    source_filename: str = ""
    source_meta: dict = field(default_factory=dict)
    file_path: Optional[str] = None  # path of the loaded .json or .lexa
    dirty: bool = False

    # ------------------------------------------------------------------
    # Annotation management

    def add_annotation(self, ann: Annotation) -> None:
        self.annotations.append(ann)
        self.dirty = True

    def remove_annotation(self, ann_id: str) -> bool:
        before = len(self.annotations)
        self.annotations = [a for a in self.annotations if a.id != ann_id]
        if len(self.annotations) != before:
            self.dirty = True
            return True
        return False

    def find_annotation(self, ann_id: str) -> Optional[Annotation]:
        for a in self.annotations:
            if a.id == ann_id:
                return a
        return None

    def annotations_at(self, pos: int) -> list[Annotation]:
        """All annotations covering a given character position."""
        return [a for a in self.annotations if a.contains(pos)]

    def annotations_in_range(self, start: int, end: int) -> list[Annotation]:
        return [
            a for a in self.annotations
            if not (a.end <= start or end <= a.start)
        ]

    def sorted_annotations(self) -> list[Annotation]:
        return sorted(self.annotations, key=lambda a: (a.start, a.end))
