#################################### Part 0: Import modules ->

import os
import re
import csv
import sys
import html
import json
import shutil
from datetime import datetime



#################################### Part 1: Setup ->

# Repo root (this file lives in Scripts/): Input/ and Output/ are found
# from here, so the script runs from any folder. The paths below are relative to it.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT = "Input/CIDs.csv"

# Every run writes to the folder of the day, Output/YYYY-MM-DD/, so each day's
# expected structure, graph and case text are kept as history. Running again
# on the same day updates that day's folder; earlier days are never touched.
OUTPUT = "Output"
DAY = datetime.now().strftime("%Y-%m-%d")
DAY_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
EXPECTED = f"{OUTPUT}/{DAY}/CIDs_Expected.csv"
HTML_OUT = f"{OUTPUT}/{DAY}/CIDs.html"
CASE_OUT = f"{OUTPUT}/{DAY}/Case_Message.txt"

# Header of the CID export from the Falcon console - any other header stops the run
HEADER = ["CID Name", "CID String", "Customer ID Checksum (CCID)", "Status", "Is Parent?",
          "Parent", "Additional Parent", "CID Groups", "Number of Endpoints",
          "Number of Endpoints Seen Last 45 Days", "Number of Child CIDs",
          "Number of Total Endpoints", "Number of Total Endpoints Seen Last 45 Days",
          "Policy Inheritance", "Detection Aggregation", "Incident Aggregation",
          "Domain Allowlist", "Falcon Module Subscriptions", "Application and Plugin Integrations"]

# Header of Output/CIDs_Expected.csv - parents by CID String, so renames never break a link
EXP_HEADER = ["CID String", "CID Name", "Parent CID", "Additional Parent CID",
              "Policy Inheritance", "Detection Aggregation", "Incident Aggregation"]

# The settings compared and written: (name in the CSVs and the case text, key)
FLAGS = [("Policy Inheritance", "pol"), ("Detection Aggregation", "det"), ("Incident Aggregation", "inc")]

# A CID String from the console, and the placeholder of a CID still to be created
CID_RE = re.compile(r"[0-9a-f]{32}")
NEW_RE = re.compile(r"NEW-\d+")

# Rules - set them to your organization's conventions:
# - a new or changed CID name has at most MAX_NAME characters (0 turns the check off);
# - with INCIDENT_FOLLOWS_DETECTION, Incident Aggregation must always have the
#   same value as Detection Aggregation (the case text also says so).
MAX_NAME = 38
INCIDENT_FOLLOWS_DETECTION = True

# Shown in the browser tab and in the page header. The tab icon is a data URI
# of the parent glyph (the dot cluster of the Falcon console), fully local.
TAB_TITLE = "Falcon Flight Control - CID Hierarchy"
APP_NAME = "Flight Control"
PAGE_NAME = "CID hierarchy"
GLYPH = ('<circle cx="0" cy="0" r="3.3"/><circle cx="7.2" cy="0" r="3.3"/><circle cx="3.6" cy="6.2" r="3.3"/>'
         '<circle cx="-3.6" cy="6.2" r="3.3"/><circle cx="-7.2" cy="0" r="3.3"/><circle cx="-3.6" cy="-6.2" r="3.3"/>'
         '<circle cx="3.6" cy="-6.2" r="3.3"/>')
FAVICON = ("data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='-12 -12 24 24' fill='%23f4895f'>"
           + GLYPH.replace('"', "'") + "</svg>")

# The page colors, as CSS custom properties: dark (the default, as in the
# Falcon console) and light (the sun/moon button in the header switches
# them; the browser remembers the choice). As in the Falcon legend, parent
# CIDs (the root and the service lines) are drawn in "parent", tenants in
# "cid", Policy Inheritance in "policy" and Detection Aggregation in
# "detect". Links are "link" (dimmed: "link-dim"), additional parents "addl",
# the chain of the clicked CID "hi".
THEMES = {
  "dark": {
    "bg": "#1c1c20", "bar": "#1c1c20", "canvas": "#27272c", "card": "#2e2e34", "card-border": "#3b3b43",
    "panel": "#2f2f35", "panel-2": "#2a2a30", "field": "#232328", "border": "#3e3e46", "border-soft": "#35353c",
    "text": "#ececef", "muted": "#a5a5af", "faint": "#72727c", "hover": "rgba(255, 255, 255, 0.06)",
    "hover-strong": "rgba(255, 255, 255, 0.11)", "sel-row": "rgba(107, 138, 253, 0.18)",
    "accent": "#6b8afd", "accent-text": "#8fa6ff", "parent": "#f4895f", "cid": "#4fd6f3",
    "policy": "#b47cf5", "policy-text": "#c9a2f8", "detect": "#f3cd3c", "detect-text": "#f3cd3c",
    "on-pol": "#1b1b1f", "on-det": "#1b1b1f", "link": "#6c6c76", "link-dim": "#38383f", "addl": "#8a8a94",
    "hi": "#ffffff", "ok": "#4ade80", "warn": "#f5a524", "shadow": "0 10px 30px rgba(0, 0, 0, 0.35)"},
  "light": {
    "bg": "#ffffff", "bar": "#ffffff", "canvas": "#f1f2f4", "card": "#ffffff", "card-border": "#dfe0e5",
    "panel": "#ffffff", "panel-2": "#f6f7f9", "field": "#f4f5f7", "border": "#d9dbe0", "border-soft": "#e8e9ed",
    "text": "#1d1e23", "muted": "#5b5d68", "faint": "#9093a0", "hover": "rgba(0, 0, 0, 0.045)",
    "hover-strong": "rgba(0, 0, 0, 0.08)", "sel-row": "rgba(61, 99, 240, 0.12)",
    "accent": "#3d63f0", "accent-text": "#2f54de", "parent": "#e5713f", "cid": "#0ea5c9",
    "policy": "#8b4fe0", "policy-text": "#7a3fd1", "detect": "#e9b500", "detect-text": "#8a6a00",
    "on-pol": "#ffffff", "on-det": "#1d1e23", "link": "#a3a6b0", "link-dim": "#e3e4e8", "addl": "#9a9ca6",
    "hi": "#1d1e23", "ok": "#16a34a", "warn": "#d97706", "shadow": "0 8px 24px rgba(20, 20, 40, 0.12)"}}

# The two views, as (button label, hint, color): the selected view's button
# is filled with its color.
VIEW_STYLE = {"expected": ("Expected", "after the changes", "#7c4dff"),
              "today": ("Today", "current export", "#546e7a")}

# Graph layout, in px at 100% zoom: the root on top, centered, with its name
# to the right of its glyph; below it, one card per service line, in name
# order left to right, joined to the root through a bus (busY). A card has
# a header (headH: the line's glyph, name and child count) and one row per
# tenant (rowH), the tenants of the line by primary parent, tenants with an
# additional parent first, so their dashed links stay short. A tenant's
# link leaves the line's trunk (trunkInset from the card's left edge) and
# reaches its dot stub px to the right; a CID below a tenant is indented by
# indent px. The P (Policy Inheritance) and D (Detection Aggregation)
# badges sit in two columns at the right edge of each card. iconR is the
# radius of the parent glyph (rootScale times larger for the root).
# The view is framed to fit at most maxFit (zoom limits: minScale..maxScale).
LAYOUT = {
  "font": '"Segoe UI", system-ui, -apple-system, Roboto, "Helvetica Neue", Arial, sans-serif',
  "busY": 46, "cardGap": 26, "colGap": 34, "headH": 56, "rowH": 26, "rowPad": 8,
  "trunkInset": 22, "stub": 22, "indent": 18, "dotR": 6, "nameGap": 9, "padX": 12, "iconR": 11, "rootScale": 1.3,
  "badgeW": 18, "badgeH": 16, "badgeGap": 18, "badgeSpace": 4, "chipGap": 8,
  "minScale": 0.25, "maxScale": 3, "maxFit": 1.15}

# Problems found while loading: errors stop the run before anything is
# written, warnings are printed at the end.
errors, warnings = [], []



#################################### Part 2: CSV Loading ->

def fail():
  """Stops the run with every error collected so far - nothing is written."""
  if errors: sys.exit("ERROR:\n  " + "\n  ".join(errors))

def read_csv(path, header):
  """Rows as dicts with stripped values - a different header stops the run."""
  with open(path, encoding="utf-8-sig", newline="") as f:
    reader = csv.DictReader(f)
    if reader.fieldnames != header:
      sys.exit(f"ERROR: unexpected header in {path}:\n{reader.fieldnames}")
    return [{k: (v or "").strip() for k, v in r.items()} for r in reader]

def flag(value, where):
  """'true'/'false' -> bool; anything else is an error."""
  if value not in ("true", "false"):
    errors.append(f"{where}: expected true/false, got {value!r}")
  return value == "true"

def build(recs):
  """The tree of recs by primary parent: (order, kids, roots). order is the
  depth-first walk as (cid, depth); siblings in name order. A CID whose
  parent is not in recs is a root."""
  kids = {}
  for cid, r in recs.items():
    kids.setdefault(r["parent"] if r["parent"] in recs else "", []).append(cid)
  for lst in kids.values():
    lst.sort(key=lambda c: recs[c]["name"].casefold())
  roots = kids.pop("", [])
  order = []
  def walk(c, depth):
    order.append((c, depth))
    for k in kids.get(c, []): walk(k, depth + 1)
  for r in roots: walk(r, 0)
  return order, kids, roots

def load_today():
  """The export: {cid: record} and its tree. The export gives parents by
  name; they are kept by CID String."""
  if not os.path.isfile(INPUT):
    sys.exit(f"ERROR: {INPUT} not found - export the CID list from the Falcon console and save it there")
  rows = read_csv(INPUT, HEADER)
  name_to_cid = {}
  for r in rows:
    if not CID_RE.fullmatch(r["CID String"]):
      errors.append(f"invalid CID String for {r['CID Name']!r}: {r['CID String']!r}")
    if r["CID Name"] in name_to_cid:
      errors.append(f"duplicate CID Name: {r['CID Name']!r}")
    name_to_cid[r["CID Name"]] = r["CID String"]
  fail()
  today = {}
  for r in rows:
    name = r["CID Name"]
    for col in ("Parent", "Additional Parent"):
      if r[col] and r[col] not in name_to_cid:
        warnings.append(f"{col} of {name!r} not found in export: {r[col]!r}")
    if r["Status"] != "active":
      warnings.append(f"{name!r} status is {r['Status']!r}")
    if MAX_NAME and len(name) > MAX_NAME:
      warnings.append(f"{name!r} has {len(name)} characters (limit {MAX_NAME})")
    if INCIDENT_FOLLOWS_DETECTION and r["Incident Aggregation"] != r["Detection Aggregation"]:
      warnings.append(f"{name!r}: Incident Aggregation differs from Detection Aggregation")
    where = f"export row {name!r}"
    today[r["CID String"]] = {
      "name": name, "parent": name_to_cid.get(r["Parent"], ""),
      "addl": name_to_cid.get(r["Additional Parent"], ""), "status": r["Status"],
      "is_parent": r["Is Parent?"] == "true", "endpoints": r["Number of Endpoints"],
      "pol": flag(r["Policy Inheritance"], where), "det": flag(r["Detection Aggregation"], where),
      "inc": flag(r["Incident Aggregation"], where)}
  fail()
  order, kids, roots = build(today)
  if len(roots) != 1:
    warnings.append(f"expected 1 root CID in export, found {len(roots)}: {[today[c]['name'] for c in roots]}")
  for c, depth in order:
    if bool(kids.get(c)) != today[c]["is_parent"]:
      warnings.append(f"{today[c]['name']!r}: Is Parent?={today[c]['is_parent']} but has "
                      f"{len(kids.get(c, []))} children in export")
    if depth > 2:
      warnings.append(f"{today[c]['name']!r} is at depth {depth} (below a tenant); the graph draws it "
                      f"with the tenants of its service line")
  return today, (order, kids, roots)

