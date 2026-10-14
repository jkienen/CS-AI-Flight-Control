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

# Repo root (this file lives in Output/Scripts/): Input/ and Output/ are found
# from here, so the script runs from any folder. The paths below are relative to it.
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
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

# Shown over the canvas, and in the browser tab. The tab icon is a data URI,
# fully local (no external file/network fetch).
TITLE = "FALCON FLIGHT CONTROL · CID HIERARCHY"
TAB_TITLE = "Falcon Flight Control - CID Hierarchy"
FAVICON = ("data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'>"
           "<text x='50' y='75' font-size='80' text-anchor='middle'>&#x1F6E1;</text></svg>")

# The root is drawn in ROOT_COLOR; each service line (a direct child of the
# root) and every CID under it take one LINE_COLORS entry, in name order:
# the first line blue, the second orange, the third yellow, the fourth red.
ROOT_COLOR = "#e0e0e0"
LINE_COLORS = ["#4fc3f7", "#ff9800", "#ffd54f", "#ef5350", "#ff7f50", "#f06292", "#90a4ae"]

# Links between a CID and each of its parents (dashed for the additional
# parent): parent -> child in POLICY_COLOR when the child has Policy
# Inheritance enabled, LINK_COLOR otherwise; plus child -> parent in
# DETECTION_COLOR when it has Detection Aggregation enabled. Both curve by
# LINK_CURVE, to opposite sides, so a pair never overlaps.
LINK_COLOR = "#555555"
POLICY_COLOR = "#b388ff"
DETECTION_COLOR = "#69f0ae"
LINK_CURVE = 0.12

# Line widths: the Detection Aggregation links are thinner, so they stay in
# the background; clicking a CID draws each link of its chain HIGHLIGHT_WIDTH
# wider than its own width (selected and hovered links get nothing extra).
LINK_WIDTH = 1
DETECTION_WIDTH = 0.6
HIGHLIGHT_WIDTH = 0.6

# Every link is drawn at LINK_OPACITY, darker against the black canvas;
# clicking a CID draws its chain at full color.
LINK_OPACITY = 0.5

# Layout: a tree, left to right - root, service lines, tenants. Each service
# line gets a horizontal band, in name order top to bottom (01 on top); its
# tenants are stacked one below the other, ROW_HEIGHT apart, each name
# LABEL_GAP px to the right of its dot; tenants with an additional parent
# come first, so their dashed links stay short. A line sits at the middle of
# its band, the root at the middle of the lines. Root and line names sit
# below their dots. NODE_SIZE is the dot radius of the root and the lines,
# TENANT_SIZE of the tenants; COLUMN_GAP is the space between two columns,
# BAND_GAP the space between the last tenant of a band and the first of the
# next.
NODE_SIZE = 16
TENANT_SIZE = 10
ROW_HEIGHT = 28
LABEL_GAP = 8
COLUMN_GAP = 80
BAND_GAP = 70

# The two views, as (button label, hint, color): the selected view's button
# is filled with its color.
VIEW_STYLE = {"expected": ("Expected", "after the changes", "#7c4dff"),
              "today": ("Today", "current export", "#546e7a")}

# CIDs that are not active are drawn faded, dot and label.
INACTIVE_OPACITY = 0.40

# Clicking a CID lights it up with its whole chain (parents up to the root,
# children down), border and glow in HIGHLIGHT_COLOR; the links of the chain
# keep their colors, thicker, and every other link fades.
HIGHLIGHT_COLOR = "#ffffff"
HIGHLIGHT_CHAIN = True

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



#################################### Part 5: Graph Construction ->

e = html.escape

def short(name):
  """Text after the last '|': '01 - Example Corp | Managed' -> 'Managed'."""
  return name.rsplit("|", 1)[-1].strip()

def line_text(name):
  """Service line as listed in the filter: '01 - Example Corp | Managed' -> '01 - Managed'."""
  prefix = name.split(" - ", 1)[0] if " - " in name else ""
  return f"{prefix} - {short(name)}" if prefix else short(name)

def rgba(color, alpha):
  """'#69f0ae', 0.5 -> 'rgba(105, 240, 174, 0.5)'."""
  return f"rgba({int(color[1:3], 16)}, {int(color[3:5], 16)}, {int(color[5:7], 16)}, {alpha})"

