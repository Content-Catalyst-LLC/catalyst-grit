# src/catalyst_grit/db.py
import os, sqlite3
from flask import g

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "instance", "grit.db")
DB_PATH = os.path.normpath(DB_PATH)

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.executescript(
        '''
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL CHECK(kind IN ('setback','recovery')),
            note TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        '''
    )
    db.commit()
    db.close()