def previous_expected():
  """The most recent CIDs_Expected.csv of an earlier day, or None."""
  if not os.path.isdir(OUTPUT): return None
  days = sorted(d for d in os.listdir(OUTPUT)
                if DAY_RE.fullmatch(d) and d < DAY and os.path.isfile(f"{OUTPUT}/{d}/CIDs_Expected.csv"))
  return f"{OUTPUT}/{days[-1]}/CIDs_Expected.csv" if days else None

def keep_expected():
  """--keep-expected: today's CIDs_Expected.csv starts as a copy of the most
  recent earlier one, to go on from where that review stopped. Refuses to
  overwrite an existing file."""
  if os.path.exists(EXPECTED):
    sys.exit(f"ERROR: {EXPECTED} already exists; delete it first to start over")
  previous = previous_expected()
  if not previous:
    sys.exit(f"ERROR: no CIDs_Expected.csv of an earlier day in {OUTPUT}/")
  os.makedirs(os.path.dirname(EXPECTED), exist_ok=True)
  shutil.copyfile(previous, EXPECTED)
  print(f"OK: copied {previous} to {EXPECTED}")

def init_expected(today, order):
  """--init-expected: today's CIDs_Expected.csv as a copy of the export, so
  nothing is pending. Refuses to overwrite an existing file."""
  if os.path.exists(EXPECTED):
    sys.exit(f"ERROR: {EXPECTED} already exists; delete it first to start over")
  os.makedirs(os.path.dirname(EXPECTED), exist_ok=True)
  with open(EXPECTED, "w", encoding="utf-8", newline="") as f:
    out = csv.writer(f, lineterminator="\n")
    out.writerow(EXP_HEADER)
    for c, _ in order:
      r = today[c]
      out.writerow([c, r["name"], r["parent"], r["addl"]] + [str(r[k]).lower() for _, k in FLAGS])
  print(f"OK: created {EXPECTED} from {INPUT}")

def load_expected(today):
  """Today's CIDs_Expected.csv: {cid: record} and its tree, or (None, None)
  when it does not exist. Every rule is checked here."""
  if not os.path.exists(EXPECTED): return None, None
  expected = {}
  seen_names = set()
  for r in read_csv(EXPECTED, EXP_HEADER):
    c, where = r["CID String"], f"expected row {r['CID Name']!r}"
    if not (CID_RE.fullmatch(c) or NEW_RE.fullmatch(c)):
      errors.append(f"{where}: CID String must be 32 lowercase hex or NEW-<n>, got {c!r}")
    elif CID_RE.fullmatch(c) and c not in today:
      errors.append(f"{where}: CID {c} is not in the export (new CIDs use NEW-<n>)")
    if c in expected:
      errors.append(f"duplicate CID String in expected: {c!r}")
    if r["CID Name"] in seen_names:
      errors.append(f"duplicate CID Name in expected: {r['CID Name']!r}")
    seen_names.add(r["CID Name"])
    t = today.get(c, {})
    expected[c] = {
      "name": r["CID Name"], "parent": r["Parent CID"], "addl": r["Additional Parent CID"],
      "status": t.get("status", "new"), "endpoints": t.get("endpoints", "0"),
      "pol": flag(r["Policy Inheritance"], where), "det": flag(r["Detection Aggregation"], where),
      "inc": flag(r["Incident Aggregation"], where)}
  for c, r in expected.items():
    for col in ("parent", "addl"):
      if r[col] and r[col] not in expected:
        errors.append(f"expected row {r['name']!r}: {col} {r[col]!r} is not in expected")
    if r["addl"] and r["addl"] == r["parent"]:
      errors.append(f"expected row {r['name']!r}: additional parent equals parent")
    if MAX_NAME and len(r["name"]) > MAX_NAME and r["name"] != today.get(c, {}).get("name"):
      errors.append(f"expected row {r['name']!r}: new name has {len(r['name'])} characters (limit {MAX_NAME})")
    if INCIDENT_FOLLOWS_DETECTION and r["inc"] != r["det"]:
      errors.append(f"expected row {r['name']!r}: Incident Aggregation must equal Detection Aggregation")
  fail()
  order, kids, roots = build(expected)
  if len(order) != len(expected):
    errors.append(f"expected has a parent cycle; unreachable: {sorted(set(expected) - {c for c, _ in order})}")
  fail()
  if len(roots) != 1:
    warnings.append(f"expected 1 root CID in expected, found {len(roots)}")
  for c, depth in order:
    if depth > 2:
      warnings.append(f"{expected[c]['name']!r} is at depth {depth} in expected (below a tenant); the graph "
                      f"draws it with the tenants of its service line")
  # a CID created by support shows up in the export with its real CID String
  by_name = {r["name"]: c for c, r in today.items() if c not in expected}
  for c, r in expected.items():
    if NEW_RE.fullmatch(c) and r["name"] in by_name:
      warnings.append(f"{c} {r['name']!r} now exists in the export as {by_name[r['name']]}; "
                      f"replace {c} with that CID String in {EXPECTED}")
  return expected, (order, kids, roots)



#################################### Part 3: Comparison ->

def onoff(value):
  return "enabled" if value else "disabled"

def name_of(c, today, expected):
  """The expected name when there is one, the export's otherwise."""
  return (expected or {}).get(c, today.get(c, {})).get("name", c)

def lab(c, today, expected, start=False):
  """A CID for the case text: its CID String and name, or 'new CID "<name>"'
  (capitalized when it starts a line). A CID String is never capitalized."""
  if NEW_RE.fullmatch(c):
    return f'{"New" if start else "new"} CID "{name_of(c, today, expected)}"'
  return f"{c} ({name_of(c, today, expected)})"

def diff(c, today, expected):
  """What changes on one CID from the export to the expected structure."""
  t, x = today.get(c), expected.get(c)
  d = {"delete": x is None, "create": t is None, "rename": None, "remove": [], "add": [],
       "keep": [], "flags": []}
  if t and x:
    by_name = lambda p: name_of(p, today, expected)
    if t["name"] != x["name"]: d["rename"] = (t["name"], x["name"])
    tp = {p for p in (t["parent"], t["addl"]) if p}
    xp = {p for p in (x["parent"], x["addl"]) if p}
    d["remove"] = sorted(tp - xp, key=by_name)
    d["add"] = sorted(xp - tp, key=by_name)
    d["keep"] = sorted(tp & xp, key=by_name)
    d["flags"] = [(label, k, x[k]) for label, k in FLAGS if t[k] != x[k]]
  return d

def changed(d):
  return d["delete"] or d["create"] or d["rename"] or d["remove"] or d["add"] or d["flags"]

def pending_summary(D):
  """One line with what is still pending, for the run output."""
  counts = [("creation", sum(1 for d in D.values() if d["create"])),
            ("rename", sum(1 for d in D.values() if d["rename"])),
            ("parent-link change", sum(1 for d in D.values() if not (d["create"] or d["delete"]) and (d["remove"] or d["add"]))),
            ("settings change", sum(1 for d in D.values() if d["flags"])),
            ("deletion", sum(1 for d in D.values() if d["delete"]))]
  pending = ", ".join(f"{n} {what}{'' if n == 1 else 's'}" for what, n in counts if n)
  if not pending: return "Export matches the expected structure: nothing pending."
  n_changed = sum(1 for d in D.values() if changed(d))
  return f"Pending to reach the expected structure: {pending}, on {n_changed} CID{'' if n_changed == 1 else 's'}."



#################################### Part 4: Case Message ->

def these(n):
  return "this CID" if n == 1 else f"these {n} CIDs"

def case_message(order, D, today, expected, x_info):
  """The step-by-step text for CrowdStrike support, from the export to the
  expected structure - None when nothing is pending."""
  x_order, x_kids, _ = x_info
  def ref(c, start=False): return lab(c, today, expected, start)
  def parents_phrase(cids): return ("parent " if len(cids) == 1 else "parents ") + " and ".join(ref(p) for p in cids)
  def under(p): return ref(p) + (" (created above)" if NEW_RE.fullmatch(p) else "")
  steps = []

  creates = [c for c in order if D[c]["create"]]
  if creates:
    items = []
    for c in creates:
      x = expected[c]
      s = f'"{x["name"]}" under parent {under(x["parent"])}'
      if x["addl"]: s += f", with additional parent {under(x['addl'])}"
      s += "; " + ", ".join(f"{label} {onoff(x[k])}" for label, k in FLAGS)
      items.append((c, s))
    intro = "this child CID" if len(items) == 1 else f"these {len(items)} child CIDs"
    steps.append(("CREATE CIDs", [(f"Please create {intro}:", items, None)]))

  renames = [c for c in order if D[c]["rename"]]
  if renames:
    steps.append(("RENAME CIDs", [(
      f"Please rename {these(len(renames))}. Format: CID string: current name -> new name.",
      [(c, f'{c}: "{D[c]["rename"][0]}" -> "{D[c]["rename"][1]}"') for c in renames], None)]))

  groups = {}
  for c in order:
    d = D[c]
    if d["delete"] or d["create"] or not (d["remove"] or d["add"]): continue
    final = sorted(set(d["keep"]) | set(d["add"]), key=lambda p: name_of(p, today, expected))
    groups.setdefault((tuple(d["remove"]), tuple(d["add"]), tuple(final)), []).append(c)
  subs = []
  for (rem, add, final), cids in groups.items():
    n = len(cids)
    if rem and add: s = f"Please move {these(n)} from {parents_phrase(rem)} to {parents_phrase(add)}."
    elif rem: s = f"Please remove {parents_phrase(rem)} from {these(n)}."
    else: s = f"Please link {these(n)} to {parents_phrase(add)}."
    own = "its" if n == 1 else "their"
    if len(final) == 1: s += f" After this change, parent CID {ref(final[0])} must be {own} only parent."
    elif final: s += f" After this change, {own} parents must be {' and '.join(ref(p) for p in final)}."
    else: s += f" After this change, {'it has' if n == 1 else 'they have'} no parent."
    subs.append((s, [(c, ref(c)) for c in cids], None))
  if subs: steps.append(("CHANGE PARENT LINKS", subs))

  subs = []
  for val in (False, True):
    for label, k in FLAGS:
      cids = [c for c in order if (label, k, val) in D[c]["flags"]]
      if cids:
        subs.append((f"Please {'enable' if val else 'disable'} {label} on {these(len(cids))}:",
                     [(c, ref(c)) for c in cids], None))
  if subs: steps.append(("CHANGE SETTINGS", subs))

  deletes = [c for c in order if D[c]["delete"]]
  if deletes:
    items = []
    for c in deletes:
      t = today[c]
      s = ref(c) + (f", a child of {ref(t['parent'])}" if t["parent"] else "")
      if t["endpoints"] not in ("", "0"): s += f". It still has {t['endpoints']} endpoints registered."
      items.append((c, s))
    steps.append(("DELETE CIDs", [(f"Please delete {these(len(deletes))}:", items,
                  "If anything needs to be done on our side before the deletion (for example, "
                  "uninstalling the sensors or a written approval), please let us know.")]))
  if not steps: return None

  lines = ["Hello,", "", "Please make the changes below.", "", "GENERAL NOTES",
           "- Please identify every CID by its CID string."]
  if INCIDENT_FOLLOWS_DETECTION:
    lines.append("- Rule for all CIDs: Incident Aggregation must always have the same value as Detection Aggregation.")
  rename_step = [i for i, s in enumerate(steps, 1) if s[0] == "RENAME CIDs"]
  if rename_step and rename_step[0] < len(steps):
    lines.append(f"- Some CIDs are renamed in Step {rename_step[0]}, so the names shown in later steps are the "
                 f"names after the rename.")
  if len(steps) > 1:
    lines.append(f"- Please do the steps in order: {', '.join(str(i) for i in range(1, len(steps) + 1))}.")
  lines.append("- Please do not change anything that is not listed below.")

  appears = {}
  for i, (title, subs) in enumerate(steps, 1):
    lines += ["", "", f"STEP {i} - {title}"]
    for j, (intro, items, footer) in enumerate(subs, 1):
      num = f"{i}.{j}"
      lines += ["", f"{num} {intro}"]
      for c, s in items:
        lines.append("- " + s)
        appears.setdefault(c, []).append(num)
      if footer: lines.append(footer)

  inactive = [c for c in appears if today.get(c, {}).get("status", "active") != "active"]
  if inactive:
    lines += ["", "", "INACTIVE CIDs"]
    for c in inactive:
      lines.append(f"{ref(c)} is {today[c]['status']}. It appears in Step {', '.join(appears[c])}. If the console "
                   f"does not allow changes to it, please skip it, continue with the rest, and let us know in the case.")

  lines += ["", "", "EXPECTED RESULT", f"- {len(expected)} CIDs in total."]
  for c in deletes:
    lines.append(f"- {ref(c)} no longer exists.")
  for c, _ in x_order:
    extra = sum(1 for r in expected.values() if r["addl"] == c)
    n = len(x_kids.get(c, [])) + extra
    if n:
      lines.append(f"- {ref(c, start=True)} has {n} child CID{'' if n == 1 else 's'}"
                   f"{f' ({extra} of them as additional parent)' if extra else ''}.")
  addl = [c for c, _ in x_order if expected[c]["addl"]]
  for c in addl:
    lines.append(f"- {ref(c, start=True)} also has additional parent {ref(expected[c]['addl'])}.")
  if not addl: lines.append("- No CID has an additional parent.")
  total = len(expected)
  for label, k in FLAGS:
    on = [c for c, _ in x_order if expected[c][k]]
    off = [c for c, _ in x_order if not expected[c][k]]
    if not off: lines.append(f"- {label} is enabled on all {total} CIDs.")
    elif not on: lines.append(f"- {label} is disabled on all {total} CIDs.")
    elif len(on) <= 5: lines.append(f"- {label} is enabled only on: {'; '.join(ref(c) for c in on)}.")
    elif len(off) <= 5: lines.append(f"- {label} is disabled only on: {'; '.join(ref(c) for c in off)}.")
    else: lines.append(f"- {label} is enabled on {len(on)} CIDs and disabled on {len(off)} CIDs.")
  if not renames: lines.append("- CID names do not change.")
  if not (groups or creates or deletes): lines.append("- Parent links do not change.")
  lines += ["", "Thanks,", ""]
  return "\n".join(lines)



