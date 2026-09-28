"""
api/nurse_ics.py — Vercel serverless function
POST /api/nurse-ics  →  generates iCalendar (.ics) file for individual nurse
"""
import json
import os
import sys
import base64
from urllib.parse import quote

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
        body = json.loads(request.body or '{}')
        nurse = body.get('nurse', {})
        month = body.get('month', 'ตุลาคม')
        year = body.get('year', '2569')
        ward = body.get('ward', 'W6A')

        ics_content = roster_engine.generate_nurse_ics(nurse, month, year, ward)
        ics_bytes = ics_content.encode('utf-8')

        nurse_name = nurse.get('name', 'nurse').strip()
        encoded_name = quote(f'ตารางเวร_{nurse_name}.ics')

        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'text/calendar; charset=utf-8',
                'Content-Disposition': f"attachment; filename=schedule.ics; filename*=UTF-8''{encoded_name}",
                'Access-Control-Allow-Origin': '*'
            },
            'body': base64.b64encode(ics_bytes).decode('utf-8'),
            'isBase64Encoded': True
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': f'ICS export error: {str(e)}'})
        }
