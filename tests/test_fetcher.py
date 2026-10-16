import unittest
from core.fetcher import Fetcher

class TestFetcher(unittest.TestCase):
    def setUp(self):
        self.fetcher = Fetcher()

    def test_parse_content_uppercase_protocols(self):
        content = """
VMESS://eyJhZGQiOiIxLjIuMy40IiwicG9ydCI6NDQzLCJpZCI6ImEwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMCIsInBzIjoiVXBwZXJWbWVzcyJ9
HY2://pwd123@1.2.3.4:443#UpperHy2
VLESS://a0000000-0000-0000-0000-000000000000@1.2.3.4:443#UpperVless
SS://YWVzLTI1Ni1nY206cHdkMTIz@1.2.3.4:8388#UpperSS
"""
        nodes = self.fetcher.parse_content(content)
        self.assertEqual(len(nodes), 4)
        types = {n.type for n in nodes}
        self.assertIn("vmess", types)
        self.assertIn("hysteria2", types)
        self.assertIn("vless", types)
        self.assertIn("ss", types)

    def test_parse_content_html_skip(self):
        html_content = "<!DOCTYPE html><html><body>vmess://invalid</body></html>"
        nodes = self.fetcher.parse_content(html_content)
        self.assertEqual(len(nodes), 0)

    def test_parse_content_yaml(self):
        yaml_content = """
proxies:
  - name: YAML_Node_1
    type: vmess
    server: 1.2.3.4
    port: 443
    uuid: a0000000-0000-0000-0000-000000000000
"""
        nodes = self.fetcher.parse_content(yaml_content)
        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0].name, "YAML_Node_1")

    def test_fetcher_timeout_config(self):
        f = Fetcher(timeout=12.0, connect_timeout=4.0)
        self.assertEqual(f.timeout, 12.0)
        self.assertEqual(f.connect_timeout, 4.0)
        self.assertEqual(f.req_timeout.connect, 4.0)
        self.assertEqual(f.req_timeout.read, 12.0)

    def test_recursive_fetch_semaphore_no_deadlock(self):
        import asyncio
        from unittest.mock import AsyncMock, MagicMock

        async def run_test():
            mock_client = MagicMock()
            async def mock_get(url, **kwargs):
                resp = MagicMock()
                resp.status_code = 200
                if "parent" in str(url):
                    resp.content = b"https://example.com/sub1\nhttps://example.com/sub2"
                elif "sub1" in str(url):
                    resp.content = b"vmess://eyJhZGQiOiIxLjEuMS4xIiwicG9ydCI6NDQzLCJpZCI6ImEwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMCIsInBzIjoiU3ViMSJ9"
                elif "sub2" in str(url):
                    resp.content = b"vmess://eyJhZGQiOiIyLjIuMi4yIiwicG9ydCI6NDQzLCJpZCI6ImEwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMCIsInBzIjoiU3ViMiJ9"
                else:
                    resp.status_code = 404
                    resp.content = b""
                return resp

            mock_client.get = AsyncMock(side_effect=mock_get)
            # max_concurrent=1: 以前如果外层占住信号量，递归子任务获取信号量时必定死锁卡死
            async with Fetcher(max_concurrent=1, client=mock_client) as f:
                nodes = await asyncio.wait_for(f.fetch_nodes("*https://example.com/parent"), timeout=2.0)
                self.assertEqual(len(nodes), 2)
                self.assertEqual({n.name for n in nodes}, {"Sub1", "Sub2"})

        asyncio.run(run_test())


if __name__ == "__main__":
    unittest.main()