#################################### Part 5: Graph Data ->

e = html.escape

def view_data(recs, info):
  """One view (expected or today) for the page script: its CIDs in tree
  order, each with what the graph, the table and the details card show.
  'line' is the service line a CID sits under by primary parent (itself for
  a service line, empty for the root)."""
  order, kids, roots = info
  root_set = set(roots)

  def line_of(c):
    while recs[c]["parent"] in recs and recs[c]["parent"] not in root_set:
      c = recs[c]["parent"]
    return c

  cids = []
  for c, d in order:
    r = recs[c]
    cids.append({
      "id": c, "name": r["name"], "depth": d, "line": line_of(c) if d else "",
      "parent": r["parent"] if r["parent"] in recs else "", "addl": r["addl"] if r["addl"] in recs else "",
      "status": r["status"], "endpoints": r["endpoints"], "new": bool(NEW_RE.fullmatch(c)),
      "pol": r["pol"], "det": r["det"], "inc": r["inc"]})
  return {"cids": cids}

def js(value):
  """JSON for an inline <script>: '</' is escaped so no string can close the tag."""
  return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")

def css_vars(theme):
  """A theme as CSS custom properties: {'bg': '#000'} -> '--bg: #000; '."""
  return "".join(f"--{k}: {v}; " for k, v in theme.items())



#################################### Part 6: Page Template ->

# The page around the graph, in the layout of the Falcon console: a header
# (name, search, view switch, theme), the Graph and Table tabs, the graph
# pane (toolbar, legend, source stamp), the table pane and the details
# drawer. The %%NAME%% markers are filled in by build_page(); the page
# script (Part 7) draws the rest from DATA.
PAGE = """<!doctype html>
<html lang="en" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%%TAB_TITLE%%</title>
<link rel="icon" href="%%FAVICON%%">
<style>%%CSS%%</style>
</head>
<body>
<header class="topbar">
  <div class="brand">
    <svg class="brand-icon" width="22" height="22" viewBox="-12 -12 24 24" aria-hidden="true"><g class="glyph">%%GLYPH%%</g></svg>
    <span class="brand-app">%%APP%%</span>
    <span class="brand-sep"></span>
    <span class="brand-page">%%PAGE%%</span>
    <span class="brand-company">%%COMPANY%%</span>
  </div>
  <label class="search">
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg>
    <input id="search" type="search" placeholder="Search CID name or string" autocomplete="off" spellcheck="false" aria-label="Search CIDs">
    <kbd>/</kbd>
  </label>
  <div class="top-right">
    <div class="seg" id="view-seg" role="group" aria-label="View">%%VIEW_BUTTONS%%</div>
    <button type="button" class="icon-btn" id="theme-btn" aria-label="Switch between light and dark theme">
      <svg class="i-sun" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>
      <svg class="i-moon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>
    </button>
  </div>
</header>
<nav class="tabs" role="tablist" aria-label="Views of the hierarchy">
  <button type="button" role="tab" class="tab" data-tab="graph" aria-selected="true">Graph</button>
  <button type="button" role="tab" class="tab" data-tab="table" aria-selected="false">Table</button>
</nav>
<main>
  <section id="graph-pane" class="pane">
    <svg id="graph" role="img" aria-label="CID hierarchy graph"><g id="viewport"></g></svg>
    <div id="overlay-left">
      <div class="toolbar" role="toolbar" aria-label="Graph tools">
        <button type="button" id="tb-legend" title="Show or hide the legend" aria-pressed="true"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16"/></svg></button>
        <button type="button" id="tb-fit" title="Fit to screen"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 9V5h4M16 4h4v4M20 15v4h-4M8 20H4v-4"/></svg></button>
        <button type="button" id="tb-in" title="Zoom in"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg></button>
        <button type="button" id="tb-out" title="Zoom out"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M5 12h14"/></svg></button>
      </div>
      <aside id="legend" class="legend" aria-label="Legend"></aside>
    </div>
    <div id="empty" class="empty" hidden>No CIDs to show. Turn a service line back on in the legend.</div>
    <div id="stamp" class="stamp"></div>
  </section>
  <section id="table-pane" class="pane" hidden>
    <div id="table-bar" class="table-bar"></div>
    <div class="table-wrap"><table id="cid-table"></table></div>
  </section>
  <aside id="drawer" class="drawer" aria-hidden="true" aria-label="CID details"></aside>
</main>
<script>%%SCRIPT%%</script>
</body>
</html>
"""