def graph_view(view, recs, info, color_of):
  """Nodes and edges of one view (expected or today). Node ids are
  '<view>/<cid>', so both views live in the same graph; the side panel shows
  one at a time. Each node carries the HTML of its detail card."""
  order, kids, roots = info
  depth = dict(order)
  root_set = set(roots)

  def line_of(c):
    while recs[c]["parent"] in recs and recs[c]["parent"] not in root_set:
      c = recs[c]["parent"]
    return c

  def child_count(c):
    return len(kids.get(c, [])) + sum(1 for r in recs.values() if r["addl"] == c)

  nodes, edges = [], []
  for row, (c, d) in enumerate(order):
    r = recs[c]
    layer = "root" if d == 0 else "line" if d == 1 else "tenant"
    line = line_of(c) if d else ""
    lines = sorted({line} | ({line_of(r["addl"])} if r["addl"] in recs and depth.get(r["addl"], 0) >= 1 else set())) if d else []
    color = ROOT_COLOR if d == 0 else color_of.get(line, ROOT_COLOR)
    opacity = 1 if r["status"] in ("active", "new") else INACTIVE_OPACITY

    # detail card shown in the side panel when the node is clicked
    kind = {"root": "Root CID", "line": "Service line", "tenant": "Tenant"}[layer]
    if layer == "tenant" and line in recs: kind += " &#183; " + e(line_text(recs[line]["name"]))
    parents = ""
    for p, additional in ((r["parent"], False), (r["addl"], True)):
      if p not in recs: continue
      dot = ROOT_COLOR if depth.get(p) == 0 else color_of.get(line_of(p), ROOT_COLOR)
      tag = '<span class="d-tag">additional</span>' if additional else ""
      parents += (f'<div class="d-parent"><span class="d-dot sm" style="background:{dot}"></span>'
                  f'<span>{e(recs[p]["name"])}</span>{tag}</div>')
    cid_html = f'<span class="d-mono">{e(c)}</span>' + (
      '<span class="d-tag">to be created</span>' if NEW_RE.fullmatch(c) else
      f'<button type="button" class="d-copy" data-copy="{e(c)}">Copy</button>')
    settings = "".join(
      f'<div class="d-set"><span>{label}</span><span class="d-chip {cls if r[k] else "d-off"}">'
      f'{"Enabled" if r[k] else "Disabled"}</span></div>'
      for label, k, cls in (("Policy Inheritance", "pol", "d-pol"), ("Detection Aggregation", "det", "d-det")))
    rows = [("CID String", cid_html),
            ("Status", e(r["status"].capitalize())),
            ("Parents", parents or '<span class="d-muted">None - this is the root</span>'),
            ("Settings", settings),
            ("Child CIDs", str(child_count(c)))]
    detail = (f'<div class="d-head"><span class="d-dot" style="background:{color}"></span>'
              f'<span class="d-name">{e(r["name"])}</span></div><div class="d-sub">{kind}</div>'
              + "".join(f'<div class="d-row"><div class="d-label">{e(k)}</div><div class="d-value">{v}</div></div>'
                        for k, v in rows))

    nodes.append({
      "id": f"{view}/{c}", "name": r["name"], "color": color, "shape": "dot",
      "size": TENANT_SIZE if layer == "tenant" else NODE_SIZE,
      "x": 0, "y": 0, "physics": False, "row": row,
      "opacity": opacity, "font": {"color": f"rgba(255, 255, 255, {opacity})" if opacity < 1 else "#ffffff"},
      "layer": layer, "view": view, "line": line, "lines": lines, "extra": r["addl"] in recs,
      "detail": detail})
    # the page draws tenant names itself, to the right of their dots
    if layer != "tenant": nodes[-1]["label"] = r["name"]

    # links to each parent: parent -> child (policy), child -> parent (detection)
    me = f"{view}/{c}"
    for p, dashed in ((r["parent"], False), (r["addl"], True)):
      if p not in recs: continue
      parent = f"{view}/{p}"
      pairs = [("link", parent, me, POLICY_COLOR if r["pol"] else LINK_COLOR, LINK_WIDTH)]
      if r["det"]: pairs.append(("det", me, parent, DETECTION_COLOR, DETECTION_WIDTH))
      for kind, src, dst, col, width in pairs:
        dim = rgba(col, LINK_OPACITY)
        look = {"color": dim, "highlight": dim, "hover": dim, "inherit": False}
        full = {"color": col, "highlight": col, "hover": col, "inherit": False}
        edges.append({"from": src, "to": dst, "arrows": "to", "kind": kind, "dashes": dashed,
                      "color": look, "base": look, "full": full, "width": width, "baseWidth": width,
                      "smooth": {"type": "curvedCW", "roundness": LINK_CURVE}})
  return nodes, edges



#################################### Part 6: Side Panel ->

def line_filter(lines_js):
  """The Service lines filter: one checkbox per line (multi-select), with its color dot."""
  boxes = "".join(f'<label class="f-option"><input type="checkbox" class="f-line" value="{e(c)}">'
                  f'<span class="f-dot" style="background:{color}"></span><span class="f-text">{e(text)}</span></label>'
                  for c, text, color, _ in lines_js)
  return f'<div class="f-group"><div class="f-group-title">Service lines</div>{boxes}</div>'

