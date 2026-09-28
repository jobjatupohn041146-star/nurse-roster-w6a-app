#!/usr/bin/env python3
"""Fill empty cells of a roster workbook with C4/P4/CK/'-' so all ward rules hold.
Cells already filled (leave, X, training, pre-assigned shifts) are LOCKED and never changed.
Usage: solve_roster.py in.xlsx out.xlsx [--prev prev.json] [--time 60] [--no-ck] [--allow-ck-day]
prev.json: {"ชื่อ นามสกุล": ["C4","C4","X","P4"]}  # last days of previous month, oldest first
Requires: pip install ortools openpyxl
"""
import sys, json, argparse
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from ortools.sat.python import cp_model
from openpyxl.styles import PatternFill, Alignment
from roster_lib import *

ap = argparse.ArgumentParser()
ap.add_argument("inp"); ap.add_argument("out")
ap.add_argument("--prev"); ap.add_argument("--sheet"); ap.add_argument("--time", type=int, default=60)
ap.add_argument("--no-ck", action="store_true", help="do not schedule any new CK shifts")
ap.add_argument("--ck-not-day", action="store_true", help="CK does not count toward the 3-person day requirement")
ap.add_argument("--seed", type=int, default=1)
a = ap.parse_args()

R = dict(DEFAULT_RULES, ck_counts_as_day=not a.ck_not_day)
prev = json.load(open(a.prev, encoding="utf-8")) if a.prev else {}
wb, ws, days, nurses = read_roster(a.inp, a.sheet)
N, D = len(nurses), len(days)

m = cp_model.CpModel()
# cell[i][d] -> dict code->(int|BoolVar). For locked cells: constants.
V = {}
for i, n in enumerate(nurses):
    for d in range(D):
        code = n["grid"][d]
        if code is not None:
            V[i, d] = {k: int(code == k) for k in ("C4", "P4", "CK", "TRAIN")}
            V[i, d]["work"] = int(code in WORK)
            V[i, d]["plain"] = int(code in PLAIN_OFF)      # off w/o leave justification
            V[i, d]["off"] = int(is_off(code))
        else:
            c, p = m.NewBoolVar(f"c{i}_{d}"), m.NewBoolVar(f"p{i}_{d}")
            k = m.NewBoolVar(f"k{i}_{d}") if not a.no_ck else 0
            m.Add(sum(x for x in (c, p, k) if not isinstance(x, int)) <= 1)
            w = m.NewBoolVar(f"w{i}_{d}")
            m.Add(w == sum(x for x in (c, p, k) if not isinstance(x, int)))
            o = m.NewBoolVar(f"o{i}_{d}"); m.Add(o + w == 1)
            V[i, d] = dict(C4=c, P4=p, CK=k, TRAIN=0, work=w, plain=o, off=o)

def hasvar(*xs):
    return any(not isinstance(x, int) for x in xs)

def prevcode(i, back):           # back=1 -> last day of previous month
    lst = prev.get(nurses[i]["name"], [])
    return norm(lst[-back]) if len(lst) >= back else None

for i in range(N):
    # consecutive work <= 4 (windows of 5), incl. previous month tail
    seq = [dict(work=int(prevcode(i, b) in WORK), off=int(is_off(prevcode(i, b))),
                plain=int(prevcode(i, b) in PLAIN_OFF), C4=0, CK=0, P4=int(prevcode(i, b) == "P4"))
           for b in range(4, 0, -1)] + [V[i, d] for d in range(D)]
    for t in range(len(seq) - 4):
        w = [seq[t + j]["work"] for j in range(5)]
        if hasvar(*w): m.Add(sum(w) <= 4)
    # no P4 -> C4/CK next day
    for t in range(len(seq) - 1):
        x = seq[t]["P4"]; y = [seq[t + 1]["C4"], seq[t + 1]["CK"]]
        if hasvar(x, *y): m.Add(x + sum(y) <= 1)
    # 3rd+ consecutive off day must be a leave code: off,off,plain not allowed
    for t in range(len(seq) - 2):
        a1, a2, a3 = seq[t]["off"], seq[t + 1]["off"], seq[t + 2]["plain"]
        if hasvar(a1, a2, a3): m.Add(a1 + a2 + a3 <= 2)
    # monthly caps
    for code, cap in (("C4", R["cap_C4"]), ("CK", R["cap_CK"]), ("P4", R["cap_P4"])):
        m.Add(sum(V[i, d][code] for d in range(D)) <= cap)

