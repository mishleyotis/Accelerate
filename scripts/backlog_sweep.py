"""Check every open finding for evidence it is already fixed.

"Check all learning notes backlog and implement each." Implementing 183 in
one pass is not possible; CHECKING all 183 is, and it is the half that tells
you which of them are still real. MEM-0095 had been fixed for days and sat
open, so the backlog's own count was misleading.

For each open finding this extracts the concrete things it names — a gate id,
a repo path, a symbol — and reports whether each now exists. That is evidence
toward "already fixed", never proof; nothing is closed from this script.
"""
import sys, re, json, subprocess
from pathlib import Path
ROOT_ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_ / 'scripts'))
sys.path.insert(0, str(ROOT_ / 'apps' / 'mcp'))
from dma_connector import call

ROOT = ROOT_
from dma_mcp.gates import GATES

GATE_RE = re.compile(r'\b((?:CG|AG|SG|ET)-\d{2,3})\b')
PATH_RE = re.compile(r'\b((?:apps|packages|scripts|plugins|migrations|infra)'
                     r'/[\w./-]+\.(?:py|js|jsx|json|md|sql))\b')
SYM_RE = re.compile(r'\b(_?[a-z][a-z0-9_]{6,})\(')

found = call('list_open_findings', limit=300)['findings']
print(f"open findings: {len(found)}\n")

rows = []
for f in found:
    blob = " ".join(str(f.get(k) or "") for k in
                    ("title", "measurement", "fix_hint"))
    gates = sorted(set(GATE_RE.findall(blob)))
    paths = sorted(set(PATH_RE.findall(blob)))
    syms = sorted(set(SYM_RE.findall(blob)))

    gates_live = [g for g in gates if g in GATES]
    paths_live = [p for p in paths if (ROOT / p).exists()]
    paths_gone = [p for p in paths if not (ROOT / p).exists()]

    # a symbol the finding names that now exists somewhere in the repo
    syms_live = []
    for s in syms[:6]:
        r = subprocess.run(['grep', '-rl', '--include=*.py', f'def {s}',
                            'apps', 'packages', 'scripts', 'plugins'],
                           capture_output=True, text=True, cwd=ROOT)
        if r.stdout.strip():
            syms_live.append(s)

    signal = 0
    if gates_live:
        signal += 2
    if syms_live:
        signal += 2
    if paths_gone:
        signal += 1          # the file it blamed no longer exists
    rows.append((signal, f, gates, gates_live, paths_live, paths_gone, syms_live))

rows.sort(key=lambda r: (-r[0], r[1]['finding_id']))

strong = [r for r in rows if r[0] >= 4]
some = [r for r in rows if 2 <= r[0] < 4]
none = [r for r in rows if r[0] < 2]

print(f"STRONG evidence of a fix already in place : {len(strong)}")
print(f"SOME evidence                             : {len(some)}")
print(f"NO structural signal (needs reading)      : {len(none)}\n")

print("=" * 78)
print("STRONG — the gate it asked for is registered AND the symbol exists")
print("=" * 78)
for sig, f, g, gl, pl, pg, sl in strong[:40]:
    print(f"{f['finding_id']} {f['severity']:8} {f['component'][:22]:24} "
          f"gates={gl} syms={sl[:3]}")
    print(f"    {f['title'][:96]}")

out = {'strong': [r[1]['finding_id'] for r in strong],
       'some': [r[1]['finding_id'] for r in some],
       'none': [r[1]['finding_id'] for r in none]}
if len(sys.argv) > 1:
    json.dump(out, open(sys.argv[1], 'w'), indent=1)
    print(f"\nwrote {sys.argv[1]}")
