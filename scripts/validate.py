#!/usr/bin/env python3
"""Check entries for required front matter and for private details that must not be committed.

Exit code 1 if anything is wrong. Run: python3 scripts/validate.py
"""
import re
import subprocess
import sys

from retreat_lib import COLLECTIONS, ROOT, STATUSES, entries, parse

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
PHONE = re.compile(r"(?<![\w/.-])(\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}(?![\w/-])")
WIFI = re.compile(r"(wi-?fi|network)\s*(password|passphrase|key)\s*[:=]", re.I)
ALLOWED_EMAILS = {"noreply@anthropic.com"}
TEXT_SUFFIXES = {".md", ".txt", ".py", ".yml", ".yaml", ".json", ".toml", ".csv", ".sh", ".lean", ".tex", ""}


def tracked_files():
    out = subprocess.run(["git", "ls-files", "-co", "--exclude-standard"], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout
    return [ROOT / line for line in out.splitlines() if line]


def main():
    problems = []
    for collection, (kind, required) in COLLECTIONS.items():
        for path in entries(collection):
            rel = path.relative_to(ROOT)
            meta, _ = parse(path)
            if meta is None:
                problems.append(f"{rel}: missing front matter (start the file with ---)")
                continue
            for key in required:
                if not meta.get(key):
                    problems.append(f"{rel}: missing required field '{key}'")
            if "status" in meta and meta["status"] and meta["status"] not in STATUSES:
                problems.append(f"{rel}: status '{meta['status']}' not one of {sorted(STATUSES)}")
            if not re.fullmatch(r"[a-z0-9][a-z0-9-]*\.md", path.name):
                problems.append(f"{rel}: file name must be lowercase-kebab-case.md")

    for path in tracked_files():
        if path.suffix.lower() not in TEXT_SUFFIXES or not path.is_file():
            continue
        rel = path.relative_to(ROOT)
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for number, line in enumerate(text.splitlines(), 1):
            for match in EMAIL.finditer(line):
                address = match.group(0).lower()
                if address not in ALLOWED_EMAILS and not address.endswith("@users.noreply.github.com"):
                    problems.append(f"{rel}:{number}: email address (keep contact details out of the repo)")
            if PHONE.search(line):
                problems.append(f"{rel}:{number}: looks like a phone number")
            if WIFI.search(line):
                problems.append(f"{rel}:{number}: looks like a wifi password")

    for line in problems:
        print(line)
    print(f"{len(problems)} problem(s)" if problems else "OK")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
