"""
api/initial.py — Vercel Python Serverless Function
GET /api/initial  →  parses Excel roster and returns JSON data
"""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import roster_engine

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE_EXCEL_PATH = os.path.join(BASE_DIR, 'ตัวอย่างผลจัดเวร_ตค69.xlsx')

class handler(BaseHTTPRequestHandler):

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_GET(self):
        try:
            if os.path.exists(SAMPLE_EXCEL_PATH):
                data = roster_engine.parse_excel_roster(SAMPLE_EXCEL_PATH)
            else:
                data = {
                    'ward': 'W6A',
                    'month': 'ตุลาคม',
                    'year': '2569',
                    'days': list(range(1, 32)),
                    'weekdays': ['พฤ','ศ','ส','อา','จ','อ','พ','พฤ','ศ','ส',
                                 'อา','จ','อ','พ','พฤ','ศ','ส','อา','จ','อ',
                                 'พ','พฤ','ศ','ส','อา','จ','อ','พ','พฤ','ศ','ส'],
                    'nurses': []
                }
            data['default_tail'] = {
                'ฐานียา แสงงาม': ['C4', 'C4', 'P4', '-'],
                'ปิยาภรณ์ ดาราศร': ['X', 'X', 'C4', 'C4']
            }
            self._send_json(data)
        except Exception as e:
            self._send_json({'error': str(e)}, 500)

    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def _send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self._cors()
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass  # suppress access logs
