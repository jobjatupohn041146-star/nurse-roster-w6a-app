"""
api/solve.py — Vercel Python Serverless Function
POST /api/solve  →  runs CP-SAT solver, returns solved schedule
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
            body = self._read_body()
            result = roster_engine.solve_schedule(
                nurses=body.get('nurses', []),
                days=body.get('days', list(range(1, 32))),
                rules=body.get('rules', {}),
                prev_tail=body.get('prev_tail', {}),
                locked_grid=body.get('locked_grid', None),
                allow_ck=body.get('allow_ck', True),
                time_limit_sec=body.get('time_limit', 30)
            )
            self._send_json(result)
        except Exception as e:
            self._send_json({'success': False, 'message': f'Server Error: {str(e)}'}, 500)

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
