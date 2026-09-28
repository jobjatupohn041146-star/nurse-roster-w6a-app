#!/usr/bin/env python3
"""
app.py
Web server for 12-Hour Nurse Rostering (W6A Ward).
Runs on standard library http.server + roster_engine.
"""

import os
import sys
import json
import io
import mimetypes
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import roster_engine

PORT = 8000
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, 'static')
SAMPLE_EXCEL_PATH = os.path.join(BASE_DIR, 'ตัวอย่างผลจัดเวร_ตค69.xlsx')

class RosterHandler(BaseHTTPRequestHandler):
    def send_cors_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_cors_headers()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path in ('/', '/index.html'):
            self.serve_file(os.path.join(STATIC_DIR, 'index.html'), 'text/html; charset=utf-8')
        elif path.startswith('/static/'):
            rel_path = path[len('/static/'):]
            file_path = os.path.join(STATIC_DIR, rel_path)
            mime_type, _ = mimetypes.guess_type(file_path)
            self.serve_file(file_path, mime_type or 'application/octet-stream')
        elif path == '/api/initial':
            self.handle_api_initial()
        elif path == '/api/rules':
            self.send_json(roster_engine.DEFAULT_RULES)
        else:
            self.send_error(404, 'Not Found')

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == '/api/solve':
            self.handle_api_solve()
        elif path == '/api/validate':
            self.handle_api_validate()
        elif path == '/api/import':
            self.handle_api_import()
        elif path == '/api/export':
            self.handle_api_export()
        elif path == '/api/save-excel':
            self.handle_api_save_excel()
        elif path == '/api/nurse-ics':
            self.handle_api_nurse_ics()
        else:
            self.send_error(404, 'Not Found')

    def serve_file(self, full_path, content_type):
        if not os.path.exists(full_path):
            self.send_error(404, 'File Not Found')
            return
        try:
            with open(full_path, 'rb') as f:
                data = f.read()
            self.send_response(200)
            self.send_cors_headers()
            self.send_header('Content-Type', content_type)
            self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
            self.send_header('Pragma', 'no-cache')
            self.send_header('Expires', '0')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            self.send_error(500, f'Error reading file: {str(e)}')

    def send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_cors_headers()
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json_body(self):
        length = int(self.headers.get('Content-Length', 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length).decode('utf-8')
        return json.loads(raw)

    def handle_api_initial(self):
        try:
            if os.path.exists(SAMPLE_EXCEL_PATH):
                data = roster_engine.parse_excel_roster(SAMPLE_EXCEL_PATH)
            else:
                data = {
                    'ward': 'W6A', 'month': 'ตุลาคม', 'year': '2569',
                    'days': list(range(1, 32)),
                    'weekdays': ['พฤ', 'ศ', 'ส', 'อา'] * 8,
                    'nurses': []
                }
            # Add sample tail shifts
            default_tail = {
                'ฐานียา แสงงาม': ['C4', 'C4', 'P4', '-'],
                'ปิยาภรณ์ ดาราศร': ['X', 'X', 'C4', 'C4']
            }
            data['default_tail'] = default_tail
            self.send_json(data)
        except Exception as e:
            self.send_json({'error': str(e)}, status=500)

    def handle_api_solve(self):
        try:
            body = self.read_json_body()
            nurses = body.get('nurses', [])
            days = body.get('days', list(range(1, 32)))
            rules = body.get('rules', {})
            prev_tail = body.get('prev_tail', {})
            locked_grid = body.get('locked_grid', None)
            allow_ck = body.get('allow_ck', True)
            time_limit = body.get('time_limit', 30)

            result = roster_engine.solve_schedule(
                nurses=nurses,
                days=days,
                rules=rules,
                prev_tail=prev_tail,
                locked_grid=locked_grid,
                allow_ck=allow_ck,
                time_limit_sec=time_limit
            )
            self.send_json(result)
        except Exception as e:
            self.send_json({'success': False, 'message': f'Server Error: {str(e)}'}, status=500)

    def handle_api_validate(self):
        try:
            body = self.read_json_body()
            nurses = body.get('nurses', [])
            ndays = len(body.get('days', [])) or 31
            rules = body.get('rules', {})
            prev_tail = body.get('prev_tail', {})

            violations = roster_engine.validate_schedule(nurses, ndays, rules, prev_tail)
            self.send_json({'violations': violations})
        except Exception as e:
            self.send_json({'error': str(e)}, status=500)

    def handle_api_import(self):
        try:
            content_type = self.headers.get('Content-Type', '')
            if 'multipart/form-data' in content_type:
                length = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(length)
                boundary = content_type.split('boundary=')[1].strip().encode('utf-8')
                parts = body.split(b'--' + boundary)
                file_bytes = None
                sep_crlf = bytes([13, 10, 13, 10])
                sep_lf = bytes([10, 10])
                sep = sep_crlf if sep_crlf in body else sep_lf
                for part in parts:
                    if b'filename=' in part:
                        subparts = part.split(sep, 1)
                        if len(subparts) == 2:
                            file_bytes = subparts[1].rstrip(bytes([13, 10, 45]))
                            break
                if not file_bytes:
                    self.send_json({'error': 'No file found in upload'}, status=400)
                    return
                data = roster_engine.parse_excel_roster(file_bytes)
                self.send_json(data)
            else:
                self.send_json({'error': 'Expected multipart/form-data'}, status=400)
        except Exception as e:
            self.send_json({'error': f'Import error: {str(e)}'}, status=500)

    def handle_api_export(self):
        try:
            body = self.read_json_body()
            roster_data = body.get('roster_data', {})
            rules = body.get('rules', {})
            prev_tail = body.get('prev_tail', {})
            month = roster_data.get('month', 'เดือนนี้')

            excel_bytes = roster_engine.generate_excel_roster(
                roster_data=roster_data,
                template_path=SAMPLE_EXCEL_PATH if os.path.exists(SAMPLE_EXCEL_PATH) else None,
                rules=rules,
                prev_tail=prev_tail
            )

            from urllib.parse import quote
            safe_name = f'nurse_roster_{month}.xlsx'
            encoded_name = quote(f'ตารางเวร_{month}.xlsx')
            self.send_response(200)
            self.send_cors_headers()
            self.send_header('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            self.send_header('Content-Disposition', f"attachment; filename=nurse_roster.xlsx; filename*=UTF-8''{encoded_name}")
            self.send_header('Content-Length', str(len(excel_bytes)))
            self.end_headers()
            self.wfile.write(excel_bytes)
        except Exception as e:
            self.send_json({'error': f'Export error: {str(e)}'}, status=500)

    def handle_api_save_excel(self):
        try:
            body = self.read_json_body()
            roster_data = body.get('roster_data', {})
            rules = body.get('rules', {})
            prev_tail = body.get('prev_tail', {})
            output_name = body.get('filename', 'ตารางเวร_จัดสำเร็จ.xlsx')

            excel_bytes = roster_engine.generate_excel_roster(
                roster_data=roster_data,
                template_path=SAMPLE_EXCEL_PATH if os.path.exists(SAMPLE_EXCEL_PATH) else None,
                rules=rules,
                prev_tail=prev_tail
            )

            target_path = os.path.join(BASE_DIR, output_name)
            with open(target_path, 'wb') as f:
                f.write(excel_bytes)

            self.send_json({
                'success': True,
                'path': target_path,
                'filename': output_name,
                'message': f'บันทึกไฟล์สำเร็จ: {output_name}'
            })
        except Exception as e:
            self.send_json({'error': f'Save error: {str(e)}'}, status=500)


    def handle_api_nurse_ics(self):
        try:
            from urllib.parse import quote
            body = self.read_json_body()
            nurse = body.get('nurse', {})
            month = body.get('month', 'ตุลาคม')
            year = body.get('year', '2569')
            ward = body.get('ward', 'W6A')

            ics_content = roster_engine.generate_nurse_ics(nurse, month, year, ward)
            ics_bytes = ics_content.encode('utf-8')

            nurse_name = nurse.get('name', 'nurse').strip()
            encoded_name = quote(f"ตารางเวร_{nurse_name}.ics")

            self.send_response(200)
            self.send_cors_headers()
            self.send_header('Content-Type', 'text/calendar; charset=utf-8')
            self.send_header('Content-Disposition', f"attachment; filename=schedule.ics; filename*=UTF-8''{encoded_name}")
            self.send_header('Content-Length', str(len(ics_bytes)))
            self.end_headers()
            self.wfile.write(ics_bytes)
        except Exception as e:
            self.send_json({'error': f'ICS export error: {str(e)}'}, status=500)


def run_server(port=PORT):
    server = HTTPServer(('0.0.0.0', port), RosterHandler)
    print(f'Server running at http://localhost:{port}/')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('Shutting down server...')
        server.server_close()

if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else PORT
    run_server(port)
