"""
api/export.py — Vercel serverless function
POST /api/export  →  generates Excel file and returns as binary download
"""
import json
import os
import sys
import base64
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import roster_engine

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE_EXCEL_PATH = os.path.join(BASE_DIR, 'ตัวอย่างผลจัดเวร_ตค69.xlsx')

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
        body = json.loads(request.body or '{}')
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
        # Vercel requires base64-encoded body for binary responses
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                'Content-Disposition': f"attachment; filename=nurse_roster.xlsx; filename*=UTF-8''{encoded_name}",
                'Access-Control-Allow-Origin': '*'
            },
            'body': base64.b64encode(excel_bytes).decode('utf-8'),
            'isBase64Encoded': True
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': f'Export error: {str(e)}'})
        }
