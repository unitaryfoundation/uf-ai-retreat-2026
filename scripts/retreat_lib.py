"""Shared helpers: front-matter parsing for retreat entries (standard library only)."""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent

# collection directory -> (entry type, required front-matter keys)
COLLECTIONS = {
    "attendees": ("attendee", ["name", "affiliation"]),
    "charts/problems": ("problem", ["title", "proposer", "status"]),
    "charts/tools": ("tool", ["title", "contributor"]),
    "charts/structures": ("structure", ["title", "proposer", "status"]),
    "sessions/sat-failure-autopsies": ("autopsy", ["title"]),
}
STATUSES = {"idea", "pitched", "group-formed", "done", "parked"}
SKIP = {"README.md", "INDEX.md"}


def parse(path):
    """Return (front_matter_dict, body). Front matter is flat `key: value` lines between --- fences."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return None, text
    end = text.find("\n---", 4)
    if end == -1:
        return None, text
    meta = {}
    for line in text[4:end].splitlines():
        if not line.strip() or line.lstrip().startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        value = value.strip()
        if value.startswith('"'):
            try:
                value = json.loads(value)
            except ValueError:
                value = value.strip('"')
        meta[key.strip()] = value
    return meta, text[end + 4:].lstrip("\n")


def entries(collection):
    folder = ROOT / collection
    for path in sorted(folder.glob("*.md")):
        if path.name not in SKIP:
            yield path
