# tests/test_survey_utils.py
# common/survey_utils.py のユニットテスト
# - parse_questions の正常系・異常系（不正JSON、空リスト等）
import sys
import os
from unittest import TestCase

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from common.survey_utils import parse_questions


class TestParseQuestions(TestCase):
    """parse_questions のテスト"""

    def test_valid_json(self):
        """正常なJSONをパースできる"""
        json_str = '[{"text": "Q1", "type": "text", "options": []}]'
        result = parse_questions(json_str)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['text'], 'Q1')
        self.assertEqual(result[0]['type'], 'text')

    def test_multiple_questions(self):
        """複数質問のパース"""
        json_str = '[{"text": "Q1", "type": "text"}, {"text": "Q2", "type": "radio", "options": ["A", "B"]}]'
        result = parse_questions(json_str)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[1]['options'], ['A', 'B'])

    def test_missing_fields_get_defaults(self):
        """必須フィールドが欠けている場合にデフォルト値が設定される"""
        json_str = '[{}]'
        result = parse_questions(json_str)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['text'], '(無題の質問)')
        self.assertEqual(result[0]['type'], 'text')
        self.assertEqual(result[0]['options'], [])

    def test_invalid_json_returns_empty(self):
        """不正なJSONの場合は空リストを返す"""
        result = parse_questions("not valid json")
        self.assertEqual(result, [])

    def test_empty_string_returns_empty(self):
        """空文字列の場合は空リストを返す"""
        result = parse_questions("")
        self.assertEqual(result, [])

    def test_non_list_json_returns_empty(self):
        """JSONオブジェクト（非リスト）の場合は空リストを返す"""
        result = parse_questions('{"text": "Q1"}')
        self.assertEqual(result, [])

    def test_non_dict_items_skipped(self):
        """リスト内の非辞書要素はスキップされる"""
        json_str = '[{"text": "Q1"}, "invalid", 123, null]'
        result = parse_questions(json_str)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['text'], 'Q1')

    def test_empty_list(self):
        """空リストのJSON"""
        result = parse_questions('[]')
        self.assertEqual(result, [])

    def test_none_input(self):
        """None入力の場合は空リストを返す（TypeError対策）"""
        # Why: json.loads(None) は TypeError を投げるが、
        #      except で捕捉して空リストを返す
        result = parse_questions(None)
        self.assertEqual(result, [])


if __name__ == '__main__':
    import unittest
    unittest.main()
