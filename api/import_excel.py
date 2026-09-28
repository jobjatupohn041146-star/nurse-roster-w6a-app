"""
api/import_excel.py — Vercel Python Serverless Function
POST /api/import  →  parses uploaded Excel file, returns roster JSON
"""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import roster_engine

class handler(BaseHTTPRequestHandler):

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_POST(self):
        try:
            content_type = self.headers.get('Content-Type', '')
            if 'multipart/form-data' not in content_type:
                self._send_json({'error': 'Expected multipart/form-data'}, 400)
                return

            length = int(self.headers.get('Content-Length', 0))
            raw = self.rfile.read(length)

            boundary = content_type.split('boundary=')[1].strip().encode('utf-8')
            parts = raw.split(b'--' + boundary)
            file_bytes = None
            sep = bytes([13, 10, 13, 10])
            sep_lf = bytes([10, 10])

            for part in parts:
                if b'filename=' in part:
                    actual_sep = sep if sep in part else sep_lf
                    subparts = part.split(actual_sep, 1)
                    if len(subparts) == 2:
                        file_bytes = subparts[1].rstrip(bytes([13, 10, 45]))
                        break

            if not file_bytes:
                self._send_json({'error': 'No file found in upload'}, 400)
                return

            data = roster_engine.parse_excel_roster(file_bytes)
            self._send_json(data)
        except Exception as e:
            self._send_json({'error': f'Import error: {str(e)}'}, 500)

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
