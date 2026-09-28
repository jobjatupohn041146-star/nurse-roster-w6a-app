"""
api/import_excel.py — Vercel serverless function
POST /api/import  →  parses uploaded Excel file and returns roster data
"""
import json
import os
import sys
import base64

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import roster_engine

def handler(request):
    if request.method == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'POST, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type'
            },
            'body': ''
        }

    try:
        content_type = request.headers.get('content-type', '')

        if 'multipart/form-data' in content_type:
            # Get raw body - Vercel may base64-encode binary
            raw_body = request.body
            if isinstance(raw_body, str):
                body_bytes = raw_body.encode('latin-1')
            else:
                body_bytes = raw_body

            boundary_str = content_type.split('boundary=')[1].strip()
            boundary = boundary_str.encode('utf-8')
            parts = body_bytes.split(b'--' + boundary)
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
                return {
                    'statusCode': 400,
                    'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                    'body': json.dumps({'error': 'No file found in upload'})
                }

            data = roster_engine.parse_excel_roster(file_bytes)
            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json; charset=utf-8',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps(data, ensure_ascii=False)
            }
        else:
            return {
                'statusCode': 400,
                'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
                'body': json.dumps({'error': 'Expected multipart/form-data'})
            }
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': f'Import error: {str(e)}'})
        }