PAGE_CSS = r"""
:root { %%DARK%% --font: %%FONT%%; --mono: Consolas, "Cascadia Mono", "SFMono-Regular", Menlo, monospace; color-scheme: dark; }
:root[data-theme="light"] { %%LIGHT%% color-scheme: light; }
*, *::before, *::after { box-sizing: border-box; }
html, body { height: 100%; margin: 0; }
body {
  display: flex; flex-direction: column; overflow: hidden; background: var(--bg); color: var(--text);
  font: 13px/1.45 var(--font); -webkit-font-smoothing: antialiased;
}
button { font: inherit; color: inherit; }
[hidden] { display: none !important; }
:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }

/* header */
.topbar {
  flex: none; height: 52px; display: grid; align-items: center; gap: 16px; padding: 0 16px;
  grid-template-columns: minmax(0, 1fr) minmax(220px, 440px) minmax(0, 1fr);
  background: var(--bar); border-bottom: 1px solid var(--border);
}
.brand { display: flex; align-items: center; gap: 10px; min-width: 0; white-space: nowrap; }
.brand-icon { flex: none; }
.brand-app { font-size: 14px; font-weight: 700; }
.brand-sep { width: 1px; height: 18px; background: var(--border); flex: none; }
.brand-page { color: var(--muted); }
.brand-company { color: var(--faint); overflow: hidden; text-overflow: ellipsis; }
.brand-company:not(:empty)::before { content: "·"; margin-right: 10px; }
.search {
  display: flex; align-items: center; gap: 8px; height: 34px; padding: 0 10px; border-radius: 8px;
  border: 1px solid var(--border); background: var(--field); color: var(--muted);
}
.search:focus-within { border-color: var(--accent); }
.search input { flex: 1; min-width: 0; border: 0; outline: 0; background: transparent; color: var(--text); font: inherit; }
.search input::placeholder { color: var(--faint); }
.search kbd { font: 11px var(--font); color: var(--faint); border: 1px solid var(--border); border-radius: 4px; padding: 0 6px; }
.top-right { display: flex; justify-content: flex-end; align-items: center; gap: 10px; }
.seg { display: inline-flex; gap: 2px; padding: 3px; border-radius: 9px; border: 1px solid var(--border); background: var(--field); }
.seg button {
  display: inline-flex; align-items: center; gap: 7px; padding: 4px 12px; border: 0; border-radius: 6px;
  background: transparent; color: var(--muted); font-weight: 600; cursor: pointer;
}
.seg button:hover { color: var(--text); }
.seg .sw { width: 8px; height: 8px; border-radius: 50%; background: var(--vc); }
.seg button[aria-pressed="true"] { background: var(--vc); color: #fff; }
.seg button[aria-pressed="true"] .sw { background: #fff; }
.icon-btn {
  width: 34px; height: 34px; display: grid; place-items: center; flex: none; border: 0; border-radius: 8px;
  background: transparent; color: var(--muted); cursor: pointer;
}
.icon-btn:hover { background: var(--hover); color: var(--text); }
:root[data-theme="dark"] .i-moon, :root[data-theme="light"] .i-sun { display: none; }
.tabs { flex: none; display: flex; justify-content: center; gap: 30px; height: 44px; background: var(--bar); border-bottom: 1px solid var(--border); }
.tab { position: relative; padding: 0 8px; border: 0; background: none; color: var(--muted); font-size: 15px; cursor: pointer; }
.tab:hover { color: var(--text); }
.tab[aria-selected="true"] { color: var(--text); }
.tab[aria-selected="true"]::after {
  content: ""; position: absolute; left: -6px; right: -6px; bottom: -1px; height: 3px;
  border-radius: 3px 3px 0 0; background: var(--accent);
}
main { position: relative; flex: 1; min-height: 0; }
.pane { position: absolute; inset: 0; background: var(--canvas); }

/* graph */
#graph-pane { overflow: hidden; }
#graph { display: block; width: 100%; height: 100%; cursor: grab; touch-action: none; user-select: none; }
#graph.panning { cursor: grabbing; }
#graph text { font-family: var(--font); fill: var(--text); }
.card { fill: var(--card); stroke: var(--card-border); }
.card-div { fill: none; stroke: var(--card-border); }
.card-g.ctx { opacity: 0.55; }
.link { fill: none; stroke: var(--link); stroke-width: 1.4; }
.link.pol { stroke: var(--policy); stroke-width: 1.8; }
.link.addl { stroke: var(--addl); stroke-width: 1.2; stroke-dasharray: 5 4; }
.link.dim { stroke: var(--link-dim); }
.halo { fill: none; stroke: var(--canvas); stroke-width: 6; }
.port { fill: var(--addl); }
.port.dim { fill: var(--link-dim); }
.link-hi { fill: none; stroke: var(--hi); stroke-width: 2; }
.link-hi.pol { stroke: var(--policy); stroke-width: 2.4; }
.link-hi.addl { stroke-dasharray: 5 4; }
.row, .node { cursor: pointer; transition: opacity 0.15s; }
.row.dim, .node.dim { opacity: 0.3; }
.node-bg { fill: transparent; }
.row:hover .node-bg, .node:hover .node-bg { fill: var(--hover); }
.row.sel .node-bg, .node.sel .node-bg { fill: var(--sel-row); }
.glyph { fill: var(--parent); }
.node.ctx .glyph { opacity: 0.6; }
.dot { fill: var(--cid); }
.row.sel .dot { stroke: var(--hi); stroke-width: 2.5; }
.row.inactive .dot { fill: none; stroke: var(--faint); stroke-width: 1.6; }
#graph .row.inactive .t-name { fill: var(--faint); }
#graph .t-name { font-size: 13px; }
#graph .t-pre { fill: var(--muted); }
#graph .row.match .t-name { fill: var(--accent-text); }
#graph .t-head { font-size: 14px; font-weight: 600; }
#graph .t-sub { font-size: 11.5px; fill: var(--muted); }
#graph .badge text, .lg-badge text { font-size: 10px; font-weight: 700; text-anchor: middle; font-family: var(--font); }
.badge.pol rect, .lg-badge.pol rect { fill: var(--policy); }
.badge.det rect, .lg-badge.det rect { fill: var(--detect); }
#graph .badge.pol text, .lg-badge.pol text { fill: var(--on-pol); }
#graph .badge.det text, .lg-badge.det text { fill: var(--on-det); }
.chip rect { fill: none; stroke: var(--border); }
#graph .chip text { font-size: 10.5px; fill: var(--muted); }

/* toolbar and legend */
#overlay-left { position: absolute; top: 14px; left: 14px; z-index: 4; display: flex; align-items: flex-start; gap: 8px; max-height: calc(100% - 28px); }
.toolbar {
  display: flex; flex-direction: column; gap: 2px; padding: 4px; border-radius: 10px;
  background: var(--panel); border: 1px solid var(--border); box-shadow: var(--shadow);
}
.toolbar button {
  width: 32px; height: 32px; display: grid; place-items: center; border: 0; border-radius: 7px;
  background: transparent; color: var(--muted); cursor: pointer;
}
.toolbar button:hover { background: var(--hover); color: var(--text); }
.toolbar button[aria-pressed="true"] { background: var(--hover-strong); color: var(--text); }
.legend {
  width: 296px; max-height: calc(100vh - 140px); overflow-y: auto; border-radius: 10px;
  background: var(--panel); border: 1px solid var(--border); box-shadow: var(--shadow);
  scrollbar-width: thin; scrollbar-color: var(--border) transparent;
}
.lg-title {
  display: flex; align-items: center; justify-content: space-between; padding: 8px 8px 8px 16px;
  font-size: 15px; font-weight: 700; border-bottom: 1px solid var(--border);
}
.lg-row {
  display: grid; grid-template-columns: 24px minmax(0, 1fr) auto 28px; align-items: center; gap: 10px;
  min-height: 42px; padding: 4px 8px 4px 16px; border-bottom: 1px solid var(--border-soft);
}
.lg-row:last-child { border-bottom: 0; }
.lg-ico { display: grid; place-items: center; color: var(--muted); }
.lg-label { min-width: 0; font-weight: 500; }
.lg-n { color: var(--muted); font-variant-numeric: tabular-nums; }
.lg-btn {
  width: 28px; height: 28px; display: grid; place-items: center; border: 0; border-radius: 6px;
  background: transparent; color: var(--muted); cursor: pointer;
}
.lg-btn:hover { background: var(--hover); color: var(--text); }
.lg-btn svg { transition: transform 0.15s; }
.lg-btn.open svg { transform: rotate(180deg); }
.lg-row.off .lg-ico, .lg-row.off .lg-label, .lg-row.off .lg-n { opacity: 0.45; }
.lg-sub { background: var(--panel-2); border-bottom: 1px solid var(--border-soft); padding: 4px 0; }
.lg-sub .lg-row { min-height: 34px; padding-left: 30px; border-bottom: 0; grid-template-columns: 16px minmax(0, 1fr) auto 28px; }
.lg-solo {
  min-width: 0; padding: 0; border: 0; background: none; color: var(--text); font-size: 12.5px; text-align: left;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; cursor: pointer;
}
.lg-solo:hover { text-decoration: underline; }
.lg-row.solo .lg-solo { color: var(--accent-text); font-weight: 600; }
.lg-reset { display: block; margin: 2px 0 6px 30px; padding: 2px 0; border: 0; background: none; color: var(--accent-text); font-size: 12px; cursor: pointer; }
.lg-reset:hover { text-decoration: underline; }
.lg-section {
  padding: 12px 16px 6px; font-size: 10.5px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase;
  color: var(--faint); border-bottom: 1px solid var(--border-soft);
}
.ico-dot { width: 12px; height: 12px; border-radius: 50%; background: var(--cid); }
.ico-dot.off { background: none; border: 1.6px solid var(--faint); }
.stamp { position: absolute; right: 16px; bottom: 12px; z-index: 2; color: var(--faint); font-size: 11.5px; pointer-events: none; }
.stamp b { color: var(--muted); font-weight: 600; }
.empty { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); color: var(--muted); }

/* table */
#table-pane { display: flex; flex-direction: column; }
body.has-drawer #table-pane { right: 380px; }
.table-bar { flex: none; display: flex; align-items: center; flex-wrap: wrap; gap: 8px; padding: 14px 24px; border-bottom: 1px solid var(--border); }
.chip-btn {
  display: inline-flex; align-items: center; gap: 7px; height: 30px; padding: 0 12px; border-radius: 15px;
  border: 1px solid var(--border); background: var(--panel); color: var(--faint); cursor: pointer;
}
.chip-btn:hover { color: var(--text); }
.chip-btn[aria-pressed="true"] { color: var(--text); border-color: var(--accent); }
.chip-btn[aria-pressed="false"] svg { opacity: 0.4; }
.link-btn { border: 0; background: none; color: var(--accent-text); cursor: pointer; padding: 0 6px; }
.link-btn:hover { text-decoration: underline; }
.bar-n { margin-left: auto; color: var(--muted); font-variant-numeric: tabular-nums; }
.bar-n b { color: var(--text); }
.table-wrap { flex: 1; overflow: auto; padding: 0 24px 24px; scrollbar-width: thin; scrollbar-color: var(--border) transparent; }
#cid-table { width: 100%; border-collapse: separate; border-spacing: 0; font-variant-numeric: tabular-nums; }
#cid-table th {
  position: sticky; top: 0; z-index: 1; padding: 0; text-align: left; background: var(--canvas);
  border-bottom: 1px solid var(--border); white-space: nowrap;
}
#cid-table th button {
  display: flex; align-items: center; gap: 4px; width: 100%; padding: 14px 12px 10px; border: 0; background: none;
  color: var(--muted); font-size: 11px; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; cursor: pointer;
}
#cid-table th button:hover { color: var(--text); }
#cid-table th.num button { justify-content: flex-end; }
#cid-table th[aria-sort="ascending"] button, #cid-table th[aria-sort="descending"] button { color: var(--text); }
#cid-table td { padding: 7px 12px; border-bottom: 1px solid var(--border-soft); white-space: nowrap; }
#cid-table td.num { text-align: right; }
#cid-table tbody tr { cursor: pointer; }
#cid-table tbody tr:hover td { background: var(--hover); }
#cid-table tbody tr.sel td { background: var(--sel-row); }
.nm { display: inline-flex; align-items: center; gap: 9px; }
.t-dot { width: 10px; height: 10px; border-radius: 50%; background: var(--cid); flex: none; margin: 0 3px; }
.t-dot.off { background: none; border: 1.5px solid var(--faint); }
.muted { color: var(--faint); }
.c-cid { display: flex; align-items: center; gap: 6px; }
.c-cid code { font: 12px var(--mono); color: var(--muted); }
.copy {
  width: 26px; height: 26px; display: grid; place-items: center; border: 0; border-radius: 6px;
  background: transparent; color: var(--faint); cursor: pointer;
}
.copy:hover, .copy.done { background: var(--hover); color: var(--text); }
.empty-row { text-align: center; padding: 32px !important; }

/* chips used in the table and the drawer */
.pill {
  display: inline-flex; align-items: center; gap: 6px; height: 22px; padding: 0 9px; border-radius: 11px;
  border: 1px solid var(--border); color: var(--muted); font-size: 11.5px; font-weight: 600; white-space: nowrap;
}
.pill i { width: 7px; height: 7px; border-radius: 50%; }
.pill.ok i { background: var(--ok); }
.pill.warn i { background: var(--warn); }
.pill.new { color: var(--accent-text); border-color: var(--accent); }
.pill.pol { color: var(--policy-text); border-color: color-mix(in srgb, var(--policy) 60%, transparent); background: color-mix(in srgb, var(--policy) 14%, transparent); }
.pill.det { color: var(--detect-text); border-color: color-mix(in srgb, var(--detect) 60%, transparent); background: color-mix(in srgb, var(--detect) 14%, transparent); }
.pill.off { color: var(--faint); border-color: transparent; padding: 0; }

/* details drawer */
.drawer {
  position: absolute; top: 0; right: 0; bottom: 0; z-index: 6; width: 380px; max-width: 100%; overflow-y: auto;
  background: var(--panel); border-left: 1px solid var(--border); box-shadow: var(--shadow);
  transform: translateX(105%); transition: transform 0.2s ease; visibility: hidden;
}
.drawer.open { transform: none; visibility: visible; }
.dw-head {
  position: sticky; top: 0; z-index: 1; display: flex; align-items: flex-start; gap: 12px; padding: 18px 12px 16px 20px;
  background: var(--panel); border-bottom: 1px solid var(--border);
}
.dw-head > svg { margin-top: 1px; flex: none; }
.dw-title { flex: 1; min-width: 0; }
.dw-name { font-size: 16px; font-weight: 700; line-height: 1.3; overflow-wrap: anywhere; }
.dw-kind { margin-top: 3px; color: var(--muted); font-size: 12px; }
.dw-sec { padding: 14px 20px; border-bottom: 1px solid var(--border-soft); }
.dw-label { margin-bottom: 8px; color: var(--faint); font-size: 10.5px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; }
.dw-cid { display: flex; align-items: center; gap: 10px; }
.dw-cid code { flex: 1; font: 12px/1.4 var(--mono); overflow-wrap: anywhere; }
.btn-sm {
  flex: none; height: 26px; padding: 0 10px; border-radius: 6px; border: 1px solid var(--border);
  background: var(--panel-2); color: var(--muted); font-size: 12px; cursor: pointer;
}
.btn-sm:hover { color: var(--text); }
.dw-stats { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; padding: 14px 20px; border-bottom: 1px solid var(--border-soft); }
.dw-num { font-size: 18px; font-weight: 700; font-variant-numeric: tabular-nums; }
.dw-set { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 4px 0; }
.dw-go {
  display: flex; align-items: center; gap: 9px; width: calc(100% + 16px); margin: 0 -8px; padding: 6px 8px;
  border: 0; border-radius: 6px; background: none; color: var(--text); text-align: left; cursor: pointer;
}
.dw-go:hover { background: var(--hover); }
.dw-go > span:nth-child(2) { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tag { margin-left: auto; flex: none; padding: 0 6px; border: 1px solid var(--border); border-radius: 4px; color: var(--muted); font-size: 10.5px; }
.mini-dot { width: 9px; height: 9px; margin: 0 2.5px; border-radius: 50%; background: var(--cid); flex: none; }
.mini-dot.off { background: none; border: 1.5px solid var(--faint); }
.dw-none { color: var(--faint); }
"""



