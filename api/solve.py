"""
api/solve.py — Vercel serverless function
POST /api/solve  →  runs CP-SAT solver and returns solved schedule
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import roster_engine

def handler(request):
    # Handle CORS preflight
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

        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json; charset=utf-8',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps(result, ensure_ascii=False)
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'success': False, 'message': f'Server Error: {str(e)}'})
        }
