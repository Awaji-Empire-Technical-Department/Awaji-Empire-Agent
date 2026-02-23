# common/survey_utils.py
# Why: parse_questions は JSON パース + データ整形のみの純粋関数。
#      import discord を使用せず、副作用もないため common/ に配置。
#      routes/survey.py と cogs/survey/logic.py の両方から利用される。
import json
from typing import Any, Dict, List


def parse_questions(json_str: str) -> List[Dict[str, Any]]:
    """アンケートの質問JSON文字列をパースし、安全なデータ構造にサニタイズする。

    Args:
        json_str: 質問データのJSON文字列
    Returns:
        サニタイズ済みの質問リスト。パース失敗時は空リスト。
    """
    try:
        data = json.loads(json_str)
        if not isinstance(data, list):
            return []
        sanitized = []
        for q in data:
            if not isinstance(q, dict):
                continue
            q['text'] = q.get('text', '(無題の質問)')
            q['type'] = q.get('type', 'text')
            q['options'] = q.get('options', [])
            sanitized.append(q)
        return sanitized
    except (json.JSONDecodeError, TypeError):
        return []
