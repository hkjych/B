import unittest
from core.fetcher import Fetcher, parallel_fetch
from core.parser import Node

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

    def test_parse_content_base64_protocol_filter_ignores_ads_and_text(self):
        import base64
        # 模拟 Base64 订阅中夹杂 Telegram 广告、公告说明、HTTP 链接及其他非代理杂质文本
        raw_text = """
https://t.me/some_channel_advertisement
公告：本订阅节点每小时自动更新一次
vmess://eyJhZGQiOiIxLjIuMy40IiwicG9ydCI6NDQzLCJpZCI6ImEwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMCIsInBzIjoiVm1lc3NOb2RlIn0=
STATUS: OK
ss://YWVzLTI1Ni1nY206cHdkMTIz@1.2.3.4:8388#SSNode
http://example.com/not_a_proxy
hysteria2://pwd@5.6.7.8:443#Hy2Node
联系作者：admin@example.com
"""
        b64_content = base64.b64encode(raw_text.strip().encode("utf-8")).decode("utf-8")
        nodes = self.fetcher.parse_content(b64_content)
        # 应仅解析出 3 个合法协议节点 (vmess, ss, hysteria2)，其余 5 行非代理杂质文本全部被拦截过滤
        self.assertEqual(len(nodes), 3)
        names = {n.name for n in nodes}
        self.assertEqual(names, {"VmessNode", "SSNode", "Hy2Node"})

    def test_fetcher_timeout_config(self):
        f = Fetcher(timeout=12.0, connect_timeout=4.0)
        self.assertEqual(f.timeout, 12.0)
        self.assertEqual(f.connect_timeout, 4.0)
        self.assertEqual(f.req_timeout.connect, 4.0)
        self.assertEqual(f.req_timeout.read, 12.0)

    def test_recursive_fetch_semaphore_no_deadlock(self):
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch

        async def run_test():
            from contextlib import asynccontextmanager
            mock_client = MagicMock()
            async def mock_get(url, **kwargs):
                resp = MagicMock()
                resp.status_code = 200
                resp.headers = {}
                if "parent" in str(url):
                    body = b"https://example.com/sub1\nhttps://example.com/sub2"
                elif "sub1" in str(url):
                    body = b"vmess://eyJhZGQiOiIxLjEuMS4xIiwicG9ydCI6NDQzLCJpZCI6ImEwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMCIsInBzIjoiU3ViMSJ9"
                elif "sub2" in str(url):
                    body = b"vmess://eyJhZGQiOiIyLjIuMi4yIiwicG9ydCI6NDQzLCJpZCI6ImEwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMCIsInBzIjoiU3ViMiJ9"
                else:
                    resp.status_code = 404
                    body = b""
                async def chunks():
                    yield body
                resp.aiter_bytes = chunks
                return resp

            @asynccontextmanager
            async def mock_stream(method, url, **kwargs):
                yield await mock_get(url, **kwargs)
            mock_client.stream = mock_stream
            # 模拟 DNS 通过，以便专注测试抓取及信号量行为
            with patch.object(Fetcher, '_validate_fetch_url', new=AsyncMock()):
                async with Fetcher(max_concurrent=1, client=mock_client) as f:
                    nodes = await asyncio.wait_for(f.fetch_nodes("*https://example.com/parent"), timeout=2.0)
                self.assertEqual(len(nodes), 2)
                self.assertEqual({n.name for n in nodes}, {"Sub1", "Sub2"})

        asyncio.run(run_test())

    def test_parse_content_html_head_slice(self):
        f = Fetcher()
        # 大文本开头是 HTML 标签，后续带有很多普通字符
        html_doc = "<!DOCTYPE html><html><body>" + "x" * 10000 + "</body></html>"
        nodes = f.parse_content(html_doc)
        self.assertEqual(len(nodes), 0)

    def test_parse_content_skip_yaml_for_plain_urls(self):
        f = Fetcher()
        # 纯 URL 列表不包含 proxies: / Proxy: / payload: / server: 等，应直接进入 URL 逐行解析
        content = "vmess://eyJhZGQiOiIxLjEuMS4xIiwicG9ydCI6NDQzLCJpZCI6ImEwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMCIsInBzIjoiVVJMMTEifQ\n"
        nodes = f.parse_content(content)
        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0].name, "URL11")

    def test_fetcher_mirror_fallback(self):
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch

        async def run_test():
            from contextlib import asynccontextmanager
            mock_client = MagicMock()
            attempts = []
            async def mock_get(url, **kwargs):
                attempts.append(str(url))
                resp = MagicMock()
                resp.headers = {}
                if "raw.githubusercontent.com" in str(url):
                    resp.status_code = 500
                    body = b"Internal Server Error"
                else:
                    resp.status_code = 200
                    body = b"vmess://eyJhZGQiOiIxLjEuMS4xIiwicG9ydCI6NDQzLCJpZCI6ImEwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMCIsInBzIjoiTWlycm9yTm9kZSJ9"
                async def chunks():
                    yield body
                resp.aiter_bytes = chunks
                return resp

            @asynccontextmanager
            async def mock_stream(method, url, **kwargs):
                yield await mock_get(url, **kwargs)
            mock_client.stream = mock_stream
            with patch.object(Fetcher, '_validate_fetch_url', new=AsyncMock()):
                async with Fetcher(client=mock_client) as f:
                    nodes = await f.fetch_nodes("https://raw.githubusercontent.com/user/repo/master/sub.txt")
                self.assertEqual(len(nodes), 1)
                self.assertEqual(nodes[0].name, "MirrorNode")
                self.assertGreaterEqual(len(attempts), 2)

        asyncio.run(run_test())

    def test_fetch_url_rejects_non_https_and_private_addresses(self):
        import asyncio
        from unittest.mock import AsyncMock, patch

        async def run_test():
            f = Fetcher()
            with self.assertRaisesRegex(ValueError, "HTTPS"):
                await f._validate_fetch_url("http://example.com/sub")

            with patch("core.fetcher.asyncio.get_running_loop") as get_loop:
                loop = get_loop.return_value
                loop.getaddrinfo = AsyncMock(return_value=[(None, None, None, None, ("10.2.3.4", 443))])
                with self.assertRaisesRegex(ValueError, "non-public"):
                    await f._validate_fetch_url("https://private.example/sub")

        asyncio.run(run_test())

    def test_redirect_target_is_validated(self):
        import asyncio
        from contextlib import asynccontextmanager
        from unittest.mock import AsyncMock, MagicMock, patch

        async def run_test():
            client = MagicMock()
            response = MagicMock(status_code=302, headers={"location": "http://127.0.0.1/admin"})
            @asynccontextmanager
            async def stream(method, url, **kwargs):
                yield response
            client.stream = stream
            f = Fetcher(client=client)
            async def validate(url):
                if url.startswith("http://"):
                    raise ValueError("only credential-free HTTPS URLs are allowed")
            with patch.object(f, "_validate_fetch_url", new=AsyncMock(side_effect=validate)) as validate_mock:
                with self.assertRaisesRegex(ValueError, "HTTPS"):
                    await f._request_limited(client, "https://public.example/start")
                self.assertEqual(validate_mock.await_count, 2)
                self.assertEqual(validate_mock.await_args_list[1].args[0], "http://127.0.0.1/admin")

        asyncio.run(run_test())

    def test_response_size_limit_enforced_while_streaming(self):
        import asyncio
        from contextlib import asynccontextmanager
        from unittest.mock import MagicMock, patch
        from core.fetcher import MAX_RESPONSE_BYTES

        async def run_test():
            client = MagicMock()
            response = MagicMock(status_code=200, headers={})
            async def chunks():
                yield b"x" * (MAX_RESPONSE_BYTES + 1)
            response.aiter_bytes = chunks
            @asynccontextmanager
            async def stream(method, url, **kwargs):
                yield response
            client.stream = stream
            f = Fetcher(client=client)
            with patch.object(f, "_validate_fetch_url", new=AsyncMock()):
                with self.assertRaisesRegex(ValueError, "byte limit"):
                    await f._request_limited(client, "https://public.example/sub")

        from unittest.mock import AsyncMock
        asyncio.run(run_test())

    def test_recursive_url_count_is_capped(self):
        import asyncio
        from unittest.mock import AsyncMock
        from core.fetcher import MAX_RECURSIVE_URLS

        async def run_test():
            f = Fetcher()
            f._request_limited = AsyncMock(return_value="\n".join(f"https://public.example/{i}" for i in range(MAX_RECURSIVE_URLS + 25)).encode())
            f.fetch_nodes = AsyncMock(return_value=[])
            await f._fetch_nodes_internal("*https://public.example/index")
            self.assertEqual(f.fetch_nodes.await_count, MAX_RECURSIVE_URLS)

        asyncio.run(run_test())

    def test_recursion_depth_limit_stops_before_request(self):
        import asyncio
        from unittest.mock import AsyncMock

        async def run_test():
            f = Fetcher()
            f._request_limited = AsyncMock(side_effect=AssertionError("request should not happen"))
            nodes = await f.fetch_nodes("https://public.example/sub", recursion_depth=2)
            self.assertEqual(nodes, [])
            f._request_limited.assert_not_awaited()

        asyncio.run(run_test())

    def test_tls_verification_setting_passed_per_source(self):
        import asyncio
        from unittest.mock import patch

        async def run_test():
            infos = [{"name": "exception-source", "url": "https://public.example/sub", "verify_tls": False}]
            async def fake_fetch(url, *args, **kwargs):
                self.assertFalse(kwargs["verify_tls"])
                return [Node({"name": "n", "type": "ss", "server": "1.1.1.1", "port": 443, "cipher": "aes-128-gcm", "password": "p"})]
            with patch.object(Fetcher, "fetch_nodes", side_effect=fake_fetch):
                nodes, results = await parallel_fetch(infos)
            self.assertEqual(len(nodes), 1)
            self.assertTrue(results[0]["ok"])

        asyncio.run(run_test())

    def test_parallel_fetch(self):
        import asyncio
        from unittest.mock import patch

        async def run_test():
            source_infos = [
                {'name': 'Public Source 1', 'url': 'https://example.com/s1', 'filters': {}, 'is_private': False},
                {'name': 'Private Source 2', 'url': 'https://example.com/s2', 'filters': {}, 'is_private': True},
            ]
            async def fake_fetch(url, *args, **kwargs):
                is_priv = kwargs.get('is_private', False)
                if 's1' in url:
                    n = Node({"name": "Pub1", "type": "ss", "server": "1.1.1.1", "port": 443, "cipher": "aes-128-gcm", "password": "p"})
                    return [n]
                else:
                    n = Node({"name": "Priv1", "type": "ss", "server": "2.2.2.2", "port": 443, "cipher": "aes-128-gcm", "password": "p"})
                    if is_priv:
                        n.data['_is_private'] = True
                    return [n]

            with patch.object(Fetcher, 'fetch_nodes', side_effect=fake_fetch):
                all_nodes, source_results = await parallel_fetch(source_infos)
                self.assertEqual(len(all_nodes), 2)
                self.assertEqual(len(source_results), 2)
                self.assertFalse(source_results[0]['is_private'])
                self.assertTrue(source_results[1]['is_private'])

        asyncio.run(run_test())

if __name__ == "__main__":
    unittest.main()
