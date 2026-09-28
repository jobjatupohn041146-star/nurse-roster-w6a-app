"""
roster_engine.py
Core engine for 12-hour Nurse Rostering (W6A Ward standard).
Provides:
  - Solver using OR-Tools CP-SAT (with heuristic fallback)
  - Comprehensive rule validation
  - Excel template parser and exporter with openpyxl
"""

import os
import re
import io
import json
import copy
from typing import List, Dict, Any, Tuple, Optional

# Constants & Default Ward Rules
WORK_SHIFTS = {'C4', 'P4', 'CK', 'TRAIN'}
LEAVE_CODES = {'V', 'HBD', 'LK', 'LP', 'H'}
PLAIN_OFF = {'X', '-'}
OFF_CODES = LEAVE_CODES | PLAIN_OFF
DAY_SHIFTS = {'C4', 'CK'}

DEFAULT_RULES = {
    'max_consec_work': 4,
    'max_consec_plain_off': 2,
    'cap_C4': 11,
    'cap_CK': 4,
    'cap_P4': 8,
    'need_C4': 3,
    'need_P4': 2,
    'ck_counts_as_day': True,
    'require_senior_per_shift': True,
}

SHIFT_HOURS = {
    'C4': 12,
    'P4': 12,
    'CK': 16,
    'TRAIN': 12,
    'c': 12,
}

COLOR_MAP = {
    'C4': 'FFF2CC',
    'CK': 'FCE4D6',
    'P4': 'D9E1F2',
    'X': 'F2F2F2',
    '-': 'FFFFFF',
    'V': 'E2EFDA',
    'HBD': 'F8CBAD',
    'LK': 'FFF2CC',
    'LP': 'F2DCDB',
    'TRAIN': 'E7E6E6',
}