pen = []
for d in range(D):
    day = sum(V[i, d]["C4"] + (V[i, d]["CK"] if R["ck_counts_as_day"] else 0) for i in range(N))
    ngt = sum(V[i, d]["P4"] for i in range(N))
    for tot, need, nm in ((day, R["need_C4"], "c"), (ngt, R["need_P4"], "p")):
        sh, ov = m.NewIntVar(0, N, f"s{nm}{d}"), m.NewIntVar(0, N, f"o{nm}{d}")
        m.Add(tot + sh - ov == need)
        pen += [10000 * sh, 200 * ov]

# fairness: balance total hours-ish (C4=12, P4=12, CK=16) among nurses
hrs = [sum(12 * V[i, d]["C4"] + 12 * V[i, d]["P4"] + 16 * V[i, d]["CK"] for d in range(D)) for i in range(N)]
hi, lo = m.NewIntVar(0, 1000, "hi"), m.NewIntVar(0, 1000, "lo")
for h in hrs: m.Add(h <= hi); m.Add(h >= lo)
pen.append(5 * (hi - lo))
# CK costs 16h: use only if needed
pen += [30 * V[i, d]["CK"] for i in range(N) for d in range(D) if not isinstance(V[i, d]["CK"], int)]
# comfort: avoid lone single work days sandwiched between offs (prefer blocks of 2-4)
for i in range(N):
    for d in range(1, D - 1):
        if hasvar(V[i, d]["work"]):
            iso = m.NewBoolVar(f"iso{i}_{d}")
            m.Add(iso >= V[i, d]["work"] + V[i, d - 1]["off"] + V[i, d + 1]["off"] - 2)
            pen.append(3 * iso)
m.Minimize(sum(pen))

s = cp_model.CpSolver()
s.parameters.max_time_in_seconds = a.time
s.parameters.num_workers = 8
s.parameters.random_seed = a.seed
st = s.Solve(m)
print("status:", s.StatusName(st))
if st not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
    print("ไม่พบคำตอบ: ข้อจำกัดขัดกัน (เช่น วันลาที่ล็อกไว้มากเกินไป หรือคนไม่พอ) — ลอง --ck-not-day / ผ่อนโควตา / เพิ่มคน")
    sys.exit(2)

fills = {"C4": PatternFill("solid", fgColor="FFF2CC"), "CK": PatternFill("solid", fgColor="FCE4D6"),
         "P4": PatternFill("solid", fgColor="D9E1F2")}
for i, n in enumerate(nurses):
    for d in range(D):
        if n["grid"][d] is not None: continue
        code = next((k for k in ("C4", "P4", "CK") if not isinstance(V[i, d][k], int) and s.Value(V[i, d][k])), "-")
        n["grid"][d] = code
        cell = ws.cell(n["row"], DAY_COL0 + d, code)
        cell.alignment = Alignment(horizontal="center")
        if code in fills: cell.fill = fills[code]

# summary columns (template: AL=C4 AM=CK AN=P4 AO=OFF AP=V AQ=LP AR=hours)
hdr = {str(ws.cell(HEADER_ROW, c).value).strip(): c for c in range(DAY_COL0 + D, DAY_COL0 + D + 12)
       if ws.cell(HEADER_ROW, c).value}
for n in nurses:
    g = n["grid"]; r = n["row"]
    cnt = lambda *cs: sum(1 for x in g if x in cs)
    vals = {"C4": cnt("C4"), "CK": cnt("CK"), "P4": cnt("P4"),
            "OFF": cnt("X", "-", "HBD", "LK", "H"), "V": cnt("V"), "LP": cnt("LP")}
    for k, v in vals.items():
        if k in hdr: ws.cell(r, hdr[k], v or None)
    if "รวม" in hdr and all(k in hdr for k in ("C4", "CK", "P4")):
        cl = lambda k: ws.cell(r, hdr[k]).column_letter
        ws.cell(r, hdr["รวม"], f"={cl('C4')}{r}*12+{cl('CK')}{r}*16+{cl('P4')}{r}*12")

# report sheet
rep = wb.create_sheet("ตรวจสอบ")
viol = validate(nurses, D, R, prev)
rep.append(["ผลตรวจกฎเวร"]); rep.append(["ผ่านทุกกฎ" if not viol else f"พบ {len(viol)} รายการ"])
for v in viol: rep.append([v])
rep.append([]); rep.append(["วันที่", "C4", "CK", "P4"])
for d in range(D):
    rep.append([d + 1] + [sum(1 for n in nurses if n["grid"][d] == k) for k in ("C4", "CK", "P4")])
rep.column_dimensions["A"].width = 60
wb.save(a.out)
print("saved", a.out); print("\n".join(viol) if viol else "ผ่านทุกกฎ")
