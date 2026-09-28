"""
api/initial.py — Vercel serverless function
GET /api/initial  →  returns parsed Excel data (or defaults)
"""
import json
import os
import sys

# Make roster_engine importable from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import roster_engine

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE_EXCEL_PATH = os.path.join(BASE_DIR, 'ตัวอย่างผลจัดเวร_ตค69.xlsx')

def handler(request):
    try:
        if os.path.exists(SAMPLE_EXCEL_PATH):
            data = roster_engine.parse_excel_roster(SAMPLE_EXCEL_PATH)
        else:
            data = {
                'ward': 'W6A',
                'month': 'ตุลาคม',
                'year': '2569',
                'days': list(range(1, 32)),
                'weekdays': ['พฤ', 'ศ', 'ส', 'อา', 'จ', 'อ', 'พ', 'พฤ', 'ศ', 'ส',
                             'อา', 'จ', 'อ', 'พ', 'พฤ', 'ศ', 'ส', 'อา', 'จ', 'อ',
                             'พ', 'พฤ', 'ศ', 'ส', 'อา', 'จ', 'อ', 'พ', 'พฤ', 'ศ', 'ส'],
                'nurses': []
            }

        default_tail = {
            'ฐานียา แสงงาม': ['C4', 'C4', 'P4', '-'],
            'ปิยาภรณ์ ดาราศร': ['X', 'X', 'C4', 'C4']
        }
        data['default_tail'] = default_tail

        body = json.dumps(data, ensure_ascii=False)
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json; charset=utf-8',
                'Access-Control-Allow-Origin': '*',
                'Cache-Control': 'no-cache'
            },
            'body': body
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': str(e)}, ensure_ascii=False)
        }
