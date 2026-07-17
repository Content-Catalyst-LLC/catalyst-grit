# src/catalyst_grit/cli.py
import os, json, sqlite3, click
from .db import DB_PATH, init_db
from .metrics import (
    load_blocks_csv, load_topics_csv,
    deliberate_practice_ratio, consistency_of_interests
)

def _connect():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    init_db()
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con

@click.group(help="Catalyst Grit CLI — events + metrics")
def cli():
    pass

@cli.command("add")
@click.option("--kind", type=click.Choice(["setback","recovery"]), required=True)
@click.option("--note", default="")
def add_event(kind, note):
    note = (note or "").strip()[:500]
    con = _connect()
    with con:
        con.execute("INSERT INTO events (kind, note) VALUES (?, ?)", (kind, note))
    click.echo(f"✔ added {kind}: {note or '…'}")

@cli.command("list")
@click.option("--limit", default=25, show_default=True)
def list_events(limit):
    con = _connect()
    rows = con.execute(
        "SELECT id, kind, note, created_at FROM events ORDER BY created_at DESC LIMIT ?",
        (limit,)).fetchall()
    if not rows:
        click.echo("No events yet."); return
    for r in rows:
        click.echo(f"[{r['id']:>3}] {r['kind']:8} {r['created_at']}  {r['note'] or '…'}")

@cli.command("stats")
def stats():
    con = _connect()
    rows = con.execute("SELECT kind, COUNT(*) c FROM events GROUP BY kind").fetchall()
    counts = {"setback":0, "recovery":0}
    for r in rows:
        counts[r["kind"]] = r["c"]
    click.echo(json.dumps({
        "perseverance": counts["setback"],
        "resilience": counts["recovery"],
    }, indent=2))

@cli.command("dp-ratio")
@click.argument("blocks_csv")
def dp_ratio(blocks_csv):
    blocks = load_blocks_csv(blocks_csv)
    click.echo(f"{deliberate_practice_ratio(blocks):.4f}")

@cli.command("consistency")
@click.argument("topics_csv")
def consistency(topics_csv):
    topics = load_topics_csv(topics_csv)
    click.echo(f"{consistency_of_interests(topics):.4f}")

@cli.command("demo")
def demo():
    b = os.path.join(os.path.dirname(__file__), "..", "sample_data", "sample_blocks.csv")
    t = os.path.join(os.path.dirname(__file__), "..", "sample_data", "sample_topics.csv")
    b = os.path.normpath(b); t = os.path.normpath(t)
    if not (os.path.exists(b) and os.path.exists(t)):
        click.echo("Missing sample CSVs"); return
    from .metrics import deliberate_practice_ratio, consistency_of_interests, load_blocks_csv, load_topics_csv
    blocks = load_blocks_csv(b); topics = load_topics_csv(t)
    click.echo(json.dumps({
        "deliberate_practice_ratio": round(deliberate_practice_ratio(blocks),4),
        "consistency_of_interests": round(consistency_of_interests(topics),4),
    }, indent=2))