# The page around the graph: the overlays on the canvas (Tenants table, Links
# legend, title) and the side panel (View, Filters/Details, Source). The
# %%NAME%% markers are filled in by build_page().
SIDE_PANEL = """
<style>
  body { margin: 0; display: flex; height: 100vh; overflow: hidden; }
  .card { flex: 1 1 0; min-width: 0; }
  #side-panel {
    width: 25%; flex-shrink: 0; background: #111; box-sizing: border-box;
    height: 100vh; overflow-y: auto; font-family: sans-serif;
    display: flex; flex-direction: column; border-left: 1px solid #222;
    scrollbar-width: thin; scrollbar-color: #333 transparent;
  }
  #graph-title {
    position: fixed; top: 14px; left: 37.5%; transform: translateX(-50%);
    z-index: 5; color: #fff; font-family: sans-serif; font-size: 18px;
    font-weight: 700; letter-spacing: 0.18em; pointer-events: none; white-space: nowrap;
  }
  #empty-state {
    position: fixed; top: 50%; left: 37.5%; transform: translate(-50%, -50%);
    z-index: 5; color: #888; font-family: sans-serif; font-size: 14px;
    pointer-events: none; display: none;
  }
  #view-bar { padding: 20px; border-bottom: 1px solid #222; }
  .vb-label, #mode-title {
    color: #888; text-transform: uppercase;
    letter-spacing: 0.08em; font-size: 11px; font-weight: 700;
  }
  #view-toggle { display: flex; gap: 8px; margin-top: 10px; }
  .vt-btn {
    flex: 1; text-align: left; padding: 10px 12px; border-radius: 8px; border: 1px solid #333;
    background: #161616; cursor: pointer; font-family: sans-serif;
  }
  .vt-btn b { display: block; font-size: 14px; color: #ccc; }
  .vt-btn span { display: block; margin-top: 2px; font-size: 11px; color: #777; }
  .vt-btn:hover { border-color: #555; }
  .vt-btn.active { background: var(--vc); border-color: var(--vc); }
  .vt-btn.active b, .vt-btn.active span { color: #fff; }
  .vt-btn:focus-visible { outline: 2px solid #fff; outline-offset: 2px; }
  #mode-title { display: flex; align-items: center; justify-content: space-between; padding: 20px 20px 0; }
  #back-btn {
    background: none; border: 0; padding: 0; cursor: pointer; color: #4fc3f7;
    font-family: sans-serif; font-size: 12px; font-weight: 600;
  }
  #back-btn:hover { text-decoration: underline; }
  #filter-sidebar { padding: 8px 20px 20px; }
  .f-group { padding: 14px 0; }
  .f-group + .f-group { border-top: 1px solid #1f1f1f; }
  .f-group-title { color: #eee; font-size: 13px; font-weight: 600; margin-bottom: 6px; }
  .f-option {
    display: flex; align-items: center; color: #aaa; font-size: 13px; padding: 6px 8px; margin: 0 -8px;
    border-radius: 6px; cursor: pointer; user-select: none;
    transition: background 0.12s, color 0.12s;
  }
  .f-dot { width: 8px; height: 8px; border-radius: 50%; flex: none; margin-right: 8px; }
  .f-text { flex: 1; }
  .f-option:hover { background: #1a1a1a; color: #fff; }
  .f-option:has(input:checked) { color: #fff; }
  .f-option input {
    appearance: none; -webkit-appearance: none; width: 16px; height: 16px;
    margin: 0 10px 0 0; vertical-align: -3px; border: 1.5px solid #555;
    border-radius: 4px; background: #0d0d0d; cursor: inherit;
    transition: background-color 0.12s, border-color 0.12s;
  }
  .f-option:hover input { border-color: #888; }
  .f-option input:checked {
    border-color: #4fc3f7;
    background: #4fc3f7 url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 12 12'%3E%3Cpath d='M2.5 6.2l2.3 2.3 4.7-4.9' fill='none' stroke='%23111' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E") center / 12px no-repeat;
  }
  .f-option input:focus-visible { outline: 2px solid rgba(79,195,247,0.5); outline-offset: 2px; }
  #detail-panel { display: none; padding: 14px 20px 24px; color: #ddd; font-size: 13px; }
  .d-head { display: flex; align-items: center; gap: 10px; }
  .d-dot { width: 12px; height: 12px; border-radius: 50%; flex: none; }
  .d-dot.sm { width: 8px; height: 8px; }
  .d-name { color: #fff; font-size: 15px; font-weight: 700; line-height: 1.35; }
  .d-sub { color: #888; font-size: 12px; margin: 4px 0 14px 22px; }
  .d-row { padding: 12px 0; border-top: 1px solid #1f1f1f; }
  .d-label {
    color: #888; text-transform: uppercase; letter-spacing: 0.08em;
    font-size: 10px; font-weight: 700; margin-bottom: 6px;
  }
  .d-value { color: #eee; line-height: 1.5; }
  .d-mono { font-family: Consolas, monospace; font-size: 12px; word-break: break-all; }
  .d-copy {
    margin-left: 8px; padding: 1px 8px; font-size: 11px; color: #aaa; background: #1b1b1b;
    border: 1px solid #333; border-radius: 4px; cursor: pointer;
  }
  .d-copy:hover { color: #fff; border-color: #555; }
  .d-parent { display: flex; align-items: center; gap: 8px; }
  .d-parent + .d-parent { margin-top: 4px; }
  .d-tag {
    margin-left: 6px; padding: 0 6px; font-size: 10px; color: #aaa;
    border: 1px solid #333; border-radius: 4px;
  }
  .d-set { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
  .d-set + .d-set { margin-top: 8px; }
  .d-chip { padding: 2px 10px; border-radius: 999px; border: 1px solid; font-size: 11px; font-weight: 700; }
  .d-pol { color: %%POLICY%%; border-color: %%POLICY%%; }
  .d-det { color: %%DETECTION%%; border-color: %%DETECTION%%; }
  .d-off { color: #777; border-color: #333; }
  .d-muted { color: #777; }
  .sp-section { padding: 16px 20px; border-top: 1px solid #222; font-size: 12px; color: #bbb; line-height: 1.7; }
  .sp-footer { margin-top: auto; }
  .sp-title {
    color: #888; text-transform: uppercase; letter-spacing: 0.08em;
    font-size: 11px; font-weight: 700; margin-bottom: 8px;
  }
  .ua-row { display: flex; justify-content: space-between; gap: 18px; font-variant-numeric: tabular-nums; }
  .ua-value { color: #fff; font-weight: 700; }
  #counts-box, #legend {
    position: fixed; left: 12px; z-index: 5; background: rgba(17,17,17,0.85);
    color: #bbb; font-family: sans-serif; font-size: 12px; padding: 10px 14px;
    border-radius: 6px; line-height: 1.6; font-variant-numeric: tabular-nums;
  }
  #counts-box { top: 12px; min-width: 170px; }
  #legend { bottom: 12px; }
  #counts-box .sp-title, #legend .sp-title { font-size: 10px; margin-bottom: 4px; }
  .cb-row { display: flex; align-items: center; gap: 8px; }
  .cb-dot { width: 8px; height: 8px; border-radius: 50%; flex: none; }
  .cb-label { flex: 1; }
  .cb-n { color: #fff; font-weight: 700; text-align: right; }
  .cb-total { border-top: 1px solid #333; margin-top: 4px; padding-top: 4px; }
  .cb-total .cb-label { color: #888; }
  .lg-row { display: flex; align-items: center; gap: 10px; }
  .lg-row svg { flex: none; }
</style>
<div id="counts-box"></div>
<div id="legend">
  <div class="sp-title">Links</div>
  <div class="lg-row"><svg width="28" height="8"><line x1="0" y1="4" x2="28" y2="4" stroke="%%POLICY%%" stroke-opacity="%%LINK_OPACITY%%" stroke-width="2"/></svg>Policy Inheritance (parent &#8594; child)</div>
  <div class="lg-row"><svg width="28" height="8"><line x1="0" y1="4" x2="28" y2="4" stroke="%%DETECTION%%" stroke-opacity="%%LINK_OPACITY%%" stroke-width="1.2"/></svg>Detection Aggregation (child &#8594; parent)</div>
  <div class="lg-row"><svg width="28" height="8"><line x1="0" y1="4" x2="28" y2="4" stroke="%%LINK%%" stroke-opacity="%%LINK_OPACITY%%" stroke-width="2"/></svg>Parent link, no Policy Inheritance</div>
  <div class="lg-row"><svg width="28" height="8"><line x1="0" y1="4" x2="28" y2="4" stroke="#888" stroke-opacity="%%LINK_OPACITY%%" stroke-width="2" stroke-dasharray="4 3"/></svg>Additional parent (dashed)</div>
</div>
<div id="graph-title">%%TITLE%%</div>
<div id="empty-state">No CIDs match this filter</div>
<div id="side-panel">
  <div id="view-bar">
    <div class="vb-label">View</div>
    <div id="view-toggle">%%VIEW_BUTTONS%%</div>
  </div>
  <div id="mode-title"><span id="mode-text">Filters</span><button type="button" id="back-btn" hidden>&#8592; Back to filters</button></div>
  <div id="filter-sidebar">%%FILTER_GROUPS%%</div>
  <div id="detail-panel"></div>
  <div class="sp-section sp-footer">%%UPDATED%%</div>
</div>
"""

