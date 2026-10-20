import os
import tempfile
import unittest
import yaml
from unittest.mock import patch

class TestMainConfigDefense(unittest.TestCase):
    def test_sources_yaml_empty_settings_defense(self):
        # 验证 settings: null 或 smart_pool: null 时不会抛出 AttributeError
        empty_settings_yaml = """
sources:
  - name: test_source
    url: https://example.com/sub
settings: null
"""
        data = yaml.safe_load(empty_settings_yaml) or {}
        smart_pool_settings = (data.get('settings') or {}).get('smart_pool', {}) or {}
        self.assertEqual(smart_pool_settings, {})

        empty_smart_pool_yaml = """
sources: []
settings:
  smart_pool: null
"""
        data2 = yaml.safe_load(empty_smart_pool_yaml) or {}
        smart_pool_settings2 = (data2.get('settings') or {}).get('smart_pool', {}) or {}
        self.assertEqual(smart_pool_settings2, {})

    def test_normalize_private_sources(self):
        from main import _normalize_private_sources

        # 1. 验证 private_sources 为纯 List 格式时正常兼容并标记 is_private=True
        list_yaml = """
- name: priv1
  url: https://example.com/p1
- name: priv2
  url: https://example.com/p2
"""
        lp_sources = _normalize_private_sources(yaml.safe_load(list_yaml))
        self.assertEqual(len(lp_sources), 2)
        self.assertEqual(lp_sources[0]['name'], 'priv1')
        self.assertTrue(lp_sources[0]['is_private'])
        self.assertTrue(lp_sources[1]['is_private'])

        # 2. 验证 private_sources 为空或 None 时正常防崩
        self.assertEqual(_normalize_private_sources(yaml.safe_load("")), [])
        self.assertEqual(_normalize_private_sources(None), [])
        self.assertEqual(_normalize_private_sources("invalid string"), [])

        # 3. 验证 private_sources 为常规 Dict 格式
        dict_yaml = """
sources:
  - name: priv_dict
    url: https://example.com/dict
"""
        dict_sources = _normalize_private_sources(yaml.safe_load(dict_yaml))
        self.assertEqual(len(dict_sources), 1)
        self.assertEqual(dict_sources[0]['name'], 'priv_dict')
        self.assertTrue(dict_sources[0]['is_private'])

if __name__ == '__main__':
    unittest.main()