#################################### Part 7: Page Script ->

# Draws the page from DATA (both views) and LAYOUT: the graph (an SVG with
# its own pan and zoom, no external library, so the page also opens
# offline), the legend with its show/hide toggles, the table, the search and
# the details drawer.
PAGE_SCRIPT = r"""
(() => {
  'use strict';

  const L = LAYOUT, VIEWS = DATA.views;
  const NAME_FONT = `13px ${L.font}`, HEAD_FONT = `600 14px ${L.font}`, SUB_FONT = `11.5px ${L.font}`,
        CHIP_FONT = `10.5px ${L.font}`;
  const IR = L.iconR, RS = L.iconR * L.rootScale;
  const $ = id => document.getElementById(id);
  const svg = $('graph'), port = $('viewport'), drawer = $('drawer');

  // ---------- icons
  const icon = (d, size = 16) => `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" ` +
    `stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${d}</svg>`;
  const EYE = icon('<path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>');
  const EYE_OFF = icon('<path d="M10.6 5.1A10 10 0 0 1 12 5c6.4 0 10 7 10 7a17 17 0 0 1-2.4 3.3M6.6 6.6C3.7 8.4 2 12 2 12s3.6 7 10 7a9.7 9.7 0 0 0 5.4-1.6"/><path d="M9.9 9.9a3 3 0 0 0 4.2 4.2"/><path d="M3 3l18 18"/>');
  const CHEVRON = icon('<path d="M6 9l6 6 6-6"/>');
  const CLOSE = icon('<path d="M18 6L6 18M6 6l12 12"/>', 18);
  const COPY = icon('<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/>', 14);
  const PANEL = icon('<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16"/>');
  const STACK = icon('<rect x="3" y="8" width="13" height="13" rx="2"/><path d="M8 8V5a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-3"/>', 18);
  const LG_LINK = '<svg width="24" height="10" aria-hidden="true"><path d="M1 5h22" style="stroke: var(--link); stroke-width: 1.8"/></svg>';
  const LG_ADDL = '<svg width="24" height="10" aria-hidden="true"><path d="M1 5h18" style="stroke: var(--addl); stroke-width: 1.6; stroke-dasharray: 4 3"/><circle cx="21" cy="5" r="2.6" style="fill: var(--addl)"/></svg>';
  const lgBadge = (cls, letter) => `<svg class="lg-badge ${cls}" width="20" height="16" aria-hidden="true"><rect x="1" y="0" width="18" height="16" rx="4"/>` +
    `<text x="10" y="8" dy="0.35em">${letter}</text></svg>`;
  const r1 = x => Math.round(x * 10) / 10;
  const PETALS = [[0, 0], ...[0, 1, 2, 3, 4, 5].map(i => [7.2 * Math.cos(i * Math.PI / 3), 7.2 * Math.sin(i * Math.PI / 3)])]
    .map(([x, y]) => `<circle cx="${r1(x)}" cy="${r1(y)}" r="3.3"/>`).join('');
  const glyph = (x, y, s) => `<g class="glyph" transform="translate(${r1(x)},${r1(y)}) scale(${s})">${PETALS}</g>`;
  const glyphIcon = size => `<svg width="${size}" height="${size}" viewBox="-12 -12 24 24" aria-hidden="true">${glyph(0, 0, 1)}</svg>`;

  // ---------- data: each view indexed by CID, with its children (primary and additional)
  for (const v of Object.values(VIEWS)) {
    v.byId = {};
    v.kids = {};
    v.cids.forEach((c, i) => { c.row = i; v.byId[c.id] = c; });
    for (const c of v.cids) for (const p of [c.parent, c.addl]) if (p) (v.kids[p] = v.kids[p] || []).push(c.id);
  }

  const state = {view: DATA.order[0], tab: 'graph', hidden: new Set(), solo: '',
                 show: {pol: true, det: true, addl: true}, selected: '', query: '',
                 sort: {key: '', dir: 1}, legend: window.innerWidth >= 1500, linesOpen: true};
  let T = {x: 0, y: 0, k: 1}, lay = null, needFit = true, anim = 0;

  // ---------- helpers
  const esc = s => String(s).replace(/[&<>"']/g, ch => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[ch]));
  const fmt = n => (n === '' || n == null || !isFinite(Number(n))) ? '—' : Number(n).toLocaleString('en-US');
  const cap = s => s ? s[0].toUpperCase() + s.slice(1) : s;
  const short = name => { const i = name.lastIndexOf('|'); return i === -1 ? name : name.slice(i + 1).trim(); };
  const number = name => name.includes(' - ') ? name.split(' - ')[0].trim() : '';
  const splitName = name => { const i = name.indexOf(' | '); return i > 0 && i <= 6 ? [name.slice(0, i + 3), name.slice(i + 3)] : ['', name]; };
  const kidsOf = (v, id) => v.kids[id] || [];
  const label = (v, id) => { const c = v.byId[id]; return c.depth < 2 ? short(c.name) : c.name; };
  const lineTag = (v, id) => { const c = v.byId[id]; if (!c) return ''; const n = number(c.name); return (n ? n + ' · ' : '') + short(c.name); };
  const linesOf = v => DATA.lineOrder.filter(id => v.byId[id] && v.byId[id].depth === 1);
  const inactive = c => !c.new && c.status !== 'active';
  const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;
  const lineSub = (v, c) => {
    const n = number(c.name), kids = kidsOf(v, c.id), extra = kids.filter(k => v.byId[k].addl === c.id).length;
    return (n ? n + ' · ' : '') + plural(kids.length, 'child CID') + (extra ? ` (${extra} additional)` : '');
  };
  const rootSub = (v, c) => 'Root CID · ' + plural(kidsOf(v, c.id).length, 'child CID');
  const statusPill = c => c.new ? '<span class="pill new">To be created</span>' :
    `<span class="pill ${c.status === 'active' ? 'ok' : 'warn'}"><i></i>${esc(cap(c.status))}</span>`;
  const onOff = (on, cls) => `<span class="pill ${on ? cls : 'off'}">${on ? 'Enabled' : 'Disabled'}</span>`;

  const measure = document.createElement('canvas').getContext('2d'), widths = new Map();
  function textW(text, font) {
    const key = font + '|' + text;
    if (!widths.has(key)) { measure.font = font; widths.set(key, measure.measureText(text).width); }
    return widths.get(key);
  }

  // ---------- what is shown: the service lines switched on (all, or only the
  // "solo" one); a tenant shows when its line or its additional parent's line
  // is on, and brings its parents up to the root
  const lineOn = id => state.solo ? state.solo === id : !state.hidden.has(id);
  function ancestors(v, id, out) {
    const c = v.byId[id];
    for (const p of [c.parent, c.addl]) if (p && !out.has(p)) { out.add(p); ancestors(v, p, out); }
    return out;
  }
  function visibleSet(v) {
    const vis = new Set();
    for (const c of v.cids) {
      if (c.depth === 0) continue;
      const via = c.depth >= 2 && c.addl ? v.byId[c.addl].line : '';
      if (lineOn(c.line) || (via && lineOn(via))) vis.add(c.id);
    }
    for (const id of [...vis]) ancestors(v, id, vis);
    if (!linesOf(v).length) for (const c of v.cids) vis.add(c.id);
    return vis;
  }
  function matchSet(v) {
    const q = state.query.trim().toLowerCase();
    if (!q) return null;
    return new Set(v.cids.filter(c => c.name.toLowerCase().includes(q) || c.id.includes(q)).map(c => c.id));
  }
  // the clicked CID, its parents up to the root and its children down
  function chainOf(v, id) {
    const set = ancestors(v, id, new Set([id]));
    const down = x => kidsOf(v, x).forEach(k => { if (!set.has(k)) { set.add(k); down(k); } });
    down(id);
    return set;
  }

  // ---------- layout: the root on top, one card per service line below it
  const chipText = (v, c) => '+ ' + label(v, c.addl);
  const chipW = (v, c) => textW(chipText(v, c), CHIP_FONT) + 14;
  const badgeX = col => col.x + col.w - L.padX - 2 * L.badgeW - L.badgeSpace;
  function rootLabelW(v, c) { return Math.max(textW(short(c.name), HEAD_FONT), textW(rootSub(v, c), SUB_FONT)); }

  function layout(v, vis) {
    const pos = {}, ext = {}, cols = [], colOf = {}, top = L.busY + L.cardGap;
    let x = 0;
    for (const id of linesOf(v)) {
      if (!vis.has(id)) continue;
      const line = v.byId[id];
      const first = v.cids.filter(c => c.depth === 2 && c.parent === id && vis.has(c.id))
        .sort((a, b) => (!!b.addl - !!a.addl) || (a.row - b.row));
      const rows = [];
      const add = list => list.forEach(c => {
        rows.push(c);
        add(kidsOf(v, c.id).map(k => v.byId[k]).filter(k => k.parent === c.id && vis.has(k.id)).sort((a, b) => a.row - b.row));
      });
      add(first);
      let inner = 0;
      for (const c of rows) {
        inner = Math.max(inner, (c.depth - 2) * L.indent + textW(c.name, NAME_FONT) +
                                (c.addl && state.show.addl ? L.chipGap + chipW(v, c) : 0));
      }
      const head = Math.max(textW(short(line.name), HEAD_FONT), textW(lineSub(v, line), SUB_FONT));
      const w = Math.max(L.trunkInset + L.stub + L.dotR + L.nameGap + inner, L.trunkInset + IR + 12 + head) +
                L.badgeGap + 2 * L.badgeW + L.badgeSpace + L.padX;
      // a line with no tenant to show (one that is only an additional parent here) keeps just its header
      const col = {line, rows, x, w, top, trunk: x + L.trunkInset, iconY: top + L.headH / 2, index: cols.length,
                   h: L.headH + (rows.length ? 2 * L.rowPad + rows.length * L.rowH : 0)};
      pos[id] = {x: col.trunk, y: col.iconY};
      ext[id] = x + w;
      rows.forEach((c, i) => {
        pos[c.id] = {x: col.trunk + L.stub + (c.depth - 2) * L.indent, y: top + L.headH + L.rowPad + (i + 0.5) * L.rowH};
        ext[c.id] = x + w;
      });
      colOf[id] = cols.length;
      cols.push(col);
      x += w + L.colGap;
    }
    const width = Math.max(0, x - L.colGap);
    const roots = v.cids.filter(c => c.depth === 0 && vis.has(c.id));
    let left = -30, right = width + 8;
    roots.forEach((c, i) => {
      const p = pos[c.id] = {x: width / 2 + i * 300, y: 0};
      ext[c.id] = p.x + RS + 26 + rootLabelW(v, c) + 2 * L.badgeW + L.badgeSpace;
      left = Math.min(left, p.x - RS - 10);
      right = Math.max(right, ext[c.id] + 10);
    });
    const bottom = Math.max(RS, ...cols.map(c => c.top + c.h)) + 8;
    return {pos, ext, cols, colOf, roots, box: {x1: left, y1: -RS - 10, x2: right, y2: bottom}};
  }

  // ---------- graph drawing
  // an orthogonal path through the points, with rounded corners
  function route(pts, rad) {
    let d = `M${r1(pts[0][0])},${r1(pts[0][1])}`;
    for (let i = 1; i < pts.length - 1; i++) {
      const [a, b, c] = [pts[i - 1], pts[i], pts[i + 1]];
      const l1 = Math.hypot(b[0] - a[0], b[1] - a[1]), l2 = Math.hypot(c[0] - b[0], c[1] - b[1]);
      const r = Math.min(rad, l1 / 2, l2 / 2);
      if (r < 0.5) { d += `L${r1(b[0])},${r1(b[1])}`; continue; }
      const p1 = [b[0] + (a[0] - b[0]) * r / l1, b[1] + (a[1] - b[1]) * r / l1];
      const p2 = [b[0] + (c[0] - b[0]) * r / l2, b[1] + (c[1] - b[1]) * r / l2];
      d += `L${r1(p1[0])},${r1(p1[1])}Q${r1(b[0])},${r1(b[1])} ${r1(p2[0])},${r1(p2[1])}`;
    }
    const z = pts[pts.length - 1];
    return d + `L${r1(z[0])},${r1(z[1])}`;
  }
  const path = (d, cls) => `<path class="${cls}" d="${d}"/>`;
  // a setting that is enabled gets its badge; a disabled one leaves its slot empty
  function badge(kind, on, x, y) {
    if (!on) return '';
    const what = kind === 'pol' ? 'Policy Inheritance' : 'Detection Aggregation';
    return `<g class="badge ${kind}"><title>${what} enabled</title>` +
      `<rect x="${r1(x)}" y="${r1(y - L.badgeH / 2)}" width="${L.badgeW}" height="${L.badgeH}" rx="4"/>` +
      `<text x="${r1(x + L.badgeW / 2)}" y="${r1(y)}" dy="0.35em">${kind === 'pol' ? 'P' : 'D'}</text></g>`;
  }
  const badges = (c, x, y) => (state.show.pol ? badge('pol', c.pol, x, y) : '') +
                              (state.show.det ? badge('det', c.det, x + L.badgeW + L.badgeSpace, y) : '');
  function chip(x, y, text) {
    const w = textW(text, CHIP_FONT) + 14;
    return `<g class="chip"><rect x="${r1(x)}" y="${r1(y - 8)}" width="${r1(w)}" height="16" rx="8"/>` +
      `<text x="${r1(x + 7)}" y="${r1(y)}" dy="0.35em">${esc(text)}</text></g>`;
  }

  function renderGraph(v, vis) {
    lay = layout(v, vis);
    const P = lay.pos, R = L.dotR;
    const match = matchSet(v);
    const chain = state.selected && vis.has(state.selected) ? chainOf(v, state.selected) : null;
    const lit = chain || match;
    const dim = (...ids) => lit && !ids.every(id => lit.has(id)) ? ' dim' : '';
    const inChain = (a, b) => chain && chain.has(a) && chain.has(b);
    const cards = [], base = [], pol = [], halo = [], dash = [], hi = [], nodes = [];

    // root -> service lines: down to the bus, across, down into each card
    for (const root of lay.roots) {
      const rp = P[root.id];
      for (const col of lay.cols) {
        const line = col.line;
        if (line.parent !== root.id) continue;
        const d = route([[rp.x, rp.y + RS + 3], [rp.x, L.busY], [col.trunk, L.busY], [col.trunk, col.iconY - IR - 3]], 10);
        const purple = line.pol && state.show.pol;
        base.push(path(d, 'link' + dim(root.id, line.id)));
        if (purple) pol.push(path(`M${r1(col.trunk)},${L.busY + 10}V${r1(col.iconY - IR - 3)}`, 'link pol' + dim(root.id, line.id)));
        if (inChain(root.id, line.id)) hi.push(path(d, 'link-hi' + (purple ? ' pol' : '')));
      }
    }

    // cards, and the links inside them: the line's trunk to each tenant
    for (const col of lay.cols) {
      cards.push(`<g class="card-g${lineOn(col.line.id) ? '' : ' ctx'}"><rect class="card" x="${r1(col.x)}" y="${col.top}" ` +
        `width="${r1(col.w)}" height="${col.h}" rx="10"/>` +
        (col.rows.length ? `<path class="card-div" d="M${r1(col.x)},${col.top + L.headH}h${r1(col.w)}"/>` : '') + '</g>');
      for (const c of col.rows) {
        const p = P[c.id];
        const from = c.depth === 2 ? [col.trunk, col.iconY + IR + 3] : [P[c.parent].x, P[c.parent].y + R + 3];
        const d = route([from, [from[0], p.y], [p.x - R - 3, p.y]], 8);
        const purple = c.pol && state.show.pol;
        base.push(path(d, 'link' + dim(c.parent, c.id)));
        if (purple) pol.push(path(`M${r1(from[0] + 8)},${r1(p.y)}H${r1(p.x - R - 3)}`, 'link pol' + dim(c.parent, c.id)));
        if (inChain(c.parent, c.id)) hi.push(path(d, 'link-hi' + (purple ? ' pol' : '')));
      }
    }

    // additional parents: dashed, from a port on top of the parent's card,
    // along a channel under the bus, down the gutter left of the tenant's
    // card, into the tenant's row
    if (state.show.addl) {
      const groups = new Map(), sources = [];
      for (const col of lay.cols) {
        for (const c of col.rows) {
          if (!c.addl || !P[c.addl]) continue;
          const key = c.addl + '>' + col.index;
          if (!groups.has(key)) groups.set(key, {src: v.byId[c.addl], col, rows: []});
          groups.get(key).rows.push(c);
          if (!sources.includes(c.addl)) sources.push(c.addl);
        }
      }
      const gutters = {}, ports = {};
      for (const {src, col, rows} of groups.values()) {
        const k = gutters[col.index] = (gutters[col.index] || 0) + 1;
        const j = ports[src.id] = (ports[src.id] || 0) + 1;
        const gx = col.x - 8 - (k - 1) * 6;
        const srcCol = src.depth === 1 ? lay.cols[lay.colOf[src.id]] : null;
        const px = srcCol ? srcCol.trunk + 22 + (j - 1) * 7 : 0;
        const cy = L.busY + 8 + Math.min(2, sources.indexOf(src.id)) * 5;
        for (const c of rows) {
          const p = P[c.id], end = [col.x + 3, p.y], cls = dim(src.id, c.id);
          let d;
          if (srcCol && srcCol !== col) {
            d = route([[px, srcCol.top], [px, cy], [gx, cy], [gx, p.y], end], 6);
          } else {
            const s = P[src.id];
            d = `M${r1(s.x)},${r1(s.y)}C${r1(s.x - 60)},${r1(s.y)} ${r1(end[0] - 60)},${r1(end[1])} ${r1(end[0])},${r1(end[1])}`;
          }
          halo.push(path(d, 'halo'));
          dash.push(path(d, 'link addl' + cls) + `<circle class="port${cls}" cx="${r1(end[0])}" cy="${r1(end[1])}" r="2.6"/>`);
          if (srcCol && srcCol !== col) dash.push(`<circle class="port${cls}" cx="${r1(px)}" cy="${srcCol.top}" r="2.6"/>`);
          if (inChain(src.id, c.id)) hi.push(path(d, 'link-hi addl'));
        }
      }
    }

    // the root: glyph, name, child count and badges
    for (const root of lay.roots) {
      const p = P[root.id], lx = p.x + RS + 12, tw = rootLabelW(v, root);
      nodes.push(`<g class="node${state.selected === root.id ? ' sel' : ''}${dim(root.id)}" data-id="${esc(root.id)}">` +
        `<rect class="node-bg" x="${r1(p.x - RS - 8)}" y="${r1(p.y - RS - 7)}" width="${r1(2 * RS + 30 + tw + 2 * L.badgeW + L.badgeSpace)}" ` +
        `height="${r1(2 * RS + 14)}" rx="8"/>` + glyph(p.x, p.y, L.rootScale) +
        `<text class="t-head" x="${r1(lx)}" y="${r1(p.y - 3)}">${esc(short(root.name))}</text>` +
        `<text class="t-sub" x="${r1(lx)}" y="${r1(p.y + 13)}">${esc(rootSub(v, root))}</text>` +
        badges(root, lx + tw + 14, p.y) + '</g>');
    }

    // each card: the service line in its header, then one row per tenant
    for (const col of lay.cols) {
      const line = col.line, hx = col.trunk + IR + 12;
      nodes.push(`<g class="node${state.selected === line.id ? ' sel' : ''}${lineOn(line.id) ? '' : ' ctx'}${dim(line.id)}" data-id="${esc(line.id)}">` +
        `<rect class="node-bg" x="${r1(col.x + 4)}" y="${col.top + 4}" width="${r1(col.w - 8)}" height="${L.headH - 8}" rx="7"/>` +
        glyph(col.trunk, col.iconY, 1) +
        `<text class="t-head" x="${r1(hx)}" y="${r1(col.iconY - 3)}">${esc(short(line.name))}</text>` +
        `<text class="t-sub" x="${r1(hx)}" y="${r1(col.iconY + 13)}">${esc(lineSub(v, line))}</text>` +
        badges(line, badgeX(col), col.iconY) + '</g>');
      for (const c of col.rows) {
        const p = P[c.id], [pre, rest] = splitName(c.name), nx = p.x + R + L.nameGap;
        const cls = 'row' + (inactive(c) ? ' inactive' : '') + (state.selected === c.id ? ' sel' : '') +
                    (match && match.has(c.id) ? ' match' : '') + dim(c.id);
        let g = `<g class="${cls}" data-id="${esc(c.id)}">` +
          `<rect class="node-bg" x="${r1(col.x + 4)}" y="${r1(p.y - L.rowH / 2 + 1)}" width="${r1(col.w - 8)}" height="${L.rowH - 2}" rx="6"/>` +
          `<circle class="dot" cx="${r1(p.x)}" cy="${r1(p.y)}" r="${R}"/>` +
          `<text class="t-name" x="${r1(nx)}" y="${r1(p.y)}" dy="0.35em">${pre ? `<tspan class="t-pre">${esc(pre)}</tspan>` : ''}${esc(rest)}</text>`;
        if (c.addl && state.show.addl) g += chip(nx + textW(c.name, NAME_FONT) + L.chipGap, p.y, chipText(v, c));
        nodes.push(g + badges(c, badgeX(col), p.y) + '</g>');
      }
    }

    port.innerHTML = cards.join('') + base.join('') + pol.join('') + halo.join('') + dash.join('') + hi.join('') + nodes.join('');
    $('empty').hidden = lay.cols.length + lay.roots.length > 0;
    if (needFit) { needFit = false; fit(false); }
  }

  // ---------- pan and zoom
  const apply = () => port.setAttribute('transform', `translate(${T.x},${T.y}) scale(${T.k})`);
  function moveTo(to, animate) {
    cancelAnimationFrame(anim);
    if (!animate) { T = to; apply(); return; }
    const from = {...T}, t0 = performance.now();
    const step = now => {
      const t = Math.min(1, (now - t0) / 260), q = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2;
      T = {x: from.x + (to.x - from.x) * q, y: from.y + (to.y - from.y) * q, k: from.k + (to.k - from.k) * q};
      apply();
      if (t < 1) anim = requestAnimationFrame(step);
    };
    anim = requestAnimationFrame(step);
  }
  function zoomAt(mx, my, f) {
    const k = Math.max(L.minScale, Math.min(L.maxScale, T.k * f));
    cancelAnimationFrame(anim);
    T = {x: mx - (mx - T.x) * k / T.k, y: my - (my - T.y) * k / T.k, k};
    apply();
  }
  // the part of the canvas not covered by the toolbar, the legend or the drawer
  function freeArea() {
    const r = svg.getBoundingClientRect(), ov = $('overlay-left').getBoundingClientRect();
    return {w: r.width, h: r.height, left: Math.max(20, ov.right - r.left + 24), top: 24, bottom: 36,
            right: 24 + (drawer.classList.contains('open') ? drawer.offsetWidth : 0)};
  }
  function fit(animate) {
    if (!lay || state.tab !== 'graph') return;
    const a = freeArea(), b = lay.box, bw = b.x2 - b.x1, bh = b.y2 - b.y1;
    if (!a.w || !a.h || bw <= 0) return;
    const aw = Math.max(120, a.w - a.left - a.right), ah = Math.max(120, a.h - a.top - a.bottom);
    const k = Math.max(L.minScale, Math.min(L.maxFit, aw / bw, ah / bh));
    moveTo({x: a.left + (aw - bw * k) / 2 - b.x1 * k, y: a.top + Math.max(0, (ah - bh * k) * 0.3) - b.y1 * k, k}, animate);
  }
  // a CID's row (or header) runs from a little left of its dot to its card's right edge
  function centerOn(id) {
    const p = lay && lay.pos[id];
    if (!p) return;
    const a = freeArea(), k = Math.max(T.k, 0.85), mid = (p.x - 20 + lay.ext[id]) / 2;
    const cx = a.left + (a.w - a.left - a.right) / 2, cy = a.top + (a.h - a.top - a.bottom) / 2;
    moveTo({x: cx - mid * k, y: cy - p.y * k, k}, true);
  }
  // after a click: moves the view only as far as needed for the drawer not to cover the CID's row
  function keepClear(id) {
    const p = lay && lay.pos[id];
    if (!p) return;
    const a = freeArea(), x1 = T.x + (p.x - 20) * T.k, x2 = T.x + lay.ext[id] * T.k, y = T.y + p.y * T.k;
    const dx = Math.min(0, a.w - a.right - x2);
    if (x1 + dx < a.left || y < a.top || y > a.h - a.bottom) centerOn(id);
    else if (dx) moveTo({x: T.x + dx, y: T.y, k: T.k}, true);
  }

  svg.addEventListener('wheel', ev => {
    ev.preventDefault();
    const r = svg.getBoundingClientRect(), dy = ev.deltaMode === 1 ? ev.deltaY * 16 : ev.deltaY;
    zoomAt(ev.clientX - r.left, ev.clientY - r.top, Math.exp(-dy * 0.0015));
  }, {passive: false});
  let drag = null;
  svg.addEventListener('pointerdown', ev => {
    if (ev.button === 0) drag = {x: ev.clientX, y: ev.clientY, tx: T.x, ty: T.y, moved: false};
  });
  window.addEventListener('pointermove', ev => {
    if (!drag) return;
    const dx = ev.clientX - drag.x, dy = ev.clientY - drag.y;
    if (!drag.moved && Math.abs(dx) + Math.abs(dy) > 4) { drag.moved = true; svg.classList.add('panning'); }
    if (drag.moved) { cancelAnimationFrame(anim); T = {x: drag.tx + dx, y: drag.ty + dy, k: T.k}; apply(); }
  });
  window.addEventListener('pointerup', ev => {
    if (!drag) return;
    const moved = drag.moved;
    drag = null;
    svg.classList.remove('panning');
    if (moved || !svg.contains(ev.target)) return;
    const hit = ev.target.closest('[data-id]');
    if (hit) select(hit.getAttribute('data-id'), false); else clearSelection();
  });

  // ---------- legend
  function renderLegend(v, vis) {
    const n = {all: 0, parents: 0, tenants: 0, off: 0, pol: 0, det: 0, addl: 0, links: 0};
    for (const c of v.cids) {
      if (!vis.has(c.id)) continue;
      n.all++;
      if (c.depth < 2) n.parents++; else n.tenants++;
      if (inactive(c)) n.off++;
      if (c.pol) n.pol++;
      if (c.det) n.det++;
      if (c.addl && vis.has(c.addl)) n.addl++;
      if (c.parent && vis.has(c.parent)) n.links++;
    }
    const row = (ico, text, count, end = '', cls = '') => `<div class="lg-row${cls}"><span class="lg-ico">${ico}</span>` +
      `<span class="lg-label">${text}</span><span class="lg-n">${count}</span>${end || '<span></span>'}</div>`;
    const eye = (act, on, what, id = '') => `<button type="button" class="lg-btn" data-act="${act}"${id ? ` data-id="${esc(id)}"` : ''} ` +
      `aria-pressed="${on}" title="${on ? 'Hide' : 'Show'} ${esc(what)}">${on ? EYE : EYE_OFF}</button>`;
    const lines = linesOf(v).map(id => {
      const on = lineOn(id), count = v.cids.filter(c => c.depth >= 2 && c.line === id).length;
      return `<div class="lg-row${on ? '' : ' off'}${state.solo === id ? ' solo' : ''}"><span class="lg-ico">${glyphIcon(14)}</span>` +
        `<button type="button" class="lg-solo" data-act="solo" data-id="${esc(id)}" title="Show only this service line">${esc(lineTag(v, id))}</button>` +
        `<span class="lg-n">${count}</span>${eye('line', on, lineTag(v, id), id)}</div>`;
    }).join('');
    const reset = state.solo || state.hidden.size ? '<button type="button" class="lg-reset" data-act="all">Show all service lines</button>' : '';
    $('legend').innerHTML =
      `<div class="lg-title"><span>Legend</span><button type="button" class="lg-btn" data-act="legend" title="Hide legend">${PANEL}</button></div>` +
      row(STACK, 'All CIDs', n.all) +
      row(glyphIcon(20), 'Parent CIDs', n.parents, `<button type="button" class="lg-btn${state.linesOpen ? ' open' : ''}" data-act="lines" ` +
          `aria-expanded="${state.linesOpen}" title="Service lines">${CHEVRON}</button>`) +
      (state.linesOpen ? `<div class="lg-sub">${lines}${reset}</div>` : '') +
      row('<span class="ico-dot"></span>', 'Tenant CIDs', n.tenants) +
      (n.off ? row('<span class="ico-dot off"></span>', 'Inactive CIDs', n.off) : '') +
      '<div class="lg-section">Links and settings</div>' +
      row(LG_LINK, 'Parent link', n.links) +
      row(lgBadge('pol', 'P'), 'Policy Inheritance enabled', n.pol, eye('pol', state.show.pol, 'Policy Inheritance'), state.show.pol ? '' : ' off') +
      row(lgBadge('det', 'D'), 'Detection Aggregation enabled', n.det, eye('det', state.show.det, 'Detection Aggregation'), state.show.det ? '' : ' off') +
      row(LG_ADDL, 'Additional parent', n.addl, eye('addl', state.show.addl, 'additional parents'), state.show.addl ? '' : ' off');
    $('legend').hidden = !state.legend;
    $('tb-legend').setAttribute('aria-pressed', String(state.legend));
  }

  // ---------- table
  const COLS = [
    {key: 'name', label: 'CID name', get: c => c.name.toLowerCase()},
    {key: 'type', label: 'Type', get: c => Math.min(c.depth, 2)},
    {key: 'line', label: 'Service line', get: (c, v) => c.depth ? lineTag(v, c.line).toLowerCase() : ''},
    {key: 'addl', label: 'Additional parent', get: (c, v) => c.addl ? label(v, c.addl).toLowerCase() : '~'},
    {key: 'status', label: 'Status', get: c => c.new ? 'new' : c.status},
    {key: 'endpoints', label: 'Endpoints', num: true, get: c => c.new ? -1 : Number(c.endpoints) || 0},
    {key: 'pol', label: 'Policy Inheritance', get: c => c.pol ? 0 : 1},
    {key: 'det', label: 'Detection Aggregation', get: c => c.det ? 0 : 1},
    {key: 'kids', label: 'Child CIDs', num: true, get: (c, v) => kidsOf(v, c.id).length},
    {key: 'id', label: 'CID String', get: c => c.id}];

  function renderTable(v, vis) {
    const match = matchSet(v), s = state.sort, col = COLS.find(k => k.key === s.key);
    let rows = v.cids.filter(c => vis.has(c.id) && (!match || match.has(c.id)));
    if (col) {
      rows = rows.slice().sort((a, b) => {
        const x = col.get(a, v), y = col.get(b, v);
        return (x < y ? -1 : x > y ? 1 : 0) * s.dir || a.row - b.row;
      });
    }
    const dash = '<span class="muted">—</span>';
    const head = COLS.map(k => {
      const on = s.key === k.key;
      return `<th class="${k.num ? 'num' : ''}" data-sort="${k.key}" aria-sort="${on ? (s.dir > 0 ? 'ascending' : 'descending') : 'none'}">` +
        `<button type="button">${k.label}<span>${on ? (s.dir > 0 ? '↑' : '↓') : ''}</span></button></th>`;
    }).join('');
    const body = rows.map(c => {
      const [pre, rest] = splitName(c.name);
      const ico = c.depth < 2 ? glyphIcon(16) : `<span class="t-dot${inactive(c) ? ' off' : ''}"></span>`;
      return `<tr data-id="${esc(c.id)}" class="${state.selected === c.id ? 'sel' : ''}">` +
        `<td style="padding-left: ${12 + (col ? 0 : Math.min(c.depth, 4) * 20)}px"><span class="nm">${ico}<span>` +
        `${pre ? `<span class="muted">${esc(pre)}</span>` : ''}${esc(rest)}</span></span></td>` +
        `<td>${['Root CID', 'Service line', 'Tenant'][Math.min(c.depth, 2)]}</td>` +
        `<td>${c.depth ? esc(lineTag(v, c.line)) : dash}</td>` +
        `<td>${c.addl ? esc(label(v, c.addl)) : dash}</td>` +
        `<td>${statusPill(c)}</td>` +
        `<td class="num">${c.new ? dash : fmt(c.endpoints)}</td>` +
        `<td>${onOff(c.pol, 'pol')}</td><td>${onOff(c.det, 'det')}</td>` +
        `<td class="num">${kidsOf(v, c.id).length}</td>` +
        `<td><span class="c-cid"><code>${esc(c.id)}</code>` +
        `${c.new ? '' : `<button type="button" class="copy" data-copy="${esc(c.id)}" title="Copy CID String">${COPY}</button>`}</span></td></tr>`;
    }).join('');
    $('cid-table').innerHTML = `<thead><tr>${head}</tr></thead><tbody>` +
      (body || `<tr><td colspan="${COLS.length}" class="muted empty-row">No CIDs match the search or the filter.</td></tr>`) + '</tbody>';
    $('table-bar').innerHTML = linesOf(v).map(id => `<button type="button" class="chip-btn" data-act="line" data-id="${esc(id)}" ` +
      `aria-pressed="${lineOn(id)}">${glyphIcon(14)}${esc(lineTag(v, id))}</button>`).join('') +
      (state.solo || state.hidden.size ? '<button type="button" class="link-btn" data-act="all">Show all</button>' : '') +
      `<span class="bar-n"><b>${rows.length}</b> of ${v.cids.length} CIDs</span>`;
  }

  // ---------- details drawer
  function goRow(v, id, tag) {
    const c = v.byId[id];
    const ico = c.depth < 2 ? glyphIcon(14) : `<span class="mini-dot${inactive(c) ? ' off' : ''}"></span>`;
    return `<button type="button" class="dw-go" data-goto="${esc(id)}">${ico}<span>${esc(c.name)}</span>` +
      (tag ? `<span class="tag">${tag}</span>` : '') + '</button>';
  }
  function drawerHTML(v, c) {
    const kind = c.depth === 0 ? 'Root CID' : c.depth === 1 ? 'Service line' : 'Tenant · ' + lineTag(v, c.line);
    const ico = c.depth < 2 ? glyphIcon(26) : '<svg width="26" height="26" viewBox="-13 -13 26 26" aria-hidden="true"><circle class="dot" r="7"/></svg>';
    const parents = [[c.parent, 'Primary'], [c.addl, 'Additional']].filter(([p]) => p && v.byId[p])
      .map(([p, tag]) => goRow(v, p, tag)).join('') || '<div class="dw-none">None, this is the root</div>';
    const kids = kidsOf(v, c.id).map(id => v.byId[id]).sort((a, b) => a.row - b.row)
      .map(k => goRow(v, k.id, k.addl === c.id ? 'Additional' : '')).join('');
    const set = (name, on, cls) => `<div class="dw-set"><span>${name}</span>${onOff(on, cls)}</div>`;
    return `<div class="dw-head">${ico}<div class="dw-title"><div class="dw-name">${esc(c.name)}</div>` +
      `<div class="dw-kind">${esc(kind)}</div></div><button type="button" class="icon-btn" data-act="close" aria-label="Close details">${CLOSE}</button></div>` +
      `<div class="dw-sec"><div class="dw-label">CID String</div><div class="dw-cid"><code>${esc(c.id)}</code>` +
      `${c.new ? '<span class="pill new">To be created</span>' : `<button type="button" class="btn-sm" data-copy="${esc(c.id)}">Copy</button>`}</div></div>` +
      `<div class="dw-stats"><div><div class="dw-label">Status</div>${statusPill(c)}</div>` +
      `<div><div class="dw-label">Endpoints</div><div class="dw-num">${c.new ? '—' : fmt(c.endpoints)}</div></div>` +
      `<div><div class="dw-label">Child CIDs</div><div class="dw-num">${kidsOf(v, c.id).length}</div></div></div>` +
      `<div class="dw-sec"><div class="dw-label">Parents</div>${parents}</div>` +
      `<div class="dw-sec"><div class="dw-label">Settings</div>${set('Policy Inheritance', c.pol, 'pol')}` +
      `${set('Detection Aggregation', c.det, 'det')}${set('Incident Aggregation', c.inc, 'det')}</div>` +
      (kids ? `<div class="dw-sec"><div class="dw-label">Child CIDs</div>${kids}</div>` : '');
  }
  function renderDrawer(v) {
    const c = state.selected && v.byId[state.selected];
    if (!c) state.selected = '';
    else drawer.innerHTML = drawerHTML(v, c);
    drawer.classList.toggle('open', !!c);
    drawer.setAttribute('aria-hidden', String(!c));
    document.body.classList.toggle('has-drawer', !!c);
  }

  // ---------- state changes
  function render() {
    const v = VIEWS[state.view], vis = visibleSet(v);
    document.querySelectorAll('#view-seg button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.view === state.view)));
    renderDrawer(v);
    renderLegend(v, vis);
    if (state.tab === 'graph') renderGraph(v, vis); else renderTable(v, vis);
  }
  function select(id, center) {
    const v = VIEWS[state.view];
    if (!v.byId[id]) return;
    if (!visibleSet(v).has(id)) { state.solo = ''; state.hidden.clear(); needFit = true; }
    state.selected = id;
    render();
    if (state.tab === 'graph') { if (center) centerOn(id); else keepClear(id); }
    else { const tr = $('cid-table').querySelector(`tr[data-id="${id}"]`); if (tr) tr.scrollIntoView({block: 'nearest'}); }
  }
  function clearSelection() { if (state.selected) { state.selected = ''; render(); } }
  function act(name, id) {
    if (name === 'line') {
      if (state.solo) { state.hidden = new Set(DATA.lineOrder.filter(x => x !== state.solo)); state.solo = ''; }
      if (state.hidden.has(id)) state.hidden.delete(id); else state.hidden.add(id);
      needFit = true;
    } else if (name === 'solo') { state.solo = state.solo === id ? '' : id; needFit = true; }
    else if (name === 'all') { state.solo = ''; state.hidden.clear(); needFit = true; }
    else if (name === 'lines') state.linesOpen = !state.linesOpen;
    else if (name === 'legend') { state.legend = !state.legend; }
    else if (name in state.show) { state.show[name] = !state.show[name]; needFit = needFit || name === 'addl'; }
    render();
    if (name === 'legend') fit(true);
  }
  function setView(view) { state.view = view; needFit = true; render(); }
  function setTab(tab) {
    state.tab = tab;
    document.querySelectorAll('.tab').forEach(b => b.setAttribute('aria-selected', String(b.dataset.tab === tab)));
    $('graph-pane').hidden = tab !== 'graph';
    $('table-pane').hidden = tab !== 'table';
    render();
  }
  function sortBy(key) {
    const s = state.sort;
    state.sort = s.key !== key ? {key, dir: 1} : s.dir > 0 ? {key, dir: -1} : {key: '', dir: 1};
    render();
  }
  // Copy button: falls back to a hidden textarea where the clipboard API is
  // not available (a page opened from disk is not always a secure context)
  function copyText(text, button) {
    const done = () => {
      if (button.textContent === 'Copy') { button.textContent = 'Copied'; setTimeout(() => { button.textContent = 'Copy'; }, 1200); }
      else { button.classList.add('done'); setTimeout(() => button.classList.remove('done'), 1200); }
    };
    if (navigator.clipboard && window.isSecureContext) { navigator.clipboard.writeText(text).then(done, () => {}); return; }
    const area = document.createElement('textarea');
    area.value = text;
    document.body.appendChild(area);
    area.select();
    try { document.execCommand('copy'); done(); } catch (err) {}
    document.body.removeChild(area);
  }

  // ---------- events
  document.addEventListener('click', ev => {
    const t = ev.target;
    if (!(t instanceof Element) || svg.contains(t)) return;
    const copy = t.closest('[data-copy]');
    if (copy) { ev.stopPropagation(); copyText(copy.dataset.copy, copy); return; }
    const go = t.closest('[data-goto]');
    if (go) { select(go.dataset.goto, true); return; }
    if (t.closest('[data-act="close"]')) { clearSelection(); return; }
    const a = t.closest('[data-act]');
    if (a) { act(a.dataset.act, a.dataset.id); return; }
    const th = t.closest('th[data-sort]');
    if (th) { sortBy(th.dataset.sort); return; }
    const tr = t.closest('#cid-table tbody tr[data-id]');
    if (tr) select(tr.dataset.id, false);
  });
  document.querySelectorAll('#view-seg button').forEach(b => b.addEventListener('click', () => setView(b.dataset.view)));
  document.querySelectorAll('.tab').forEach(b => b.addEventListener('click', () => setTab(b.dataset.tab)));
  $('tb-legend').addEventListener('click', () => act('legend'));
  $('tb-fit').addEventListener('click', () => fit(true));
  $('tb-in').addEventListener('click', () => { const a = freeArea(); zoomAt(a.w / 2, a.h / 2, 1.25); });
  $('tb-out').addEventListener('click', () => { const a = freeArea(); zoomAt(a.w / 2, a.h / 2, 0.8); });
  const search = $('search');
  search.addEventListener('input', () => { state.query = search.value; render(); });
  search.addEventListener('keydown', ev => {
    if (ev.key !== 'Enter') return;
    const v = VIEWS[state.view], m = matchSet(v), vis = visibleSet(v);
    const first = m && v.cids.find(c => m.has(c.id) && vis.has(c.id));
    if (first) select(first.id, true);
  });
  document.addEventListener('keydown', ev => {
    const typing = ev.target instanceof Element && ev.target.matches('input, textarea');
    if (ev.key === '/' && !typing) { ev.preventDefault(); search.focus(); search.select(); return; }
    if (ev.key !== 'Escape') return;
    if (typing && search.value) { search.value = ''; state.query = ''; render(); }
    else if (state.selected) clearSelection();
    else if (typing) ev.target.blur();
  });
  // theme: dark by default, as in the Falcon console; the choice is kept by the browser
  const root = document.documentElement;
  try { if (localStorage.getItem('fc-theme') === 'light') root.setAttribute('data-theme', 'light'); } catch (err) {}
  $('theme-btn').addEventListener('click', () => {
    const next = root.getAttribute('data-theme') === 'light' ? 'dark' : 'light';
    root.setAttribute('data-theme', next);
    try { localStorage.setItem('fc-theme', next); } catch (err) {}
  });
  window.addEventListener('resize', () => fit(false));

  $('stamp').innerHTML = `CID export <b>${esc(DATA.exported)}</b> &#183; Generated <b>${esc(DATA.generated)}</b>`;
  render();
})();
"""