# Pyvis has no filter, detail panel or tree layout built in - this script runs
# after the network exists: view switch, Service lines filter, click
# highlight and details, the tree layout with the tenant names, and the
# framing of the view.
FILTER_SCRIPT = """
<script>
(function () {
  var filterSidebar = document.getElementById('filter-sidebar');
  var detailPanel = document.getElementById('detail-panel');
  var modeText = document.getElementById('mode-text');
  var backBtn = document.getElementById('back-btn');
  var viewButtons = Array.from(document.querySelectorAll('.vt-btn'));
  var currentView = viewButtons[0].dataset.view;
  var emptyState = document.getElementById('empty-state');

  // each node's own look, restored when the highlight is turned off
  var BASE_LOOK = {};
  nodes.get().forEach(function (n) { BASE_LOOK[n.id] = {color: n.color, opacity: n.opacity, font: n.font}; });
  var lit = [];

  function showFilters() {
    detailPanel.style.display = 'none';
    filterSidebar.style.display = 'block';
    modeText.textContent = 'Filters';
    backBtn.hidden = true;
    clearHighlight();
  }

  function showDetail(nodeId) {
    detailPanel.innerHTML = nodes.get(nodeId).detail;
    filterSidebar.style.display = 'none';
    detailPanel.style.display = 'block';
    modeText.textContent = 'Details';
    backBtn.hidden = false;
  }

  // the selected view: its button filled with its color
  function setView(view) {
    currentView = view;
    viewButtons.forEach(function (b) {
      var on = b.dataset.view === view;
      b.classList.toggle('active', on);
      b.setAttribute('aria-pressed', String(on));
    });
  }

  // Copy button next to the CID String; falls back to a hidden textarea where
  // the clipboard API is not available
  function copyText(text, button) {
    function done() { button.textContent = 'Copied'; setTimeout(function () { button.textContent = 'Copy'; }, 1200); }
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(done, function () {});
      return;
    }
    var area = document.createElement('textarea');
    area.value = text;
    document.body.appendChild(area);
    area.select();
    try { document.execCommand('copy'); done(); } catch (err) {}
    document.body.removeChild(area);
  }
  detailPanel.addEventListener('click', function (event) {
    var button = event.target.closest('[data-copy]');
    if (button) copyText(button.dataset.copy, button);
  });
  backBtn.addEventListener('click', showFilters);

  function checked(cls) {
    return Array.from(document.querySelectorAll('.' + cls + ':checked')).map(function (el) { return el.value; });
  }

  // "forward" follows parent -> child; "backward" child -> parent - never
  // flips direction mid-walk. Only parent links count: the Detection
  // Aggregation links point child -> parent and would turn the walk around.
  function walk(startIds, poolSet, direction) {
    var seen = new Set(startIds);
    var queue = startIds.slice();
    var links = edges.get({filter: function (e) { return e.kind === 'link'; }});
    while (queue.length > 0) {
      var current = queue.pop();
      links.forEach(function (e) {
        if (direction === 'forward' && e.from === current && poolSet.has(e.to) && !seen.has(e.to)) {
          seen.add(e.to); queue.push(e.to);
        }
        if (direction === 'backward' && e.to === current && poolSet.has(e.from) && !seen.has(e.from)) {
          seen.add(e.from); queue.push(e.from);
        }
      });
    }
    return seen;
  }

  function connectedNodes(nodeId) {
    var pool = new Set(nodes.getIds({filter: function (n) { return !n.hidden; }}));
    if (!HIGHLIGHT.chain) {
      return new Set([nodeId].concat(network.getConnectedNodes(nodeId)).filter(function (id) { return pool.has(id); }));
    }
    var chain = walk([nodeId], pool, 'forward');
    walk([nodeId], pool, 'backward').forEach(function (id) { chain.add(id); });
    return chain;
  }

  function highlight(nodeId) {
    clearHighlight();
    var on = connectedNodes(nodeId);
    lit = Array.from(on);
    nodes.update(lit.map(function (id) {
      var fill = BASE_LOOK[id].color;
      return {id: id, opacity: 1, font: {color: '#ffffff'}, borderWidth: 3, borderWidthSelected: 4,
              color: {background: fill, border: HIGHLIGHT.color,
                      highlight: {background: fill, border: HIGHLIGHT.color},
                      hover: {background: fill, border: HIGHLIGHT.color}},
              shadow: {enabled: true, color: HIGHLIGHT.color, size: 18, x: 0, y: 0}};
    }));
    var faded = {color: 'rgba(85,85,85,0.25)', highlight: 'rgba(85,85,85,0.25)', hover: 'rgba(85,85,85,0.25)', inherit: false};
    edges.update(edges.get().map(function (e) {
      var inChain = on.has(e.from) && on.has(e.to);
      return {id: e.id, color: inChain ? e.full : faded, width: inChain ? e.baseWidth + HIGHLIGHT.width : e.baseWidth};
    }));
  }

  function clearHighlight() {
    if (lit.length === 0) return;
    nodes.update(lit.map(function (id) {
      var base = BASE_LOOK[id];
      return {id: id, color: base.color, opacity: base.opacity, font: base.font,
              borderWidth: 1, borderWidthSelected: 2, shadow: false};
    }));
    edges.update(edges.get().map(function (e) { return {id: e.id, color: e.base, width: e.baseWidth}; }));
    lit = [];
  }

  // the view restricts the universe (pool). Ticked service lines keep the
  // line and every tenant linked to it (as primary or additional parent);
  // each tenant brings its parents up to the root, both when it has two.
  function computeVisible(view, lines) {
    var pool = nodes.getIds({filter: function (n) { return n.view === view; }});
    if (lines.length === 0) return new Set(pool);
    var poolSet = new Set(pool);
    var base = [];
    pool.forEach(function (id) {
      var n = nodes.get(id);
      if (n.layer !== 'root' && n.lines.some(function (l) { return lines.indexOf(l) !== -1; })) base.push(id);
    });
    var visible = new Set(base);
    walk(base, poolSet, 'backward').forEach(function (id) { visible.add(id); });
    return visible;
  }

  // the Tenants table: visible tenants per service line (by primary
  // parent's line), and the total
  function updateCounts(visible) {
    var counts = {}, total = 0;
    visible.forEach(function (id) {
      var n = nodes.get(id);
      if (n.layer === 'tenant') { counts[n.line] = (counts[n.line] || 0) + 1; total++; }
    });
    function row(dot, label, n, cls) {
      return '<div class="cb-row' + (cls ? ' ' + cls : '') + '">' +
        (dot ? '<span class="cb-dot" style="background:' + dot + '"></span>' : '') +
        '<span class="cb-label">' + label + '</span><span class="cb-n">' + n + '</span></div>';
    }
    document.getElementById('counts-box').innerHTML = '<div class="sp-title">Tenants</div>' +
      LINES.map(function (l) { return row(l[2], l[3], counts[l[0]] || 0); }).join('') +
      row(null, 'Total', total, 'cb-total');
  }

  var NODE_FONT = '14px arial';
  var NODE_LABEL = 20;

  var measure = document.createElement('canvas').getContext('2d');
  function textWidth(text, font) {
    measure.font = font;
    return measure.measureText(text).width;
  }

  // each node's name width (measured once per node)
  var nameWidths = {};
  function nameWidth(id) {
    if (!(id in nameWidths)) nameWidths[id] = textWidth(nodes.get(id).name, NODE_FONT);
    return nameWidths[id];
  }

  // how far a root or line node reaches to each side: half its label or its
  // dot, whichever is wider
  function halfWidth(id) {
    return Math.max(LAYOUT.nodeSize, nameWidth(id) / 2);
  }

  function widest(ids) {
    return ids.reduce(function (most, id) { return Math.max(most, halfWidth(id)); }, LAYOUT.nodeSize);
  }

  // a tenant's name sits to the right of its dot, LAYOUT.labelGap px away,
  // vertically centered on it: where it starts and ends
  function nameBox(n, p) {
    var start = p.x + n.size + LAYOUT.labelGap;
    return {left: start, right: start + nameWidth(n.id), top: p.y - NODE_LABEL / 2, bottom: p.y + NODE_LABEL / 2};
  }

  function shownTenants() {
    var shown = nodes.get({filter: function (n) { return !n.hidden && n.layer === 'tenant'; }});
    var positions = network.getPositions(shown.map(function (n) { return n.id; }));
    return shown.map(function (n) { return {node: n, p: positions[n.id], box: nameBox(n, positions[n.id])}; });
  }

  // tenant names, drawn over the graph in each node's font color
  network.on('afterDrawing', function (ctx) {
    ctx.save();
    ctx.font = NODE_FONT;
    ctx.textAlign = 'left';
    ctx.textBaseline = 'middle';
    shownTenants().forEach(function (t) {
      ctx.fillStyle = t.node.font.color;
      ctx.fillText(t.node.name, t.box.left, t.p.y);
    });
    ctx.restore();
  });

  // the tenant whose name is under a canvas point, if any
  function nameAt(point) {
    var hit = null;
    shownTenants().forEach(function (t) {
      var b = t.box;
      if (point.x >= b.left && point.x <= b.right && point.y >= b.top && point.y <= b.bottom) hit = t.node.id;
    });
    return hit;
  }

  // the tree, from the visible CIDs only (a filter leaves no gaps): root,
  // service lines and tenants in three columns, far enough apart for the
  // widest root and line labels. Each service line gets a band, in LINES
  // order (name order) top to bottom; its tenants (by primary parent) are
  // stacked one below the other, LAYOUT.rowHeight apart. A line sits at the
  // middle of its band, the root at the middle of the lines.
  function layoutTree(visible) {
    var byLayer = {root: [], line: [], tenant: []};
    visible.forEach(function (id) { byLayer[nodes.get(id).layer].push(id); });
    Object.keys(byLayer).forEach(function (layer) {
      byLayer[layer].sort(function (a, b) { return nodes.get(a).row - nodes.get(b).row; });
    });
    var rootHalf = widest(byLayer.root), lineHalf = widest(byLayer.line);
    var lineX = rootHalf + lineHalf + LAYOUT.columnGap;
    var tenantX = lineX + lineHalf + LAYOUT.columnGap;
    var lineOf = {}, bands = {};
    byLayer.line.forEach(function (id) { lineOf[nodes.get(id).line] = id; });
    byLayer.tenant.forEach(function (id) {
      var key = nodes.get(id).line;
      (bands[key] = bands[key] || []).push(id);
    });
    // tenants with an additional parent first (top of the band), each group
    // in name order
    Object.keys(bands).forEach(function (key) {
      bands[key].sort(function (a, b) {
        return (nodes.get(b).extra - nodes.get(a).extra) || (nodes.get(a).row - nodes.get(b).row);
      });
    });
    var updates = [], centers = [], y = 0;
    LINES.forEach(function (l) {
      var tenants = bands[l[0]] || [], lineId = lineOf[l[0]];
      if (!lineId && tenants.length === 0) return;
      tenants.forEach(function (id, i) {
        updates.push({id: id, x: tenantX, y: y + i * LAYOUT.rowHeight});
      });
      var height = tenants.length ? (tenants.length - 1) * LAYOUT.rowHeight : 0;
      if (lineId) {
        updates.push({id: lineId, x: lineX, y: y + height / 2});
        centers.push(y + height / 2);
      }
      y += height + LAYOUT.bandGap;
    });
    var rootY = centers.length ? (Math.min.apply(null, centers) + Math.max.apply(null, centers)) / 2 : 0;
    byLayer.root.forEach(function (id, i) { updates.push({id: id, x: 0, y: rootY + i * LAYOUT.bandGap}); });
    nodes.update(updates);
  }

  // the area each visible CID takes, dot and name, from its live position
  // (a dragged node is followed)
  function frameRects() {
    var shown = nodes.get({filter: function (n) { return !n.hidden; }});
    var positions = network.getPositions(shown.map(function (n) { return n.id; }));
    return shown.map(function (n) {
      var p = positions[n.id], r = n.size;
      if (n.layer === 'tenant') {
        var box = nameBox(n, p);
        return {left: p.x - r, right: box.right, top: Math.min(p.y - r, box.top), bottom: Math.max(p.y + r, box.bottom)};
      }
      return {left: p.x - halfWidth(n.id), right: p.x + halfWidth(n.id), top: p.y - r, bottom: p.y + r + NODE_LABEL};
    });
  }

  // the view that fits the bounds between the given top and bottom margins
  // (FIT_MARGIN px from the sides); never zooms in past 1
  var FIT_MARGIN = 24;
  function framing(b, canvas, marginTop, marginBottom) {
    var scale = Math.min(1, (canvas.width - 2 * FIT_MARGIN) / (b.right - b.left),
                         (canvas.height - marginTop - marginBottom) / (b.bottom - b.top));
    return {x: (b.left + b.right) / 2, y: (b.top + b.bottom) / 2 - (marginTop - marginBottom) / 2 / scale, scale: scale};
  }

  // whether a CID would fall under one of the overlays in that view
  function covered(view, rects, canvas, overlays) {
    var cx = canvas.left + canvas.width / 2, cy = canvas.top + canvas.height / 2;
    return rects.some(function (r) {
      var left = cx + (r.left - view.x) * view.scale, right = cx + (r.right - view.x) * view.scale;
      var top = cy + (r.top - view.y) * view.scale, bottom = cy + (r.bottom - view.y) * view.scale;
      return overlays.some(function (o) { return left < o.right && right > o.left && top < o.bottom && bottom > o.top; });
    });
  }

  // frames every visible CID under the title, as large as fits; when a CID
  // would then fall under the Tenants table or the Links legend, it keeps
  // clear of their whole height instead
  function fitBoxes() {
    var rects = frameRects();
    if (rects.length === 0) return;
    var bounds = {left: Math.min.apply(null, rects.map(function (r) { return r.left; })),
                  right: Math.max.apply(null, rects.map(function (r) { return r.right; })),
                  top: Math.min.apply(null, rects.map(function (r) { return r.top; })),
                  bottom: Math.max.apply(null, rects.map(function (r) { return r.bottom; }))};
    var canvas = document.querySelector('#mynetwork canvas').getBoundingClientRect();
    var countsBox = document.getElementById('counts-box').getBoundingClientRect();
    var legend = document.getElementById('legend').getBoundingClientRect();
    var titleBottom = document.getElementById('graph-title').getBoundingClientRect().bottom;
    var freeBottom = Math.min(canvas.bottom, window.innerHeight);
    var view = framing(bounds, canvas, titleBottom - canvas.top + FIT_MARGIN, canvas.bottom - freeBottom + FIT_MARGIN);
    if (covered(view, rects, canvas, [countsBox, legend])) {
      view = framing(bounds, canvas, Math.max(titleBottom, countsBox.bottom) - canvas.top + FIT_MARGIN,
                     canvas.bottom - Math.min(freeBottom, legend.top) + FIT_MARGIN);
    }
    network.moveTo({position: {x: view.x, y: view.y}, scale: view.scale,
                    animation: {duration: 300, easingFunction: 'easeInOutQuad'}});
  }

  function applyFilter() {
    clearHighlight();
    var visible = computeVisible(currentView, checked('f-line'));
    nodes.update(nodes.getIds().map(function (id) { return {id: id, hidden: !visible.has(id)}; }));
    edges.update(edges.get().map(function (e) {
      return {id: e.id, hidden: !(visible.has(e.from) && visible.has(e.to))};
    }));
    layoutTree(visible);
    updateCounts(visible);
    emptyState.style.display = visible.size === 0 ? 'block' : 'none';
    fitBoxes();
  }
  document.querySelectorAll('.f-line').forEach(function (el) {
    el.addEventListener('change', applyFilter);
  });
  viewButtons.forEach(function (b) {
    b.addEventListener('click', function () { setView(b.dataset.view); showFilters(); applyFilter(); });
  });
  setView(currentView);
  network.setSize('100%', '100%');
  applyFilter();
  // vis-network adjusts the view on its own on the first draw and on a
  // resize, which undoes the framing - framed again right after
  network.once('afterDrawing', function () { setTimeout(fitBoxes, 0); });
  network.on('resize', function () { setTimeout(fitBoxes, 0); });
  window.addEventListener('resize', function () { setTimeout(fitBoxes, 0); });

  // a click on a tenant's name selects it, like a click on its dot
  network.on('click', function (params) {
    var id = params.nodes.length > 0 ? params.nodes[0] : nameAt(params.pointer.canvas);
    if (id) {
      network.selectNodes([id]);
      highlight(id);
      showDetail(id);
    } else {
      showFilters();
    }
  });

})();
</script>
"""

