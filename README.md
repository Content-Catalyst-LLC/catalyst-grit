# Catalyst Grit (Full)

MIT-licensed **Catalyst Grit** with:
- Flask web app (event log + metrics upload)
- CLI (`grit`) for logging, listing, exporting, computing metrics
- Duckworth-style helpers (CSV loaders + metrics)
- **Compatibility shim** so old code like `from project import deliberate_practice_ratio` still works
- Sample CSVs
- (Optional) Jupyter notebook starter

## Install (editable) & Run

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e .

# Web
export FLASK_APP=catalyst_grit.app:app
export FLASK_ENV=development
flask run
# open http://127.0.0.1:5000

# CLI
grit add --kind setback --note "late start"
grit add --kind recovery --note "finished module"
grit list --limit 10
grit stats
grit dp-ratio sample_data/sample_blocks.csv
grit consistency sample_data/sample_topics.csv
grit demo
```

## Project Layout
```
catalyst-grit/
├─ LICENSE
├─ README.md
├─ pyproject.toml
├─ .gitignore
├─ src/catalyst_grit/
│  ├─ __init__.py
│  ├─ db.py
│  ├─ metrics.py
│  ├─ cli.py
│  └─ app.py
├─ templates/
│  ├─ index.html
│  └─ metrics.html
├─ static/
│  ├─ css/style.css
│  └─ js/app.js
├─ project/                 # compat shim
│  └─ __init__.py
├─ sample_data/
│  ├─ sample_blocks.csv
│  └─ sample_topics.csv
└─ notebooks/
   └─ CatalystGritDemo.ipynb (starter)
```

## License
MIT — see `LICENSE`.