def norm_code(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    if not s or s.lower() == 'none':
        return None
    u = s.upper().replace(' ', '')
    if u in ('C4', 'P4', 'CK', 'X', 'V', 'LP', 'HBD', 'LK', 'H', '-'):
        return u
    if u == 'C' or 'อบรม' in s:
        return 'TRAIN'
    return u

def is_work(code: Optional[str]) -> bool:
    return code is not None and (code in WORK_SHIFTS or code == 'TRAIN')

def is_off(code: Optional[str]) -> bool:
    if code is None:
        return False
    return code in OFF_CODES or code.startswith('H?')

def is_leave(code: Optional[str]) -> bool:
    if code is None:
        return False
    return code in LEAVE_CODES or code.startswith('H?')

def is_plain_off(code: Optional[str]) -> bool:
    return code in PLAIN_OFF

def validate_schedule(nurses: List[Dict[str, Any]],
                      ndays: int,
                      rules: Optional[Dict[str, Any]] = None,
                      prev_tail: Optional[Dict[str, List[str]]] = None) -> List[Dict[str, Any]]:
    R = dict(DEFAULT_RULES, **(rules or {}))
    prev_tail = prev_tail or {}
    violations = []

    for n_idx, n in enumerate(nurses):
        name = n.get('name') or f"พยาบาลลำดับ {n.get('no', n_idx + 1)}"
        grid = [norm_code(c) for c in n.get('grid', [])]
        raw_tail = prev_tail.get(name) or prev_tail.get(str(n.get('no'))) or []
        tail = [norm_code(c) for c in raw_tail]
        full_seq = tail + grid
        tail_len = len(tail)

        # 1. Consecutive work <= max_consec_work
        work_run = 0
        for i, c in enumerate(full_seq):
            if is_work(c):
                work_run += 1
                if work_run > R['max_consec_work'] and i >= tail_len:
                    day_num = i - tail_len + 1
                    violations.append({
                        'nurse_name': name,
                        'nurse_index': n_idx,
                        'day': day_num,
                        'rule': 'max_consec_work',
                        'message': f'{name}: ขึ้นเวรติดต่อกัน {work_run} วัน (เกินเกณฑ์ {R["max_consec_work"]} วัน) ในวันที่ {day_num}',
                        'severity': 'error'
                    })
            else:
                work_run = 0

        # 2. Reverse shift: P4 -> C4 or P4 -> CK
        for i in range(len(full_seq) - 1):
            if full_seq[i] == 'P4' and full_seq[i + 1] in DAY_SHIFTS and (i + 1) >= tail_len:
                day_num = i - tail_len + 2
                violations.append({
                    'nurse_name': name,
                    'nurse_index': n_idx,
                    'day': day_num,
                    'rule': 'reverse_shift',
                    'message': f'{name}: ขึ้นเวรย้อน P4 → {full_seq[i+1]} (วันที่ {day_num-1} ต่อ วันที่ {day_num}) พักไม่ถึง 12 ชม.',
                    'severity': 'error'
                })

        # 3. Off run: Day 3+ of consecutive off MUST be leave code
        off_run = 0
        for i, c in enumerate(full_seq):
            if c is None:
                off_run = 0
                continue
            if is_off(c):
                off_run += 1
                if off_run >= 3 and i >= tail_len and not is_leave(c):
                    day_num = i - tail_len + 1
                    violations.append({
                        'nurse_name': name,
                        'nurse_index': n_idx,
                        'day': day_num,
                        'rule': 'consec_plain_off',
                        'message': f'{name}: ออฟวันที่ {off_run} ต่อเนื่องแต่เป็นรหัส "{c}" ไม่ได้ระบุสิทธิ์ลา (วันที่ {day_num})',
                        'severity': 'warning'
                    })
            else:
                off_run = 0

        # 4. Monthly caps
        counts = {
            'C4': sum(1 for c in grid if c == 'C4'),
            'CK': sum(1 for c in grid if c == 'CK'),
            'P4': sum(1 for c in grid if c == 'P4'),
        }
        for code, cap in (('C4', R['cap_C4']), ('CK', R['cap_CK']), ('P4', R['cap_P4'])):
            if counts[code] > cap:
                violations.append({
                    'nurse_name': name,
                    'nurse_index': n_idx,
                    'day': None,
                    'rule': f'cap_{code}',
                    'message': f'{name}: เวร {code} จำนวน {counts[code]} วัน เกินโควตาสูงสุด ({cap} วัน/เดือน)',
                    'severity': 'error'
                })

    # 5. Coverage per day
    for d in range(ndays):
        day_count = sum(1 for n in nurses if (n['grid'][d] == 'C4' or (R['ck_counts_as_day'] and n['grid'][d] == 'CK')))
        night_count = sum(1 for n in nurses if n['grid'][d] == 'P4')
        if day_count != R['need_C4']:
            diff = day_count - R['need_C4']
            severity = 'error' if day_count < R['need_C4'] else 'warning'
            violations.append({
                'nurse_name': None,
                'nurse_index': None,
                'day': d + 1,
                'rule': 'coverage_day',
                'message': f'วันที่ {d+1}: เวรเช้า {day_count} คน (เป้าหมาย {R["need_C4"]} คน, {"ขาด" if diff < 0 else "เกิน"} {abs(diff)} คน)',
                'severity': severity
            })
        if night_count != R['need_P4']:
            diff = night_count - R['need_P4']
            severity = 'error' if night_count < R['need_P4'] else 'warning'
            violations.append({
                'nurse_name': None,
                'nurse_index': None,
                'day': d + 1,
                'rule': 'coverage_night',
                'message': f'วันที่ {d+1}: เวรดึก {night_count} คน (เป้าหมาย {R["need_P4"]} คน, {"ขาด" if diff < 0 else "เกิน"} {abs(diff)} คน)',
                'severity': severity
            })


    # 6. Senior RN staffing per shift (Skill Mix)
    if R.get("require_senior_per_shift", True):
        senior_indices = [idx for idx, n in enumerate(nurses) if "senior" in str(n.get("level", "")).lower()]
        if senior_indices:
            for d in range(ndays):
                morn_seniors = sum(1 for idx in senior_indices if nurses[idx]["grid"][d] in ("C4", "CK"))
                night_seniors = sum(1 for idx in senior_indices if nurses[idx]["grid"][d] == "P4")
                if morn_seniors < 1:
                    violations.append({
                        "nurse_name": None,
                        "nurse_index": None,
                        "day": d + 1,
                        "rule": "senior_morning",
                        "message": f"วันที่ {d+1}: เวรเช้าไม่มี Senior RN ประจำการ (ควรมีอย่างน้อย 1 คน)",
                        "severity": "warning"
                    })
                if night_seniors < 1:
                    violations.append({
                        "nurse_name": None,
                        "nurse_index": None,
                        "day": d + 1,
                        "rule": "senior_night",
                        "message": f"วันที่ {d+1}: เวรดึกไม่มี Senior RN ประจำการ (ควรมีอย่างน้อย 1 คน)",
                        "severity": "warning"
                    })
    return violations

def solve_schedule(nurses: List[Dict[str, Any]],
                   days: List[int],
                   rules: Optional[Dict[str, Any]] = None,
                   prev_tail: Optional[Dict[str, List[str]]] = None,
                   locked_grid: Optional[List[List[bool]]] = None,
                   allow_ck: bool = True,
                   time_limit_sec: int = 30) -> Dict[str, Any]:
    R = dict(DEFAULT_RULES, **(rules or {}))
    prev_tail = prev_tail or {}
    N = len(nurses)
    D = len(days)

    try:
        from ortools.sat.python import cp_model
    except ImportError:
        return _solve_fallback(nurses, days, R, prev_tail, locked_grid)

    model = cp_model.CpModel()
    V = {}

    for i, n in enumerate(nurses):
        name = n.get('name', '')
        grid = n.get('grid', [])
        is_locked_row = locked_grid[i] if locked_grid and i < len(locked_grid) else None

        for d in range(D):
            code = norm_code(grid[d]) if d < len(grid) else None
            is_cell_locked = (is_locked_row[d] if is_locked_row is not None and d < len(is_locked_row) else False) or (code is not None)

            if is_cell_locked and code is not None:
                V[i, d] = {
                    'C4': int(code == 'C4'),
                    'P4': int(code == 'P4'),
                    'CK': int(code == 'CK'),
                    'TRAIN': int(code in ('TRAIN', 'c')),
                    'work': int(is_work(code)),
                    'plain': int(is_plain_off(code)),
                    'off': int(is_off(code)),
                }
            else:
                c = model.NewBoolVar(f'c_{i}_{d}')
                p = model.NewBoolVar(f'p_{i}_{d}')
                k = model.NewBoolVar(f'k_{i}_{d}') if allow_ck else 0

                shift_sum = c + p + (k if allow_ck else 0)
                model.Add(shift_sum <= 1)

                w = model.NewBoolVar(f'w_{i}_{d}')
                model.Add(w == shift_sum)

                o = model.NewBoolVar(f'o_{i}_{d}')
                model.Add(o + w == 1)

                V[i, d] = {
                    'C4': c,
                    'P4': p,
                    'CK': k,
                    'TRAIN': 0,
                    'work': w,
                    'plain': o,
                    'off': o,
                }

    def has_var(*vars_list):
        return any(not isinstance(v, int) for v in vars_list)

    def get_prev_code(idx, back_step):
        n_name = str(nurses[idx].get('name', '')).strip()
        tail = None
        for k, v in prev_tail.items():
            if str(k).strip() == n_name or str(k).strip() == str(nurses[idx].get('no', '')).strip():
                tail = v
                break
        tail = tail or []
        if len(tail) >= back_step:
            return norm_code(tail[-back_step])
        return None

    for i in range(N):
        seq = []
        for b in range(4, 0, -1):
            pcode = get_prev_code(i, b)
            seq.append({
                'work': int(is_work(pcode)),
                'off': int(is_off(pcode)),
                'plain': int(is_plain_off(pcode)),
                'C4': int(pcode == 'C4'),
                'CK': int(pcode == 'CK'),
                'P4': int(pcode == 'P4'),
            })
        seq.extend([V[i, d] for d in range(D)])

        # 1. Consecutive work <= max_consec_work
        window_size = R['max_consec_work'] + 1
        for t in range(len(seq) - window_size + 1):
            w_win = [seq[t + j]['work'] for j in range(window_size)]
            if has_var(*w_win):
                model.Add(sum(w_win) <= R['max_consec_work'])

        # 2. Reverse shift: No P4 followed immediately by C4 or CK
        for t in range(len(seq) - 1):
            p4_var = seq[t]['P4']
            day_shifts = [seq[t + 1]['C4'], seq[t + 1]['CK']]
            if has_var(p4_var, *day_shifts):
                model.Add(p4_var + sum(day_shifts) <= 1)

        # 3. Off run: 3rd+ consecutive off must be justified leave
        for t in range(len(seq) - 2):
            o1, o2, p3 = seq[t]['off'], seq[t + 1]['off'], seq[t + 2]['plain']
            if has_var(o1, o2, p3):
                model.Add(o1 + o2 + p3 <= 2)

        # 4. Monthly caps per nurse
        for code, cap in (('C4', R['cap_C4']), ('CK', R['cap_CK']), ('P4', R['cap_P4'])):
            code_vars = [V[i, d][code] for d in range(D)]
            if has_var(*code_vars):
                model.Add(sum(code_vars) <= cap)

    penalties = []

    # 1. Daily staffing requirements
    for d in range(D):
        day_workers = [V[i, d]['C4'] + (V[i, d]['CK'] if R['ck_counts_as_day'] else 0) for i in range(N)]
        night_workers = [V[i, d]['P4'] for i in range(N)]

        for workers, need, prefix in [(day_workers, R['need_C4'], 'day'), (night_workers, R['need_P4'], 'night')]:
            shortage = model.NewIntVar(0, N, f'short_{prefix}_{d}')
            overage = model.NewIntVar(0, N, f'over_{prefix}_{d}')
            model.Add(sum(workers) + shortage - overage == need)
            penalties.append(10000 * shortage)
            penalties.append(200 * overage)

    # 2. Workload fairness: Balance total hours
    total_hours = []
    for i in range(N):
        h = sum(12 * V[i, d]['C4'] + 12 * V[i, d]['P4'] + 16 * V[i, d]['CK'] for d in range(D))
        total_hours.append(h)

    max_h = model.NewIntVar(0, 1000, 'max_h')
    min_h = model.NewIntVar(0, 1000, 'min_h')
    for h in total_hours:
        model.Add(h <= max_h)
        model.Add(h >= min_h)
    penalties.append(10 * (max_h - min_h))

    # 3. CK usage penalty
    if allow_ck:
        for i in range(N):
            for d in range(D):
                if not isinstance(V[i, d]['CK'], int):
                    penalties.append(30 * V[i, d]['CK'])

    # 4. Ergonomics: Avoid single work shifts between offs
    for i in range(N):
        for d in range(1, D - 1):
            if has_var(V[i, d]['work']):
                iso = model.NewBoolVar(f'iso_{i}_{d}')
                model.Add(iso >= V[i, d]['work'] + V[i, d - 1]['off'] + V[i, d + 1]['off'] - 2)
                penalties.append(5 * iso)


    # 5. Senior RN per shift (Skill mix objective & penalty)
    if R.get("require_senior_per_shift", True):
        senior_indices = [idx for idx, n in enumerate(nurses) if "senior" in str(n.get("level", "")).lower()]
        if senior_indices:
            for d in range(D):
                morn_seniors = [V[idx, d]["C4"] + (V[idx, d]["CK"] if R["ck_counts_as_day"] else 0) for idx in senior_indices]
                night_seniors = [V[idx, d]["P4"] for idx in senior_indices]

                no_morn_senior = model.NewBoolVar(f"no_morn_sr_{d}")
                model.Add(sum(morn_seniors) == 0).OnlyEnforceIf(no_morn_senior)
                model.Add(sum(morn_seniors) >= 1).OnlyEnforceIf(no_morn_senior.Not())
                penalties.append(500 * no_morn_senior)

                no_night_senior = model.NewBoolVar(f"no_night_sr_{d}")
                model.Add(sum(night_seniors) == 0).OnlyEnforceIf(no_night_senior)
                model.Add(sum(night_seniors) >= 1).OnlyEnforceIf(no_night_senior.Not())
                penalties.append(500 * no_night_senior)

    model.Minimize(sum(penalties))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_sec
    solver.parameters.num_workers = 4
    status = solver.Solve(model)

    status_name = solver.StatusName(status)
    success = status in (cp_model.OPTIMAL, cp_model.FEASIBLE)

    if not success:
        return {
            'success': False,
            'status': status_name,
            'message': 'ไม่สามารถหาตารางที่สอดคล้องกับกฎทั้งหมดได้ (อาจมีวันลาที่ล็อกไว้มากเกินไป หรือโควตาเวรไม่เพียงพอ)',
            'violations': validate_schedule(nurses, D, R, prev_tail),
        }

    new_nurses = copy.deepcopy(nurses)
    newly_assigned_count = 0

    for i in range(N):
        for d in range(D):
            current_val = new_nurses[i]['grid'][d]
            cell_is_locked = (locked_grid[i][d] if (locked_grid and i < len(locked_grid) and d < len(locked_grid[i])) else (current_val is not None))
            if cell_is_locked and current_val is not None:
                continue

            chosen_code = '-'
            for code in ('C4', 'P4', 'CK'):
                var_val = V[i, d][code]
                if not isinstance(var_val, int) and solver.Value(var_val) == 1:
                    chosen_code = code
                    break
            new_nurses[i]['grid'][d] = chosen_code
            newly_assigned_count += 1

    violations = validate_schedule(new_nurses, D, R, prev_tail)

    return {
        'success': True,
        'status': status_name,
        'nurses': new_nurses,
        'days': days,
        'newly_assigned_count': newly_assigned_count,
        'violations': violations,
        'message': f'จัดเวรสำเร็จ ({status_name}) จัดลงตารางใหม่ {newly_assigned_count} ช่อง'
    }

def _solve_fallback(nurses, days, rules, prev_tail, locked_grid):
    new_nurses = copy.deepcopy(nurses)
    D = len(days)
    N = len(nurses)
    for d in range(D):
        for i in range(N):
            if new_nurses[i]['grid'][d] is None:
                new_nurses[i]['grid'][d] = '-'
    violations = validate_schedule(new_nurses, D, rules, prev_tail)
    return {
        'success': True,
        'status': 'HEURISTIC',
        'nurses': new_nurses,
        'days': days,
        'violations': violations,
        'message': 'จัดเวรด้วยโหมดสำรอง (ติดตั้ง OR-Tools เพื่อผลลัพธ์ที่ดีที่สุด)'
    }

def parse_excel_roster(file_path_or_bytes: Any) -> Dict[str, Any]:
    import openpyxl
    if isinstance(file_path_or_bytes, bytes):
        wb = openpyxl.load_workbook(io.BytesIO(file_path_or_bytes), data_only=False)
    else:
        wb = openpyxl.load_workbook(file_path_or_bytes, data_only=False)

    ws = wb.worksheets[0]
    title = str(ws.cell(1, 1).value or '').strip()
    month_name = 'ตุลาคม'
    year_be = '2569'
    ward_name = 'W6A'

    m_match = re.search(r'เดือน\s*\.{0,3}\s*([^\s\.]+)', title)
    if m_match: month_name = m_match.group(1)
    y_match = re.search(r'พ\.ศ\.\s*(\d{4})', title)
    if y_match: year_be = y_match.group(1)
    w_match = re.search(r'แผนก\s*([^\s\.]+)', title)
    if w_match: ward_name = w_match.group(1)

    DAY_COL0 = 6
    HEADER_ROW = 2
    FIRST_NURSE_ROW = 4

    days = []
    c = DAY_COL0
    while isinstance(ws.cell(HEADER_ROW, c).value, (int, float)):
        days.append(int(ws.cell(HEADER_ROW, c).value))
        c += 1

    D = len(days)
    nurses = []
    r = FIRST_NURSE_ROW

    while isinstance(ws.cell(r, 1).value, (int, float)):
        grid = []
        locked = []
        for d in range(D):
            raw_v = ws.cell(r, DAY_COL0 + d).value
            normalized = norm_code(raw_v)
            grid.append(normalized)
            locked.append(normalized is not None)

        nurse_obj = {
            'row': r,
            'no': int(ws.cell(r, 1).value),
            'code': str(ws.cell(r, 2).value or '').strip(),
            'name': str(ws.cell(r, 3).value or '').strip(),
            'fnf': str(ws.cell(r, 4).value or '').strip(),
            'level': str(ws.cell(r, 5).value or '').strip(),
            'grid': grid,
            'locked': locked,
        }
        nurses.append(nurse_obj)
        r += 1

    weekdays = []
    for d in range(D):
        w_val = str(ws.cell(3, DAY_COL0 + d).value or '').strip()
        weekdays.append(w_val)

    return {
        'title': title,
        'ward': ward_name,
        'month': month_name,
        'year': year_be,
        'days': days,
        'weekdays': weekdays,
        'nurses': nurses,
    }

def generate_excel_roster(roster_data: Dict[str, Any],
                          template_path: Optional[str] = None,
                          rules: Optional[Dict[str, Any]] = None,
                          prev_tail: Optional[Dict[str, List[str]]] = None) -> bytes:
    import openpyxl
    from openpyxl.styles import PatternFill, Alignment, Font
    from openpyxl.utils import get_column_letter

    R = dict(DEFAULT_RULES, **(rules or {}))
    nurses = roster_data.get('nurses', [])
    days = roster_data.get('days', list(range(1, 32)))
    D = len(days)
    DAY_COL0 = 6
    HEADER_ROW = 2
    FIRST_NURSE_ROW = 4

    if template_path and os.path.exists(template_path):
        wb = openpyxl.load_workbook(template_path)
        ws = wb.worksheets[0]
        if 'ตรวจสอบ' in wb.sheetnames:
            del wb['ตรวจสอบ']
    else:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = 'Sheet1'

    fills = {
        'C4': PatternFill('solid', fgColor='FFF2CC'),
        'CK': PatternFill('solid', fgColor='FCE4D6'),
        'P4': PatternFill('solid', fgColor='D9E1F2'),
        'X': PatternFill('solid', fgColor='F2F2F2'),
        'V': PatternFill('solid', fgColor='E2EFDA'),
        'HBD': PatternFill('solid', fgColor='F8CBAD'),
        'LK': PatternFill('solid', fgColor='FFF2CC'),
        'LP': PatternFill('solid', fgColor='F2DCDB'),
    }
    align_center = Alignment(horizontal='center', vertical='center')

    for i, n in enumerate(nurses):
        r = FIRST_NURSE_ROW + i
        ws.cell(r, 1, n.get('no', i + 1)).alignment = align_center
        ws.cell(r, 2, n.get('code', '')).alignment = align_center
        ws.cell(r, 3, n.get('name', ''))
        ws.cell(r, 4, n.get('fnf', '')).alignment = align_center
        ws.cell(r, 5, n.get('level', '')).alignment = align_center

        grid = n.get('grid', [])
        for d in range(D):
            code = grid[d] if d < len(grid) else None
            val_to_write = 'c' if code == 'TRAIN' else code
            cell = ws.cell(r, DAY_COL0 + d, val_to_write)
            cell.alignment = align_center
            if code in fills:
                cell.fill = fills[code]

        cnt = lambda *cs: sum(1 for x in grid if x in cs)
        col_c4 = DAY_COL0 + D
        col_ck = col_c4 + 1
        col_p4 = col_c4 + 2
        col_off = col_c4 + 3
        col_v = col_c4 + 4
        col_lp = col_c4 + 5
        col_total = col_c4 + 6

        ws.cell(HEADER_ROW, col_c4, 'C4').alignment = align_center
        ws.cell(HEADER_ROW, col_ck, 'CK').alignment = align_center
        ws.cell(HEADER_ROW, col_p4, 'P4').alignment = align_center
        ws.cell(HEADER_ROW, col_off, 'OFF').alignment = align_center
        ws.cell(HEADER_ROW, col_v, 'V').alignment = align_center
        ws.cell(HEADER_ROW, col_lp, 'LP').alignment = align_center
        ws.cell(HEADER_ROW, col_total, 'รวม').alignment = align_center

        ws.cell(r, col_c4, cnt('C4') or None).alignment = align_center
        ws.cell(r, col_ck, cnt('CK') or None).alignment = align_center
        ws.cell(r, col_p4, cnt('P4') or None).alignment = align_center
        ws.cell(r, col_off, cnt('X', '-', 'HBD', 'LK', 'H') or None).alignment = align_center
        ws.cell(r, col_v, cnt('V') or None).alignment = align_center
        ws.cell(r, col_lp, cnt('LP') or None).alignment = align_center

        l_c4 = get_column_letter(col_c4)
        l_ck = get_column_letter(col_ck)
        l_p4 = get_column_letter(col_p4)
        ws.cell(r, col_total, f'={l_c4}{r}*12+{l_ck}{r}*16+{l_p4}{r}*12').alignment = align_center

    staff_row_start = FIRST_NURSE_ROW + len(nurses)
    ws.cell(staff_row_start, 1, 'อัตรากำลัง')
    ws.cell(staff_row_start, 5, 'เช้า').alignment = align_center
    ws.cell(staff_row_start + 1, 5, 'บ่าย').alignment = align_center
    ws.cell(staff_row_start + 2, 5, 'ดึก').alignment = align_center

    for d in range(D):
        col = DAY_COL0 + d
        ws.cell(staff_row_start, col, R['need_C4']).alignment = align_center
        ws.cell(staff_row_start + 1, col, 3).alignment = align_center
        ws.cell(staff_row_start + 2, col, R['need_P4']).alignment = align_center

    ws_rep = wb.create_sheet('ตรวจสอบ')
    violations = validate_schedule(nurses, D, R, prev_tail)

    header_font = Font(bold=True, size=12)
    ws_rep.cell(1, 1, 'ผลการตรวจสอบกฎตารางเวร 12 ชั่วโมง').font = header_font
    if not violations:
        ws_rep.cell(2, 1, '✅ ผ่านทุกกฎตามเกณฑ์ของหอผู้ป่วย').font = Font(color='008000', bold=True)
    else:
        ws_rep.cell(2, 1, f'⚠️ พบข้อสังเกต/ข้อขัดแย้ง {len(violations)} รายการ:').font = Font(color='FF0000', bold=True)

    r_idx = 4
    for v in violations:
        ws_rep.cell(r_idx, 1, ('❌ ' if v['severity'] == 'error' else '⚠️ ') + v['message'])
        r_idx += 1

    r_idx += 1
    ws_rep.cell(r_idx, 1, 'วันที่').font = header_font
    ws_rep.cell(r_idx, 2, 'เวรเช้า (C4)').font = header_font
    ws_rep.cell(r_idx, 3, 'เวรพิเศษ (CK)').font = header_font
    ws_rep.cell(r_idx, 4, 'เวรดึก (P4)').font = header_font
    ws_rep.cell(r_idx, 5, 'รวมเช้า+CK').font = header_font
    ws_rep.cell(r_idx, 6, 'สถานะ').font = header_font

    r_idx += 1
    for d in range(D):
        c4_count = sum(1 for n in nurses if n['grid'][d] == 'C4')
        ck_count = sum(1 for n in nurses if n['grid'][d] == 'CK')
        p4_count = sum(1 for n in nurses if n['grid'][d] == 'P4')
        morn_tot = c4_count + (ck_count if R['ck_counts_as_day'] else 0)
        status_txt = 'ปกติ'
        if morn_tot != R['need_C4'] or p4_count != R['need_P4']:
            status_txt = 'ไม่ตรงเป้าหมาย'

        ws_rep.cell(r_idx, 1, d + 1).alignment = align_center
        ws_rep.cell(r_idx, 2, c4_count).alignment = align_center
        ws_rep.cell(r_idx, 3, ck_count).alignment = align_center
        ws_rep.cell(r_idx, 4, p4_count).alignment = align_center
        ws_rep.cell(r_idx, 5, morn_tot).alignment = align_center
        ws_rep.cell(r_idx, 6, status_txt).alignment = align_center
        r_idx += 1

    ws_rep.column_dimensions['A'].width = 60
    ws_rep.column_dimensions['F'].width = 20

    out_stream = io.BytesIO()
    wb.save(out_stream)
    return out_stream.getvalue()


def generate_nurse_ics(nurse: Dict[str, Any],
                       month_name: str,
                       year_be: str,
                       ward_name: str = "W6A") -> str:
    """Generate standard iCalendar (.ics) format for a single nurse."""
    from datetime import datetime, timedelta

    month_map = {
        "มกราคม": 1, "กุมภาพันธ์": 2, "มีนาคม": 3, "เมษายน": 4,
        "พฤษภาคม": 5, "มิถุนายน": 6, "กรกฎาคม": 7, "สิงหาคม": 8,
        "กันยายน": 9, "ตุลาคม": 10, "พฤศจิกายน": 11, "ธันวาคม": 12
    }
    month_num = month_map.get(month_name.strip(), 10)
    try:
        y_int = int(str(year_be).strip())
        year_ad = y_int - 543 if y_int > 2400 else y_int
    except Exception:
        year_ad = 2026

    nurse_name = nurse.get("name", "พยาบาล")
    grid = nurse.get("grid", [])

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Hospital Ward//Nurse Roster 12h//TH",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:ตารางเวร {nurse_name} ({month_name} {year_be})",
        "X-WR-TIMEZONE:Asia/Bangkok"
    ]

    for d_idx, code in enumerate(grid):
        if not code or code in ("-", "X"):
            continue

        day_num = d_idx + 1
        try:
            start_dt = None
            end_dt = None
            summary = ""
            desc = f"ตารางเวรพยาบาล แผนก {ward_name}\nพยาบาล: {nurse_name}"

            if code == "C4":
                start_dt = datetime(year_ad, month_num, day_num, 7, 0, 0)
                end_dt = datetime(year_ad, month_num, day_num, 19, 0, 0)
                summary = f"🏥 เวร C4 เช้า (07:00 - 19:00) - {ward_name}"
            elif code == "P4":
                start_dt = datetime(year_ad, month_num, day_num, 19, 0, 0)
                end_dt = start_dt + timedelta(hours=12)
                summary = f"🌙 เวร P4 ดึก (19:00 - 07:00) - {ward_name}"
            elif code == "CK":
                start_dt = datetime(year_ad, month_num, day_num, 7, 0, 0)
                end_dt = datetime(year_ad, month_num, day_num, 23, 0, 0)
                summary = f"⚡ เวรพิเศษ CK 16 ชม. (07:00 - 23:00) - {ward_name}"
            elif code == "V":
                start_dt = datetime(year_ad, month_num, day_num, 0, 0, 0)
                end_dt = datetime(year_ad, month_num, day_num, 23, 59, 59)
                summary = f"🌴 ลาพักร้อน (Vacation)"
            elif code == "HBD":
                start_dt = datetime(year_ad, month_num, day_num, 0, 0, 0)
                end_dt = datetime(year_ad, month_num, day_num, 23, 59, 59)
                summary = f"🎂 วันหยุดวันเกิด (HBD)"
            elif code in ("LK", "LP"):
                start_dt = datetime(year_ad, month_num, day_num, 0, 0, 0)
                end_dt = datetime(year_ad, month_num, day_num, 23, 59, 59)
                summary = f"📄 วันลา ({code})"
            elif code in ("TRAIN", "c"):
                start_dt = datetime(year_ad, month_num, day_num, 8, 0, 0)
                end_dt = datetime(year_ad, month_num, day_num, 16, 0, 0)
                summary = f"📚 อบรม/กิจกรรม (c)"

            if start_dt and end_dt:
                uid = f"roster-{year_ad}{month_num:02d}{day_num:02d}-{nurse.get('no', 1)}@ward.hospital"
                dtstamp = datetime.now().strftime("%Y%m%dT%H%M%SZ")
                dtstart = start_dt.strftime("%Y%m%dT%H%M%S")
                dtend = end_dt.strftime("%Y%m%dT%H%M%S")

                lines.extend([
                    "BEGIN:VEVENT",
                    f"UID:{uid}",
                    f"DTSTAMP:{dtstamp}",
                    f"DTSTART;TZID=Asia/Bangkok:{dtstart}",
                    f"DTEND;TZID=Asia/Bangkok:{dtend}",
                    f"SUMMARY:{summary}",
                    f"DESCRIPTION:{desc}",
                    f"LOCATION:แผนก {ward_name}",
                    "STATUS:CONFIRMED",
                    "BEGIN:VALARM",
                    "TRIGGER:-PT60M",
                    "ACTION:DISPLAY",
                    f"DESCRIPTION:เตือนขึ้นเวร {code}",
                    "END:VALARM",
                    "END:VEVENT"
                ])
        except Exception as e:
            continue

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines)