#################################### Part 8: HTML Generation ->

def build_page(today, t_info, expected, x_info):
  """The whole HTML page: the Expected view (when there is one) and the
  Today view, as data for the page script."""
  exported = datetime.fromtimestamp(os.path.getmtime(INPUT))
  t_roots = t_info[2]
  company = today[t_roots[0]]["name"].split("|")[0].split(" - ", 1)[-1].strip() if t_roots else ""
  views = ([("expected", expected, x_info)] if expected is not None else []) + [("today", today, t_info)]

  # the service lines in name order, the same in both views
  line_order = []
  for _, _, (order, _, _) in views:
    for c, d in order:
      if d == 1 and c not in line_order: line_order.append(c)

  stamp = "%b %d, %Y · %H:%M"
  data = {"order": [k for k, _, _ in views], "views": {k: view_data(recs, info) for k, recs, info in views},
          "lineOrder": line_order, "exported": exported.strftime(stamp), "generated": datetime.now().strftime(stamp)}
  view_buttons = "".join(
    f'<button type="button" data-view="{k}" title="{e(VIEW_STYLE[k][1])}" style="--vc: {VIEW_STYLE[k][2]}">'
    f'<span class="sw"></span>{e(VIEW_STYLE[k][0])}</button>' for k, _, _ in views)
  css = (PAGE_CSS.replace("%%DARK%%", css_vars(THEMES["dark"])).replace("%%LIGHT%%", css_vars(THEMES["light"]))
         .replace("%%FONT%%", LAYOUT["font"]))
  script = f"var DATA = {js(data)};\nvar LAYOUT = {js(LAYOUT)};\n{PAGE_SCRIPT}"
  # the script goes in last, so no text from the data is ever read as a marker
  return (PAGE.replace("%%TAB_TITLE%%", e(f"{TAB_TITLE} - {company}" if company else TAB_TITLE))
          .replace("%%FAVICON%%", FAVICON)
          .replace("%%CSS%%", css)
          .replace("%%GLYPH%%", GLYPH)
          .replace("%%APP%%", e(APP_NAME)).replace("%%PAGE%%", e(PAGE_NAME)).replace("%%COMPANY%%", e(company))
          .replace("%%VIEW_BUTTONS%%", view_buttons)
          .replace("%%SCRIPT%%", script))


