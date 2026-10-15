# -*- coding: utf-8 -*-
import unittest
from core.parser import Node
from core.processor import NodeProcessor

class TestProcessor(unittest.TestCase):
    def test_processor_filter_invalid_servers(self):
        processor = NodeProcessor()
        nodes = [
            Node({"name": "Node_Valid", "type": "vmess", "server": "1.2.3.4", "port": 443, "uuid": "a0000000-0000-0000-0000-000000000000"}),
            Node({"name": "Node_Loopback1", "type": "vmess", "server": "127.0.0.1", "port": 443, "uuid": "a0000000-0000-0000-0000-000000000000"}),
            Node({"name": "Node_Loopback2", "type": "vmess", "server": "0.0.0.0", "port": 443, "uuid": "a0000000-0000-0000-0000-000000000000"}),
            Node({"name": "Node_Localhost", "type": "vmess", "server": "localhost", "port": 443, "uuid": "a0000000-0000-0000-0000-000000000000"}),
            Node({"name": "Node_NoUUID", "type": "vmess", "server": "1.2.3.4", "port": 443}),
            Node({"name": "Node_BadPort", "type": "vmess", "server": "1.2.3.4", "port": -1, "uuid": "a0000000-0000-0000-0000-000000000000"}),
        ]
        valid = processor.filter_invalid(nodes)
        self.assertEqual(len(valid), 1)
        self.assertEqual(valid[0].name, "Node_Valid")

    def test_processor_deduplicate(self):
        processor = NodeProcessor()
        node1 = Node({"name": "NodeA", "type": "ss", "server": "example.com", "port": 8388, "cipher": "aes-256-gcm", "password": "pwd"})
        # 大小写域名与重复节点
        node2 = Node({"name": "NodeA_dup_upper", "type": "ss", "server": "EXAMPLE.COM", "port": 8388, "cipher": "aes-256-gcm", "password": "pwd"})
        node3 = Node({"name": "NodeB_diff_port", "type": "ss", "server": "example.com", "port": 8389, "cipher": "aes-256-gcm", "password": "pwd"})

        deduped = processor.deduplicate([node1, node2, node3])
        self.assertEqual(len(deduped), 2)

    def test_processor_flag_and_clean_names(self):
        processor = NodeProcessor()
        node_us = Node({"name": "US Fast Server", "type": "vmess", "server": "1.2.3.4", "port": 443, "uuid": "a0000000-0000-0000-0000-000000000000"})
        node_jp = Node({"name": "Tokyo Japan VIP", "type": "vmess", "server": "1.2.3.5", "port": 443, "uuid": "a0000000-0000-0000-0000-000000000000"})
        
        processed = processor.process_all([node_us, node_jp])
        self.assertEqual(len(processed), 2)
        self.assertTrue(processed[0].name.startswith("🇺🇸"))
        self.assertTrue(processed[1].name.startswith("🇯🇵"))

    def test_processor_strip_control_characters(self):
        processor = NodeProcessor()
        # 包含 \u200d, \u200e, \ufe0f, \x00 等控制字符
        bad_name = "US\u200d\u200e\ufe0f Fast\x00 Server\t"
        node = Node({"name": bad_name, "type": "vmess", "server": "1.2.3.4", "port": 443, "uuid": "a0000000-0000-0000-0000-000000000000"})
        processed = processor.process_all([node])
        self.assertEqual(len(processed), 1)
        # 控制字符应该被完全清除
        for bad_ch in ('\u200d', '\u200e', '\x00'):
            self.assertNotIn(bad_ch, processed[0].name)

    def test_processor_filter_notice_nodes(self):
        processor = NodeProcessor()
        node_ad1 = Node({"name": "飞机群-官方通知", "type": "vmess", "server": "1.2.3.4", "port": 443, "uuid": "a0000000-0000-0000-0000-000000000000"})
        node_ad2 = Node({"name": "节点不可用请更新订阅", "type": "vmess", "server": "1.2.3.5", "port": 443, "uuid": "a0000000-0000-0000-0000-000000000000"})
        node_ok = Node({"name": "US Normal Node", "type": "vmess", "server": "1.2.3.6", "port": 443, "uuid": "a0000000-0000-0000-0000-000000000000"})
        processed = processor.process_all([node_ad1, node_ad2, node_ok])
        self.assertEqual(len(processed), 1)
        self.assertIn("US Normal Node", processed[0].name)

    def test_processor_deep_sanitize_nested_attributes(self):
        processor = NodeProcessor()
        # 模拟包含 C1 控制字符 (0x9F, 0x87) 的深层嵌套字段 (如 Shadowsocks obfs host)
        node = Node({
            "name": "US Fast SS",
            "type": "ss",
            "server": "88.210.36.106",
            "port": 2377,
            "cipher": "chacha20-ietf-poly1305",
            "password": "pwd",
            "plugin": "obfs",
            "plugin-opts": {
                "mode": "tls",
                "host": "(Telegram\x9F\x87 @WangCai2)f6e348d:70852"
            }
        })
        processed = processor.process_all([node])
        self.assertEqual(len(processed), 1)
        host_val = processed[0].data.get("plugin-opts", {}).get("host", "")
        self.assertNotIn("\x9F", host_val)
        self.assertNotIn("\x87", host_val)
        self.assertIn("@WangCai2", host_val)

    def test_private_node_anti_overwrite_and_crown_prefix(self):
        processor = NodeProcessor()
        # 公共节点与私有节点具有相同 identity
        public_node = Node({"name": "HK Public Node", "type": "ss", "server": "1.2.3.4", "port": 8388, "cipher": "aes-128-gcm", "password": "pwd"})
        private_node = Node({"name": "HK VIP Private", "type": "ss", "server": "1.2.3.4", "port": 8388, "cipher": "aes-128-gcm", "password": "pwd"})
        private_node.data['_is_private'] = True

        # 验证去重时私有节点优先保留
        deduped = processor.deduplicate([public_node, private_node])
        self.assertEqual(len(deduped), 1)
        self.assertTrue(deduped[0].data.get('_is_private'))

        # 验证命名清洗后带有 👑 标识
        processed = processor.process_all([private_node])
        self.assertTrue(processed[0].name.startswith("👑"))

    def test_processor_ss_plugin_opts_none_safety(self):
        processor = NodeProcessor()
        # 1. plugin-opts 显式为 None 的 v2ray-plugin 节点
        node_v2ray_none = Node({
            "name": "SS v2ray plugin with None opts",
            "type": "ss",
            "server": "1.2.3.4",
            "port": 8388,
            "cipher": "aes-128-gcm",
            "password": "pwd",
            "plugin": "v2ray-plugin",
            "plugin-opts": None
        })
        # 2. plugin-opts 显式为 None 的 obfs 节点
        node_obfs_none = Node({
            "name": "SS obfs with None opts",
            "type": "ss",
            "server": "1.2.3.5",
            "port": 8388,
            "cipher": "aes-128-gcm",
            "password": "pwd",
            "plugin": "obfs",
            "plugin-opts": None
        })
        # 3. 字段类型严重损毁的异常节点（验证 per-node try-except 容灾保护）
        node_corrupted = Node({
            "name": "Corrupted Node",
            "type": "ss",
            "server": "1.2.3.6",
            "port": 8388,
            "cipher": "aes-128-gcm",
            "password": "pwd",
            "plugin": 12345,  # 非法非字符串类型
            "plugin-opts": "invalid_string_not_dict"
        })

        valid = processor.filter_invalid([node_v2ray_none, node_obfs_none, node_corrupted])
        # 必须全部稳定处理，绝不发生 AttributeError 崩溃
        self.assertGreaterEqual(len(valid), 2)
        # v2ray-plugin 节点的 plugin-opts 应被安全修复为字典
        self.assertIsInstance(valid[0].data.get('plugin-opts'), dict)
        self.assertEqual(valid[0].data['plugin-opts'].get('mode'), 'websocket')


if __name__ == "__main__":
    unittest.main()
