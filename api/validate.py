"""
api/validate.py — Vercel serverless function
POST /api/validate  →  validates schedule and returns violations list
"""
import json
import os
import sys

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
        nurses = body.get('nurses', [])
        ndays = len(body.get('days', [])) or 31
        rules = body.get('rules', {})
        prev_tail = body.get('prev_tail', {})

        violations = roster_engine.validate_schedule(nurses, ndays, rules, prev_tail)
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json; charset=utf-8',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({'violations': violations}, ensure_ascii=False)
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'error': str(e)})
        }
