# -*- coding: utf-8 -*-
import unittest
from utils.constants import ALLOWED_PROTOCOLS, ALLOWED_TYPES, CANONICAL_PROTOCOLS
from core.fetcher import ALLOWED_PROTOCOLS as FETCHER_ALLOWED_PROTOCOLS
from core.processor import ALLOWED_TYPES as PROCESSOR_ALLOWED_TYPES
from core.parser import Node


class TestConstants(unittest.TestCase):
    def test_constants_definitions(self):
        # 1. 验证前缀元组包含常见 6 种协议 Scheme
        self.assertIsInstance(ALLOWED_PROTOCOLS, tuple)
        expected_protocols = {'vmess://', 'vless://', 'ss://', 'trojan://', 'hy2://', 'hysteria2://'}
        self.assertEqual(set(ALLOWED_PROTOCOLS), expected_protocols)

        # 2. 验证类型集合包含 6 种类型
        self.assertIsInstance(ALLOWED_TYPES, set)
        expected_types = {'vmess', 'vless', 'ss', 'trojan', 'hysteria2', 'hy2'}
        self.assertEqual(ALLOWED_TYPES, expected_types)

        # 3. 验证标准规范协议不含别名 (hy2 归一化为 hysteria2)
        self.assertIsInstance(CANONICAL_PROTOCOLS, set)
        expected_canonical = {'vmess', 'vless', 'ss', 'trojan', 'hysteria2'}
        self.assertEqual(CANONICAL_PROTOCOLS, expected_canonical)

    def test_constants_cross_module_consistency(self):
        # 验证各模块引用的常量与 constants 模块完全一致
        self.assertIs(FETCHER_ALLOWED_PROTOCOLS, ALLOWED_PROTOCOLS)
        self.assertIs(PROCESSOR_ALLOWED_TYPES, ALLOWED_TYPES)

    def test_parser_hy2_alias_normalization(self):
        # 验证 hy2:// 协议能被 parser 识别并归一化为 hysteria2
        hy2_url = "hy2://secret-auth@1.2.3.4:443?insecure=1&sni=hy2.example.com#Hy2_Test_Node"
        node = Node(hy2_url)
        self.assertEqual(node.type, "hysteria2")
        self.assertEqual(node.data.get("type"), "hysteria2")
        self.assertEqual(node.data.get("password"), "secret-auth")


if __name__ == "__main__":
    unittest.main()
