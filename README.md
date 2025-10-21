# Catalyst Grit — Perseverance & Resilience (MIT)

Catalyst Grit logs **setbacks** and **recoveries** and computes Duckworth-style helpers:
**Deliberate Practice Ratio** and **Consistency of Interests**. Use via **CLI**, **Web UI**, or **REST API**.
Built to integrate with **Catalyst Canvas**.

**Quickstart**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
export FLASK_APP=catalyst_grit.app:app
flask run -p 5055
# http://127.0.0.1:5055/api/grit/stats