# The same page pyvis writes (vis-network 9.1.2 from cdnjs), with the side
# panel and the script above added.
PAGE = """<html>
<head>
<meta charset="utf-8">
<title>%%TAB_TITLE%%</title>
<link rel="icon" href="%%FAVICON%%">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/vis-network/9.1.2/dist/dist/vis-network.min.css" integrity="sha512-WgxfT5LWjfszlPHXRmBWHkV2eceiWTOBvrKCNbdgDYTHrT2AeLCGbF4sZlZw3UMN3WtL0tGUoIAKsu8mllg/XA==" crossorigin="anonymous" referrerpolicy="no-referrer" />
<script src="https://cdnjs.cloudflare.com/ajax/libs/vis-network/9.1.2/dist/vis-network.min.js" integrity="sha512-LnvoEWDFrqGHlHmDD2101OrLcbsfkrzoSpvtSQtxK3RMnRV0eOkhhBN2dXHKRrUU8p2DGRTk35n4O8nWSVe1mQ==" crossorigin="anonymous" referrerpolicy="no-referrer"></script>
<style type="text/css">
  *, *::before, *::after { box-sizing: border-box; }
  #mynetwork { width: 100%; height: 100vh; background-color: #000000; border: 1px solid lightgray; position: relative; float: left; }
</style>
</head>
<body>
<div class="card" style="width: 100%">
  <div id="mynetwork" class="card-body"></div>
</div>
<script type="text/javascript">
  var nodes = new vis.DataSet(%%NODES%%);
  var edges = new vis.DataSet(%%EDGES%%);
  var network = new vis.Network(document.getElementById('mynetwork'), {nodes: nodes, edges: edges}, %%OPTIONS%%);
</script>
%%SIDE_PANEL%%
<script>var LAYOUT = %%LAYOUT%%; var HIGHLIGHT = %%HIGHLIGHT%%; var LINES = %%LINES%%;</script>
%%FILTER_SCRIPT%%
</body>
</html>
"""

