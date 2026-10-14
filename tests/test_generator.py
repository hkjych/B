import os
import yaml
import tempfile
import unittest
from core.parser import Node
from core.generator import Generator

class TestGenerator(unittest.TestCase):
    def setUp(self):
        self.template_data = {
            "mixed-port": 7890,
            "mode": "rule",
            "proxy-groups": [
                {"name": "🚀 选择代理", "type": "select", "proxies": ["♻️ 自动选择", "🗺️ 选择地区"]},
                {"name": "🗺️ 选择地区", "type": "select", "proxies": []},
                {"name": "♻️ 自动选择", "type": "fallback", "proxies": []},
                {"name": "🔰 延迟最低", "type": "url-test", "proxies": []},
                {"name": "✅ 手动选择", "type": "select", "proxies": []},
                {"name": "📢 订阅信息", "type": "select", "proxies": []}
            ],
            "rules": ["MATCH,🚀 选择代理"]
        }

    def test_generator_smart_pool_and_regions(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            template_path = os.path.join(tmpdir, "config.yaml")
            output_path = os.path.join(tmpdir, "output.yaml")
            with open(template_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(self.template_data, f)

            nodes = [
                # 中国节点 (应被排除出自动选择)
                Node({"name": "🇨🇳 CN_speednode_0001", "type": "ss", "server": "1.1.1.1", "port": 443}),
                # 荷兰节点 (带 speednode)
                Node({"name": "🇳🇱 NL_speednode_0004", "type": "ss", "server": "1.1.1.2", "port": 443}),
                Node({"name": "🇳🇱 NL_speednode_0005", "type": "ss", "server": "1.1.1.3", "port": 443}),
                # 日本节点 (带 MB/s)
                Node({"name": "🇯🇵JP_1|5.9MB/s", "type": "vmess", "server": "1.1.1.4", "port": 443}),
                # 瑞士节点 (只有 1 个，应该能独立建组)
                Node({"name": "🇨🇭 瑞士 #1", "type": "trojan", "server": "1.1.1.5", "port": 443}),
            ]

            generator = Generator(template_path)
            generator.generate(nodes, output_path)

            self.assertTrue(os.path.exists(output_path))
            with open(output_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f)

            groups = {g["name"]: g for g in cfg["proxy-groups"]}
            
            # 1. 验证 🇨🇳 是否被排除出 ♻️ 自动选择
            auto_proxies = groups["♻️ 自动选择"]["proxies"]
            for p in auto_proxies:
                self.assertFalse(p.startswith("🇨🇳"))
                self.assertFalse("⚠️" in p)

            # 2. 验证瑞士是否独立建组 (count > 0)
            region_menu = groups["🗺️ 选择地区"]["proxies"]
            self.assertIn("🇨🇭 瑞士", region_menu)

            # 3. 验证单地区内部组是否为 fallback 模式
            nl_group = groups.get("⚡ 自动选择 | 🇳🇱 荷兰")
            self.assertIsNotNone(nl_group)
            self.assertEqual(nl_group["type"], "fallback")

            # 4. 验证 📢 订阅信息 组存在且包含 5 个提示节点
            info_group = groups.get("📢 订阅信息")
            self.assertIsNotNone(info_group)
            self.assertEqual(len(info_group["proxies"]), 5)
            self.assertTrue(any("⚠️" in p for p in info_group["proxies"]))

            # 5. 验证 ✅ 手动选择 仅包含真实节点，去除非代理信息节点
            manual_proxies = groups["✅ 手动选择"]["proxies"]
            self.assertFalse(any("⚠️" in p for p in manual_proxies))
            self.assertIn("🇨🇭 瑞士 #1", manual_proxies)

    def test_generator_private_nodes_and_quota(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            template_path = os.path.join(tmpdir, "config.yaml")
            output_path = os.path.join(tmpdir, "output.yaml")
            with open(template_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(self.template_data, f)

            # 构造 15 个私有节点 (香港 10 个，日本 5 个) + 5 个公共节点
            nodes = []
            for i in range(10):
                n = Node({"name": f"👑 🇭🇰 私有香港 {i}", "type": "ss", "server": f"1.1.1.{i+10}", "port": 443})
                n.data['_is_private'] = True
                nodes.append(n)
            for i in range(5):
                n = Node({"name": f"👑 🇯🇵 私有日本 {i}", "type": "vmess", "server": f"2.2.2.{i+10}", "port": 443})
                n.data['_is_private'] = True
                nodes.append(n)
            for i in range(5):
                n = Node({"name": f"🇺🇸 公共美国 {i}", "type": "trojan", "server": f"3.3.3.{i+10}", "port": 443})
                nodes.append(n)

            pool_settings = {
                "core_regions": ["HK", "JP", "US", "SG"],
                "private": {
                    "max_total": 4,          # 限制私有最多 4 个
                    "core_per_region": 2,     # 核心地区每区 2 个
                    "other_per_region": 1
                },
                "public": {
                    "core_per_region": 3,
                    "other_per_region": 1
                },
                "min_pool_size": 5,
                "max_pool_size": 15
            }

            generator = Generator(template_path, pool_settings=pool_settings)
            generator.generate(nodes, output_path)

            with open(output_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f)

            groups = {g["name"]: g for g in cfg["proxy-groups"]}

            # 1. 验证动态生成了 👑 私有节点 策略组与子测速组
            self.assertIn("👑 私有节点", groups)
            self.assertIn("⚡ 自动选择 | 👑 私有节点", groups)
            # 专属组应包含全部 15 个私有节点
            self.assertEqual(len(groups["👑 私有节点"]["proxies"]), 16) # 1 个 auto + 15 个节点

            # 2. 验证 🚀 选择代理 首页排在第一位的是 👑 私有节点
            top_proxies = groups["🚀 选择代理"]["proxies"]
            self.assertEqual(top_proxies[0], "👑 私有节点")

            # 3. 验证 ♻️ 自动选择 中，私有节点数量严格被限制在 max_total (4个) 内
            auto_proxies = groups["♻️ 自动选择"]["proxies"]
            priv_in_auto = [p for p in auto_proxies if p.startswith("👑")]
            self.assertLessEqual(len(priv_in_auto), 4)

            # 4. 验证私有节点排在公共节点前面
            self.assertTrue(auto_proxies[0].startswith("👑"))

    def test_pool_settings_empty_and_special_values(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            template_path = os.path.join(tmpdir, "config.yaml")
            output_path = os.path.join(tmpdir, "output.yaml")
            with open(template_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(self.template_data, f)

            # 1 个私有节点，测试 max_total 为 0 (禁用)
            node_priv = Node({"name": "👑 🇭🇰 私有香港", "type": "ss", "server": "1.1.1.1", "port": 443})
            node_priv.data['_is_private'] = True
            node_pub = Node({"name": "🇯🇵 公共日本", "type": "ss", "server": "2.2.2.2", "port": 443})

            # max_total: 0 -> 私有节点不进自动选择
            gen_zero = Generator(template_path, pool_settings={"private": {"max_total": 0}})
            gen_zero.generate([node_priv, node_pub], output_path)

            with open(output_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f)
            groups = {g["name"]: g for g in cfg["proxy-groups"]}
            auto_proxies = groups["♻️ 自动选择"]["proxies"]
            self.assertNotIn("👑 🇭🇰 私有香港", auto_proxies)
            self.assertIn("🇯🇵 公共日本", auto_proxies)

    def test_generator_safedumper_quotes_and_deep_sanitize(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            template_path = os.path.join(tmpdir, "config.yaml")
            output_path = os.path.join(tmpdir, "output.yaml")
            with open(template_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(self.template_data, f)

            # 包含纯数字密码、布尔伪装字符串以及深层控制字符
            node = Node({
                "name": "Special_Quote_Node",
                "type": "ss",
                "server": "1.2.3.4",
                "port": 443,
                "cipher": "aes-128-gcm",
                "password": "true",
                "plugin": "obfs",
                "plugin-opts": {
                    "mode": "tls",
                    "host": "evil\x9f\x87host.com"
                }
            })

            generator = Generator(template_path)
            generator.generate([node], output_path)

            with open(output_path, "r", encoding="utf-8") as f:
                raw_yaml = f.read()

            # 1. 验证 password: "true" 带有双引号，防止被 Go 解析为布尔值
            self.assertIn('password: "true"', raw_yaml)
            # 2. 验证控制字符被完全清洗
            self.assertNotIn("\x9f", raw_yaml)
            self.assertNotIn("\x87", raw_yaml)
            self.assertIn("evilhost.com", raw_yaml)

if __name__ == "__main__":
    unittest.main()
