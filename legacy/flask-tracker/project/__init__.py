# project/__init__.py
# Compatibility shim so older code `from project import ...` keeps working.
from catalyst_grit.metrics import (
    load_blocks_csv, load_topics_csv,
    deliberate_practice_ratio, consistency_of_interests
)

__all__ = [
    "load_blocks_csv", "load_topics_csv",
    "deliberate_practice_ratio", "consistency_of_interests",
]
