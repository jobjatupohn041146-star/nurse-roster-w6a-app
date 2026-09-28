"""
api/export.py — Vercel Python Serverless Function
POST /api/export  →  generates Excel file, returns as binary download
"""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import roster_engine

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE_EXCEL_PATH = os.path.join(BASE_DIR, 'ตัวอย่างผลจัดเวร_ตค69.xlsx')

class handler(BaseHTTPRequestHandler):

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_POST(self):
        try:
            body = self._read_body()
            roster_data = body.get('roster_data', {})
            rules = body.get('rules', {})
            prev_tail = body.get('prev_tail', {})
            month = roster_data.get('month', 'เดือนนี้')

            template = SAMPLE_EXCEL_PATH if os.path.exists(SAMPLE_EXCEL_PATH) else None
            excel_bytes = roster_engine.generate_excel_roster(
                roster_data=roster_data,
                template_path=template,
                rules=rules,
                prev_tail=prev_tail
            )

            encoded_name = quote(f'ตารางเวร_{month}.xlsx')
            self.send_response(200)
            self._cors()
            self.send_header('Content-Type',
                'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            self.send_header('Content-Disposition',
                f"attachment; filename=nurse_roster.xlsx; filename*=UTF-8''{encoded_name}")
            self.send_header('Content-Length', str(len(excel_bytes)))
            self.end_headers()
            self.wfile.write(excel_bytes)
        except Exception as e:
            self._send_json({'error': f'Export error: {str(e)}'}, 500)

    def _read_body(self):
        length = int(self.headers.get('Content-Length', 0))
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length).decode('utf-8'))

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
        pass
