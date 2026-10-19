# -*- coding: utf-8 -*-
import unittest
from utils.validators import is_invalid_or_private_server, INVALID_SERVERS


class TestValidators(unittest.TestCase):
    def test_invalid_and_placeholder_servers(self):
        # 空值与格式错误
        self.assertTrue(is_invalid_or_private_server(""))
        self.assertTrue(is_invalid_or_private_server(None))
        self.assertTrue(is_invalid_or_private_server("server with space"))
        self.assertTrue(is_invalid_or_private_server("server\nwith\nnewline"))

        # 占位符与黑名单
        for placeholder in ["0.0.0.0", "localhost", "example.com", "test.com", "none", "null", "undefined"]:
            self.assertTrue(is_invalid_or_private_server(placeholder), f"{placeholder} should be invalid")

    def test_loopback_addresses(self):
        # 127.0.0.0/8 全段
        self.assertTrue(is_invalid_or_private_server("127.0.0.1"))
        self.assertTrue(is_invalid_or_private_server("127.0.0.53"))
        self.assertTrue(is_invalid_or_private_server("127.123.45.67"))
        self.assertTrue(is_invalid_or_private_server("127.255.255.255"))
        # IPv6 回环
        self.assertTrue(is_invalid_or_private_server("::1"))
        self.assertTrue(is_invalid_or_private_server("[::1]"))

    def test_rfc1918_private_addresses(self):
        # 10.0.0.0/8
        self.assertTrue(is_invalid_or_private_server("10.0.0.1"))
        self.assertTrue(is_invalid_or_private_server("10.254.1.100"))
        # 172.16.0.0/12
        self.assertTrue(is_invalid_or_private_server("172.16.0.1"))
        self.assertTrue(is_invalid_or_private_server("172.31.255.254"))
        # 192.168.0.0/16
        self.assertTrue(is_invalid_or_private_server("192.168.1.1"))
        self.assertTrue(is_invalid_or_private_server("192.168.100.250"))
        # IPv6 ULA (fc00::/7)
        self.assertTrue(is_invalid_or_private_server("fc00::1"))
        self.assertTrue(is_invalid_or_private_server("[fd12:3456:789a::1]"))

    def test_link_local_and_cloud_metadata(self):
        # AWS / GCP / 阿里云等云厂商元数据地址 (169.254.169.254) 与链路本地
        self.assertTrue(is_invalid_or_private_server("169.254.169.254"))
        self.assertTrue(is_invalid_or_private_server("169.254.1.1"))
        # IPv6 链路本地 (fe80::/10)
        self.assertTrue(is_invalid_or_private_server("fe80::1"))
        self.assertTrue(is_invalid_or_private_server("[fe80::1]"))

    def test_cgnat_and_reserved_addresses(self):
        # RFC 6598 运营商级 NAT (100.64.0.0/10)
        self.assertTrue(is_invalid_or_private_server("100.64.0.1"))
        self.assertTrue(is_invalid_or_private_server("100.127.255.254"))
        # 广播/多播/未指定/保留
        self.assertTrue(is_invalid_or_private_server("224.0.0.1"))
        self.assertTrue(is_invalid_or_private_server("240.0.0.1"))
        self.assertTrue(is_invalid_or_private_server("::"))
        self.assertTrue(is_invalid_or_private_server("[::]"))

    def test_valid_public_ips_and_domains(self):
        # 公网 IPv4
        self.assertFalse(is_invalid_or_private_server("1.2.3.4"))
        self.assertFalse(is_invalid_or_private_server("8.8.8.8"))
        self.assertFalse(is_invalid_or_private_server("104.16.1.1"))
        # 公网 IPv6
        self.assertFalse(is_invalid_or_private_server("2606:4700:4700::1111"))
        self.assertFalse(is_invalid_or_private_server("[2606:4700:4700::1111]"))
        # 正常域名
        self.assertFalse(is_invalid_or_private_server("hk.node.example.org"))
        self.assertFalse(is_invalid_or_private_server("proxy-123.fastserver.net"))


if __name__ == "__main__":
    unittest.main()
