from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_forbidden_generated_artifacts_absent():
    forbidden=[]
    for path in ROOT.rglob('*'):
        rel=path.relative_to(ROOT)
        if any(part in {'.git','.venv','dist','build','__pycache__','.pytest_cache'} for part in rel.parts): continue
        if path.is_file() and (path.suffix in {'.db','.sqlite','.sqlite3','.pyc'} or '.egg-info' in rel.parts): forbidden.append(str(rel))
    assert forbidden == []


def test_package_surface_is_canonical():
    assert {p.name for p in (ROOT/'src/catalyst_grit').glob('*.py')} == {'__init__.py','api.py','cli.py','core.py','publication.py','storage.py','version.py'}


def test_contract_documentation_exists():
    required=['docs/recovery-record-contract.md','docs/methodology-profile.md','docs/migration-v1.0-to-v1.1.md','docs/persistent-workspace.md','docs/migrations-v1.2.md','docs/wordpress-private-workspace.md','release/v1.2.0.md','docs/context-mapping.md','release/v1.3.0.md','docs/recovery-planning.md','docs/migrations-v1.4.md','release/v1.4.0.md','docs/learning-loops.md','docs/migrations-v1.5.md','release/v1.5.0.md','docs/team-recovery.md','docs/migrations-v1.6.md','release/v1.6.0.md','docs/evidence-and-handoffs.md','docs/migrations-v1.7.md','release/v1.7.0.md','docs/monitoring-trends.md','docs/migrations-v1.8.md','docs/publication-and-export.md','docs/institutional-api.md','docs/institutional-governance.md','docs/migrations-v1.9.md','release/v1.9.0.md']
    assert all((ROOT/path).is_file() for path in required)
