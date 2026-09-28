"""
api/nurse_ics.py — Vercel Python Serverless Function
POST /api/nurse-ics  →  generates iCalendar (.ics) for individual nurse
"""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import roster_engine

class handler(BaseHTTPRequestHandler):

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_POST(self):
        try:
            body = self._read_body()
            nurse = body.get('nurse', {})
            month = body.get('month', 'ตุลาคม')
            year = body.get('year', '2569')
            ward = body.get('ward', 'W6A')

            ics_content = roster_engine.generate_nurse_ics(nurse, month, year, ward)
            ics_bytes = ics_content.encode('utf-8')
            nurse_name = nurse.get('name', 'nurse').strip()
            encoded_name = quote(f'ตารางเวร_{nurse_name}.ics')

            self.send_response(200)
            self._cors()
            self.send_header('Content-Type', 'text/calendar; charset=utf-8')
            self.send_header('Content-Disposition',
                f"attachment; filename=schedule.ics; filename*=UTF-8''{encoded_name}")
            self.send_header('Content-Length', str(len(ics_bytes)))
            self.end_headers()
            self.wfile.write(ics_bytes)
        except Exception as e:
            self._send_json({'error': f'ICS export error: {str(e)}'}, 500)

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
