from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

MOJIBAKE_REPLACEMENTS = {
    "вЂ“": "–",
    "вЂ”": "—",
    "вЂ": "”",
    "вЂњ": "“",
    "в„–": "№",
    "В®": "®",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "item"


def normalize_whitespace(value: str) -> str:
    for broken, fixed in MOJIBAKE_REPLACEMENTS.items():
        value = value.replace(broken, fixed)
    value = value.replace("\r", "\n")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def dedupe_lines(lines: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        key = line.casefold()
        if key in seen:
            continue
        seen.add(key)
        output.append(line)
    return output


def dedupe_adjacent_lines(lines: Iterable[str]) -> list[str]:
    output: list[str] = []
    previous_key: str | None = None
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        key = line.casefold()
        if previous_key == key:
            continue
        output.append(line)
        previous_key = key
    return output


def flatten_json_strings(value: Any) -> list[str]:
    strings: list[str] = []
    if isinstance(value, str):
        strings.append(value)
    elif isinstance(value, dict):
        for item in value.values():
            strings.extend(flatten_json_strings(item))
    elif isinstance(value, list):
        for item in value:
            strings.extend(flatten_json_strings(item))
    return strings


def chunked(values: Sequence[Any], size: int) -> Iterator[Sequence[Any]]:
    for index in range(0, len(values), size):
        yield values[index : index + size]


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def iter_json_files(root: Path) -> Iterator[Path]:
    if not root.exists():
        return iter(())
    return root.rglob("*.json")
