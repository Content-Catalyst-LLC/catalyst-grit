# src/catalyst_grit/app.py
import os
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from .db import get_db, init_db, DB_PATH
from .api import api as grit_api

def create_app():
    app = Flask(__name__)
    CORS(app, resources={r"/api/*": {"origins": "*"}})
    init_db()
    app.register_blueprint(grit_api)

    @app.route("/")
    def index():
        db = get_db()
        cur = db.execute("SELECT id, kind, note, created_at FROM events ORDER BY created_at DESC LIMIT 100")
        events = [dict(row) for row in cur.fetchall()]
        perseverance = sum(1 for e in events if e["kind"] == "setback")
        resilience = sum(1 for e in events if e["kind"] == "recovery")
        return render_template("index.html", events=events, perseverance=perseverance, resilience=resilience)

    @app.post("/api/event")
    def add_event():
        payload = request.get_json(force=True)
        kind = payload.get("kind")
        note = (payload.get("note") or "").strip()[:500]
        if kind not in ("setback", "recovery"):
            return jsonify({"error": "kind must be 'setback' or 'recovery'"}), 400
        db = get_db()
        db.execute("INSERT INTO events (kind, note) VALUES (?, ?)", (kind, note))
        db.commit()
        return jsonify({"status": "ok"}), 201

    @app.route("/metrics", methods=["GET", "POST"])
    def metrics_page():
        from .metrics import load_blocks_csv, load_topics_csv, deliberate_practice_ratio, consistency_of_interests
        result = None; error = None
        if request.method == "POST":
            try:
                bfile = request.files.get("blocks_csv")
                tfile = request.files.get("topics_csv")
                if not bfile or not tfile:
                    raise ValueError("Please provide both CSV files.")
                inst = os.path.join(os.path.dirname(DB_PATH), "_uploads")
                os.makedirs(inst, exist_ok=True)
                bpath = os.path.join(inst, "_blocks.csv")
                tpath = os.path.join(inst, "_topics.csv")
                bfile.save(bpath); tfile.save(tpath)
                blocks = load_blocks_csv(bpath); topics = load_topics_csv(tpath)
                result = {
                    "deliberate_practice_ratio": round(deliberate_practice_ratio(blocks), 4),
                    "consistency_of_interests": round(consistency_of_interests(topics), 4),
                }
            except Exception as ex:
                error = str(ex)
        return render_template("metrics.html", result=result, error=error)

    return app

app = create_app()