def js(value):
  """JSON for an inline <script>: '</' is escaped so no string can close the tag."""
  return json.dumps(value, ensure_ascii=False).replace("</", "<\\/")



#################################### Part 7: HTML Generation ->

def build_page(today, t_info, expected, x_info):
  """The whole HTML page: the Expected view (when there is one) and the
  Today view, in the same graph."""
  exported = datetime.fromtimestamp(os.path.getmtime(INPUT))
  t_roots = t_info[2]
  company = today[t_roots[0]]["name"].split("|")[0].split(" - ", 1)[-1].strip() if t_roots else ""
  views = ([("expected", expected, x_info)] if expected is not None else []) + [("today", today, t_info)]

  # one color per service line, the same in both views
  line_keys = []
  for _, _, (order, _, _) in views:
    for c, d in order:
      if d == 1 and c not in line_keys: line_keys.append(c)
  color_of = {c: LINE_COLORS[i % len(LINE_COLORS)] for i, c in enumerate(line_keys)}

  all_nodes, all_edges = [], []
  for key, recs, info in views:
    nodes, edges = graph_view(key, recs, info, color_of)
    all_nodes += nodes
    all_edges += edges
  lines_js = [[c, line_text(name_of(c, today, expected)), color_of[c], short(name_of(c, today, expected))]
              for c in line_keys]

  stamp = "%b %d, %Y &#183; %H:%M"
  updated = ('<div class="sp-title">Source</div>'
             f'<div class="ua-row"><span>CID export</span><span class="ua-value">{exported.strftime(stamp)}</span></div>'
             f'<div class="ua-row"><span>Generated</span><span class="ua-value">{datetime.now().strftime(stamp)}</span></div>')
  view_buttons = "".join(
    f'<button type="button" class="vt-btn" data-view="{k}" style="--vc: {VIEW_STYLE[k][2]}">'
    f'<b>{e(VIEW_STYLE[k][0])}</b><span>{e(VIEW_STYLE[k][1])}</span></button>' for k, _, _ in views)
  side_panel = (SIDE_PANEL.replace("%%UPDATED%%", updated)
                .replace("%%TITLE%%", e(TITLE))
                .replace("%%VIEW_BUTTONS%%", view_buttons)
                .replace("%%FILTER_GROUPS%%", line_filter(lines_js))
                .replace("%%POLICY%%", POLICY_COLOR).replace("%%DETECTION%%", DETECTION_COLOR)
                .replace("%%LINK%%", LINK_COLOR).replace("%%LINK_OPACITY%%", str(LINK_OPACITY)))

  layout = {"nodeSize": NODE_SIZE, "rowHeight": ROW_HEIGHT, "labelGap": LABEL_GAP, "columnGap": COLUMN_GAP,
            "bandGap": BAND_GAP}
  options = {"physics": {"enabled": False}, "edges": {"arrows": {"to": {"scaleFactor": 0.5}}, "selectionWidth": 0, "hoverWidth": 0}}
  highlight = {"color": HIGHLIGHT_COLOR, "chain": HIGHLIGHT_CHAIN, "width": HIGHLIGHT_WIDTH}
  return (PAGE.replace("%%TAB_TITLE%%", e(f"{TAB_TITLE} - {company}" if company else TAB_TITLE))
          .replace("%%FAVICON%%", FAVICON)
          .replace("%%NODES%%", js(all_nodes))
          .replace("%%EDGES%%", js(all_edges))
          .replace("%%OPTIONS%%", js(options))
          .replace("%%SIDE_PANEL%%", side_panel)
          .replace("%%LAYOUT%%", js(layout))
          .replace("%%HIGHLIGHT%%", js(highlight))
          .replace("%%LINES%%", js(lines_js))
          .replace("%%FILTER_SCRIPT%%", FILTER_SCRIPT))


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
