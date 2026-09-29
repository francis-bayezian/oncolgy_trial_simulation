"""Reference data shipped with the code (versioned): general clinical vocabulary the pipeline reads, so that no pipeline
module embeds medical terms."""

import json
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).parent


@lru_cache(maxsize=None)
def vocabulary() -> dict:
    return json.loads((HERE / "clinical_vocabulary.json").read_text(encoding="utf-8"))
