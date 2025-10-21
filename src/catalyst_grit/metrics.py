# src/catalyst_grit/metrics.py
from __future__ import annotations
import csv
from dataclasses import dataclass
from typing import List

@dataclass
class Block:
    minutes: float
    deliberate: bool
    note: str = ""

@dataclass
class TopicShare:
    topic: str
    minutes: float

def load_blocks_csv(path: str) -> List[Block]:
    out: List[Block] = []
    def to_bool(s: str) -> bool:
        s = (s or "").strip().lower()
        return s in {"1","true","t","yes","y","on"}
    with open(path, newline="", encoding="utf-8") as f:
        rdr = csv.DictReader(f)
        cols = {c.lower(): c for c in rdr.fieldnames or []}
        for row in rdr:
            minutes = float(row[cols.get("minutes","minutes")])
            deliberate = to_bool(row[cols.get("deliberate","deliberate")])
            note = row.get(cols.get("note","note"), "").strip()
            out.append(Block(minutes=minutes, deliberate=deliberate, note=note))
    return out

def load_topics_csv(path: str) -> List[TopicShare]:
    out: List[TopicShare] = []
    with open(path, newline="", encoding="utf-8") as f:
        rdr = csv.DictReader(f)
        cols = {c.lower(): c for c in rdr.fieldnames or []}
        for row in rdr:
            topic = row[cols.get("topic","topic")].strip()
            minutes = float(row[cols.get("minutes","minutes")])
            out.append(TopicShare(topic=topic, minutes=minutes))
    return out

def deliberate_practice_ratio(blocks: List[Block]) -> float:
    total = sum(b.minutes for b in blocks) or 0.0
    if total <= 0:
        return 0.0
    deliberate = sum(b.minutes for b in blocks if b.deliberate)
    return deliberate / total

def consistency_of_interests(topics: List[TopicShare]) -> float:
    total = sum(t.minutes for t in topics) or 0.0
    if total <= 0:
        return 0.0
    shares = [t.minutes/total for t in topics if t.minutes > 0]
    if not shares:
        return 0.0
    hhi = sum(p*p for p in shares)  # 1/N .. 1
    n = len(shares)
    if n <= 1:
        return 1.0
    min_hhi = 1.0 / n
    return (hhi - min_hhi) / (1.0 - min_hhi)