if __name__ == "__main__":
  os.chdir(ROOT)
  today, t_info = load_today()
  if "--keep-expected" in sys.argv: keep_expected()
  if "--init-expected" in sys.argv: init_expected(today, t_info[0])
  expected, x_info = load_expected(today)
  if expected is None and previous_expected():
    print(f"NOTE: no {EXPECTED} yet; the most recent is {previous_expected()} "
          f"(--keep-expected carries it over)")

  page = build_page(today, t_info, expected, x_info)
  message = summary = None
  if expected is not None:
    # every CID of the expected structure, then the ones it deletes
    order = [c for c, _ in x_info[0]] + [c for c, _ in t_info[0] if c not in expected]
    D = {c: diff(c, today, expected) for c in order}
    summary = pending_summary(D)
    message = case_message(order, D, today, expected, x_info)

  os.makedirs(os.path.dirname(HTML_OUT), exist_ok=True)
  with open(HTML_OUT, "w", encoding="utf-8", newline="\n") as f: f.write(page)
  print(f"OK: {len(today)} CIDs in export -> {HTML_OUT}")
  if expected is not None:
    print(f"OK: {len(expected)} CIDs expected; {summary}")
    if message:
      with open(CASE_OUT, "w", encoding="utf-8", newline="\n") as f: f.write(message)
      print(f"OK: steps written to {CASE_OUT}")
    elif os.path.exists(CASE_OUT):
      os.remove(CASE_OUT)
      print(f"OK: nothing pending; removed stale {CASE_OUT}")
  for w in warnings: print("WARNING: " + w)
