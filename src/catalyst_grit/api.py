# src/catalyst_grit/api.py
from flask import Blueprint, request, jsonify
import os
from .db import get_db
from .metrics import (
    load_blocks_csv, load_topics_csv,
    deliberate_practice_ratio, consistency_of_interests
)

api = Blueprint("grit_api", __name__, url_prefix="/api/grit")

def _auth_ok(req):
    token = os.getenv("GRIT_API_TOKEN")
    if not token:  # allow if no token set (dev)
        return True
    return req.headers.get("Authorization") == f"Bearer {token}"

@api.before_request
def _check_auth():
    if not _auth_ok(request):
        return jsonify({"error": "unauthorized"}), 401

@api.get("/events")
def list_events():
    try:
        limit = int(request.args.get("limit", 50))
    except ValueError:
        limit = 50
    db = get_db()
    rows = db.execute(
        "SELECT id, kind, note, created_at FROM events ORDER BY created_at DESC LIMIT ?",
        (limit,)
    ).fetchall()
    return jsonify([dict(r) for r in rows])

@api.post("/events")
def add_event():
    payload = request.get_json(force=True)
    kind = payload.get("kind")
    note = (payload.get("note") or "").strip()[:500]
    if kind not in ("setback","recovery"):
        return jsonify({"error":"kind must be 'setback' or 'recovery'"}), 400
    db = get_db()
    db.execute("INSERT INTO events (kind, note) VALUES (?, ?)", (kind, note))
    db.commit()
    return jsonify({"status":"ok"}), 201

@api.get("/stats")
def stats():
    db = get_db()
    rows = db.execute("SELECT kind, COUNT(*) c FROM events GROUP BY kind").fetchall()
    counts = {"setback":0, "recovery":0}
    for r in rows:
        counts[r["kind"]] = r["c"]
    return jsonify({
        "perseverance": counts["setback"],
        "resilience": counts["recovery"]
    })

@api.post("/metrics/json")
def metrics_json():
    data = request.get_json(force=True)
    blocks = data.get("blocks", [])
    topics = data.get("topics", [])
    # coerce structures
    b = [{"minutes": float(x.get("minutes", 0)), "deliberate": bool(x.get("deliberate", False))} for x in blocks]
    t = [{"topic": str(x.get("topic","")), "minutes": float(x.get("minutes",0))} for x in topics]
    # compute
    class Block: 
        def __init__(self, minutes, deliberate, note=""): self.minutes=minutes; self.deliberate=deliberate; self.note=note
    class TopicShare:
        def __init__(self, topic, minutes): self.topic=topic; self.minutes=minutes
    bb = [Block(x["minutes"], x["deliberate"]) for x in b]
    tt = [TopicShare(x["topic"], x["minutes"]) for x in t]
    return jsonify({
        "deliberate_practice_ratio": round(deliberate_practice_ratio(bb), 4),
        "consistency_of_interests": round(consistency_of_interests(tt), 4)
    })
