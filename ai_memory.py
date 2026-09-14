from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


MAX_MEMORY_ENTRIES = 20


def _memory_path() -> Path:
    configured_path = os.getenv("SLAYTHETEXT_AI_MEMORY")
    if configured_path:
        return Path(configured_path).expanduser()
    return Path.cwd() / "slaythetext_ai_memory.json"


def load() -> list[dict[str, Any]]:
    try:
        data = json.loads(_memory_path().read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    return [entry for entry in data if isinstance(entry, dict)][-MAX_MEMORY_ENTRIES:]


def remember(title: str, choice_id: str, choice_text: str, result: str) -> None:
    entries = load()
    entries.append(
        {
            "title": title,
            "choice_id": choice_id,
            "choice": choice_text,
            "result": result,
        }
    )
    try:
        path = _memory_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(entries[-MAX_MEMORY_ENTRIES:], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass
