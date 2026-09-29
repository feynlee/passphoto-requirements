#!/usr/bin/env python3
"""Validates the requirement files, writes manifest.json, and builds the review report.

    python3 tools/validate.py                         # validate only
    python3 tools/validate.py --write-manifest        # validate and regenerate manifest.json
    python3 tools/validate.py --base origin/main \\
        --evidence review/evidence.json --report review/PR_BODY.md

With --base, every entry is compared with the version on that git ref. Changes other than the
`verified` date are "value changes": each one must have a matching record in the evidence file
(official URL and a verbatim quote), or the report marks it as unsupported. The script prints
`value_changes=true|false` and `unsupported=N` for the workflow (also to $GITHUB_OUTPUT).
"""
import argparse
from urllib.parse import urlparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQ = ROOT / "requirements"
SCHEMA_VERSION = 1

BACKGROUNDS = {"white", "whiteOrOffWhite", "creamOrLightGrey", "lightGrey", "plainLight", "lightNotWhite", "lightBlue", "blue", "red"}
GLASSES = {"notAllowed", "discouraged", "allowed"}
KINDS = {"passport", "visa", "id", "residence", "license", "other"}
APPLICANT = {"accepted", "certifiedPhotographerOnly", "officeOnly"}

# What each field does in the app, for the reviewer.
EFFECTS = {
    "widthMM": "Photo width: the crop frame's shape, print size and print sheets.",
    "heightMM": "Photo height: the crop frame's shape, print size and print sheets.",
    "sizeLabel": "How the size is shown to people.",
    "headHeightMM": "Allowed head height: where auto-crop puts the head, the head guides and the Head size check.",
    "headTop": "Whether head height is measured to the top of the skull or the hair.",
    "eyeLineFromBottomMM": "Allowed eye height: auto-crop placement, the eye band guide and the Eye height check.",
    "topMarginMM": "Allowed space above the head: auto-crop placement and its check.",
    "faceWidthMM": "Allowed face width: the Face width check.",
    "background": "Background rule: the instruction, the Background check and whether it's replaced.",
    "backgroundFill": "Colour a replaced background is filled with.",
    "glasses": "Glasses rule: the instruction and the Glasses check.",
    "digitalPixels": "Exact pixel size of the saved photo.",
    "minPixels": "Minimum pixel size for digital submission.",
    "maxFileKB": "Upload size limit: how much the JPEG is compressed.",
    "notes": "Notes shown under the specifications.",
    "infant": "Rules for babies: the Baby switch, instructions, head range and checks.",
    "source": "The official page linked in the app.",
    "applicantPhoto": "Whether the country accepts a photo you make yourself; the app warns if not.",
    "document": "Document name shown in the app.",
    "country": "Country name shown in the app.",
    "kind": "Which group the document is listed under.",
    "confidence": "Whether the app shows a 'check the official rules' note.",
}


# US-embargoed countries (Apple's App Review guideline 5); never include them or link to their domains.
EMBARGOED = {"CU", "IR", "KP", "SY"}


def load_dir(files):
    specs, errors = {}, []
    for path, text in files:
        try:
            entries = json.loads(text)
        except json.JSONDecodeError as e:
            errors.append(f"{path}: invalid JSON ({e})")
            continue
        for entry in entries:
            sid = entry.get("id", "?")
            if sid in specs:
                errors.append(f"{path}: duplicate id {sid}")
            specs[sid] = (path, entry)
    return specs, errors


def pair(value, name, sid, errors, low=0, high=200):
    if value is None:
        return None
    if not (isinstance(value, list) and len(value) == 2 and all(isinstance(v, (int, float)) for v in value)):
        errors.append(f"{sid}: {name} must be [min, max]")
        return None
    a, b = sorted(value)
    if a < low or b > high:
        errors.append(f"{sid}: {name} {value} outside {low}–{high}")
    return a, b


def check(sid, s, errors, warnings):
    """Rules an entry must meet to ship. Entries without a head size are allowed but won't load in the app."""
    if not re.fullmatch(r"[a-z]{2}-[a-z0-9-]+", sid):
        errors.append(f"{sid}: id must be a lowercase ISO code, a dash and a slug")
    for key in ("countryCode", "country", "document", "widthMM", "heightMM", "sizeLabel", "background", "source"):
        if s.get(key) in (None, "", []):
            errors.append(f"{sid}: missing {key}")
    w, h = s.get("widthMM"), s.get("heightMM")
    if isinstance(w, (int, float)) and not 15 <= w <= 110:
        errors.append(f"{sid}: widthMM {w} is implausible")
    if isinstance(h, (int, float)) and not 15 <= h <= 110:
        errors.append(f"{sid}: heightMM {h} is implausible")
    head = pair(s.get("headHeightMM"), "headHeightMM", sid, errors, 5, 90)
    if head is None:
        warnings.append(f"{sid}: no head size, so the app skips it")
    elif isinstance(h, (int, float)) and head[1] >= h:
        errors.append(f"{sid}: head height {head[1]} mm doesn't fit a {h} mm photo")
    eye = pair(s.get("eyeLineFromBottomMM"), "eyeLineFromBottomMM", sid, errors, 0, 110)
    if eye and isinstance(h, (int, float)) and eye[1] >= h:
        errors.append(f"{sid}: eye line {eye[1]} mm is above the top of a {h} mm photo")
    pair(s.get("topMarginMM"), "topMarginMM", sid, errors, 0, 30)
    pair(s.get("faceWidthMM"), "faceWidthMM", sid, errors, 5, 90)
    if s.get("background") not in BACKGROUNDS:
        errors.append(f"{sid}: unknown background {s.get('background')!r}")
    if s.get("glasses", "discouraged") not in GLASSES:
        errors.append(f"{sid}: unknown glasses rule {s.get('glasses')!r}")
    if s.get("kind", "other") not in KINDS:
        errors.append(f"{sid}: unknown kind {s.get('kind')!r}")
    if s.get("applicantPhoto", "accepted") not in APPLICANT:
        errors.append(f"{sid}: unknown applicantPhoto {s.get('applicantPhoto')!r}")
    if not str(s.get("source", "")).startswith("https://"):
        errors.append(f"{sid}: source must be an https URL")
    # Apple can't distribute apps connected to US-embargoed countries, so they must never be listed or linked.
    host = urlparse(str(s.get("source", ""))).hostname or ""
    if s.get("countryCode") in EMBARGOED or host.rsplit(".", 1)[-1].upper() in EMBARGOED:
        errors.append(f"{sid}: {s.get('countryCode')} / {host} is a US-embargoed country; it can't be included")
    if not re.fullmatch(r"#[0-9A-Fa-f]{6}", s.get("backgroundFill", "#FFFFFF")):
        errors.append(f"{sid}: backgroundFill must be #RRGGBB")
    try:
        date.fromisoformat(s.get("verified", ""))
    except ValueError:
        errors.append(f"{sid}: verified must be YYYY-MM-DD")
    if s.get("schema", 1) > SCHEMA_VERSION:
        errors.append(f"{sid}: schema {s.get('schema')} is newer than this validator")


def git_files(ref):
    try:
        names = subprocess.run(["git", "ls-tree", "--name-only", f"{ref}:requirements"], cwd=ROOT,
                               capture_output=True, text=True, check=True).stdout.split()
    except subprocess.CalledProcessError:
        return []
    return [(f"requirements/{n}", subprocess.run(["git", "show", f"{ref}:requirements/{n}"], cwd=ROOT,
             capture_output=True, text=True, check=True).stdout) for n in names if n.endswith(".json")]


def fmt(value):
    if value is None:
        return "—"
    if isinstance(value, list) and len(value) == 2 and all(isinstance(v, (int, float)) for v in value):
        return f"{value[0]}–{value[1]}"
    if isinstance(value, (dict, list)):
        return "`" + json.dumps(value, ensure_ascii=False) + "`"
    return str(value)


def flag(code):
    if code == "EU":
        return "🇪🇺"
    if code == "XX":
        return "🌐"
    return "".join(chr(127397 + ord(c)) for c in code.upper())


def report(base_specs, specs, evidence, out):
    by_id = {d["id"]: d for d in evidence.get("documents", [])}
    changed, added, removed, confirmed, unreachable = [], [], [], [], []
    unsupported = 0
    for sid, (_, new) in sorted(specs.items()):
        old = base_specs.get(sid, (None, None))[1]
        if old is None:
            added.append(sid)
            continue
        fields = sorted(k for k in set(old) | set(new) if k != "verified" and old.get(k) != new.get(k))
        if fields:
            changed.append((sid, old, new, fields))
        elif old.get("verified") != new.get("verified"):
            confirmed.append(sid)
    removed = sorted(set(base_specs) - set(specs))
    unreachable = sorted(d["id"] for d in evidence.get("documents", []) if d.get("status") == "unreachable")

    lines = []
    lines.append(f"## Quarterly requirements review · {evidence.get('checkedAt', date.today().isoformat())}\n")
    lines.append("Each change below comes from the document's official page. **Before approving, open each link, find the quoted text, and confirm the new value matches it.** "
                 "Nothing reaches the app until you merge this pull request.\n")
    lines.append(f"- **{len(changed)}** documents with changed values\n- **{len(added)}** new documents\n- **{len(removed)}** removed documents\n"
                 f"- **{len(confirmed)}** confirmed unchanged (only their “as of” date moves)\n- **{len(unreachable)}** couldn’t be checked\n")

    def evidence_for(sid, field):
        for c in by_id.get(sid, {}).get("changes", []):
            if c.get("field") == field:
                return c
        return None

    for sid, old, new, fields in changed:
        doc = by_id.get(sid, {})
        lines.append(f"\n### {flag(new.get('countryCode', ''))} {new.get('country')} {new.get('document')} (`{sid}`)\n")
        src = doc.get("source") or new.get("source")
        lines.append(f"**Official page:** {src}\n")
        if doc.get("note"):
            lines.append(f"> {doc['note']}\n")
        lines.append("| Field | Before | After | What it changes in the app |\n|---|---|---|---|")
        for field in fields:
            lines.append(f"| `{field}` | {fmt(old.get(field))} | {fmt(new.get(field))} | {EFFECTS.get(field, '')} |")
        lines.append("")
        for field in fields:
            ev = evidence_for(sid, field)
            if ev and ev.get("quote") and str(ev.get("sourceURL", src)).startswith("https://"):
                lines.append(f"- **`{field}`** — quoted from {ev.get('sourceURL', src)}:\n  > {ev['quote']}")
                if ev.get("reasoning"):
                    lines.append(f"  \n  _How the value was derived:_ {ev['reasoning']}")
            else:
                unsupported += 1
                lines.append(f"- ⚠️ **`{field}` has no quoted evidence. Don’t approve this change without checking it yourself.**")
        lines.append(f"\n- [ ] I opened the official page and the quoted text supports every change for `{sid}`.")

    for sid in added:
        new = specs[sid][1]
        doc = by_id.get(sid, {})
        lines.append(f"\n### New: {flag(new.get('countryCode', ''))} {new.get('country')} {new.get('document')} (`{sid}`)\n")
        lines.append(f"**Official page:** {doc.get('source') or new.get('source')}\n")
        lines.append("```json\n" + json.dumps(new, indent=2, ensure_ascii=False) + "\n```")
        quotes = doc.get("changes", [])
        if quotes:
            for c in quotes:
                lines.append(f"- **`{c.get('field')}`**: > {c.get('quote', '')}")
        else:
            unsupported += 1
            lines.append("- ⚠️ **No quoted evidence for this new document.**")
        lines.append(f"\n- [ ] I checked every value for `{sid}` against the official page.")

    for sid in removed:
        old = base_specs[sid][1]
        doc = by_id.get(sid, {})
        lines.append(f"\n### Removed: {old.get('country')} {old.get('document')} (`{sid}`)\n")
        lines.append(f"Reason: {doc.get('note', '⚠️ none given')}  \nOfficial page: {doc.get('source') or old.get('source')}")
        if not doc.get("note"):
            unsupported += 1

    if unreachable:
        lines.append("\n### Couldn’t be checked\nThese pages couldn’t be read (blocked, down, or moved). Their “as of” date stays at the last successful check; check them by hand if you can.\n")
        for sid in unreachable:
            doc = by_id[sid]
            lines.append(f"- `{sid}`: {doc.get('source', '')} — {doc.get('note', '')}")
    if confirmed:
        lines.append("\n<details><summary>Confirmed unchanged</summary>\n\n" + ", ".join(f"`{s}`" for s in confirmed) + "\n</details>")

    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return bool(changed or added or removed), unsupported, bool(confirmed)


def write_manifest(specs):
    files = []
    for path in sorted(REQ.glob("*.json")):
        data = path.read_bytes()
        files.append({"path": f"requirements/{path.name}", "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)})
    as_of = max(e["verified"] for _, e in specs.values())
    now = datetime.now(timezone.utc)
    manifest = {"schema": SCHEMA_VERSION, "version": int(now.strftime("%Y%m%d%H%M")), "asOf": as_of,
                "generated": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "documents": len(specs), "files": files}
    old = json.loads((ROOT / "manifest.json").read_text()) if (ROOT / "manifest.json").exists() else {}
    if old.get("files") == files and old.get("asOf") == as_of:
        print("manifest.json is already current")
        return
    (ROOT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"wrote manifest.json: version {manifest['version']}, as of {as_of}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-manifest", action="store_true")
    parser.add_argument("--base")
    parser.add_argument("--evidence", default="review/evidence.json")
    parser.add_argument("--report", default="review/PR_BODY.md")
    args = parser.parse_args()

    specs, errors = load_dir([(str(p.relative_to(ROOT)), p.read_text(encoding="utf-8")) for p in sorted(REQ.glob("*.json"))])
    warnings = []
    for sid, (_, s) in specs.items():
        check(sid, s, errors, warnings)
    for w in warnings:
        print(f"note: {w}")
    if errors:
        for e in errors:
            print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
    print(f"{len(specs)} entries valid")

    outputs = {}
    if args.base:
        base_specs, _ = load_dir(git_files(args.base))
        evidence_path = ROOT / args.evidence
        evidence = json.loads(evidence_path.read_text()) if evidence_path.exists() else {}
        value_changes, unsupported, confirmed = report(base_specs, specs, evidence, ROOT / args.report)
        outputs = {"value_changes": str(value_changes).lower(), "unsupported": str(unsupported),
                   "dates_only": str(confirmed and not value_changes).lower()}
    if args.write_manifest:
        write_manifest(specs)
    for k, v in outputs.items():
        print(f"{k}={v}")
    if os.environ.get("GITHUB_OUTPUT") and outputs:
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            for k, v in outputs.items():
                f.write(f"{k}={v}\n")


if __name__ == "__main__":
    main()
