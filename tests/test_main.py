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

    def test_private_sources_formats_defense(self):
        # 1. 验证 private_sources 为纯 List 格式时正常兼容
        list_yaml = """
- name: priv1
  url: https://example.com/p1
- name: priv2
  url: https://example.com/p2
"""
        lp_data = yaml.safe_load(list_yaml) or {}
        lp_sources = lp_data if isinstance(lp_data, list) else (lp_data.get('sources') or [])
        self.assertEqual(len(lp_sources), 2)
        self.assertEqual(lp_sources[0]['name'], 'priv1')

        # 2. 验证 private_sources 为空文件 (None) 时正常防崩
        empty_data = yaml.safe_load("") or {}
        lp_sources_empty = empty_data if isinstance(empty_data, list) else (empty_data.get('sources') or [])
        self.assertEqual(lp_sources_empty, [])

        # 3. 验证 private_sources 为常规 Dict 格式
        dict_yaml = """
sources:
  - name: priv_dict
    url: https://example.com/dict
"""
        dict_data = yaml.safe_load(dict_yaml) or {}
        lp_sources_dict = dict_data if isinstance(dict_data, list) else (dict_data.get('sources') or [])
        self.assertEqual(len(lp_sources_dict), 1)
        self.assertEqual(lp_sources_dict[0]['name'], 'priv_dict')

if __name__ == '__main__':
    unittest.main()
