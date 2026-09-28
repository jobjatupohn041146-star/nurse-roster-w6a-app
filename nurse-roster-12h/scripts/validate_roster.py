#!/usr/bin/env python3
"""Check a roster workbook against the ward rules. Usage: validate_roster.py file.xlsx [--prev prev.json]"""
import sys, json, argparse
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from roster_lib import read_roster, validate

ap = argparse.ArgumentParser()
ap.add_argument("xlsx"); ap.add_argument("--prev"); ap.add_argument("--sheet")
a = ap.parse_args()
prev = json.load(open(a.prev, encoding="utf-8")) if a.prev else None
wb, ws, days, nurses = read_roster(a.xlsx, a.sheet)
v = validate(nurses, len(days), prev=prev)
print(f"{len(nurses)} พยาบาล, {len(days)} วัน")
print("\n".join(v) if v else "ผ่านทุกกฎ")
sys.exit(1 if v else 0)
