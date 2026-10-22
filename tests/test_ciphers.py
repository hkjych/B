import unittest
from utils.ciphers import normalize_ss_cipher, is_valid_ss_cipher, SS_CIPHER_ALIASES, VALID_SS_CIPHERS
from core.parser import Node
from core.processor import NodeProcessor

class TestCiphers(unittest.TestCase):
    def test_normalize_ss_cipher_aliases(self):
        # 常见漏写 ietf 的情况
        self.assertEqual(normalize_ss_cipher('chacha20-poly1305'), 'chacha20-ietf-poly1305')
        self.assertEqual(normalize_ss_cipher('CHACHA20-POLY1305'), 'chacha20-ietf-poly1305')
        self.assertEqual(normalize_ss_cipher('chacha20-ietf-poly-1305'), 'chacha20-ietf-poly1305')
        self.assertEqual(normalize_ss_cipher('xchacha20-poly1305'), 'xchacha20-ietf-poly1305')
        
        # 常见缺少连字符的情况
        self.assertEqual(normalize_ss_cipher('aes128-gcm'), 'aes-128-gcm')
        self.assertEqual(normalize_ss_cipher('aes256-gcm'), 'aes-256-gcm')
        self.assertEqual(normalize_ss_cipher('rc4md5'), 'rc4-md5')

    def test_normalize_ss_cipher_standard(self):
        # 原生合法标准算法保持不变
        self.assertEqual(normalize_ss_cipher('aes-128-gcm'), 'aes-128-gcm')
        self.assertEqual(normalize_ss_cipher('chacha20-ietf-poly1305'), 'chacha20-ietf-poly1305')
        self.assertEqual(normalize_ss_cipher('2022-blake3-aes-128-gcm'), '2022-blake3-aes-128-gcm')

    def test_normalize_empty_or_none(self):
        self.assertEqual(normalize_ss_cipher(''), '')
        self.assertEqual(normalize_ss_cipher(None), '')

    def test_is_valid_ss_cipher(self):
        self.assertTrue(is_valid_ss_cipher('chacha20-ietf-poly1305'))
        self.assertTrue(is_valid_ss_cipher('chacha20-poly1305'))  # 自动归一化后合法
        self.assertTrue(is_valid_ss_cipher('aes-256-gcm'))
        self.assertTrue(is_valid_ss_cipher('2022-blake3-aes-256-gcm'))
        self.assertFalse(is_valid_ss_cipher('unknown-cipher-xyz'))
        self.assertFalse(is_valid_ss_cipher(''))
        self.assertFalse(is_valid_ss_cipher(None))

    def test_node_init_dict_cipher_normalization(self):
        # 模拟从上游 Clash YAML 加载的字典节点（即用户遇到的报错场景）
        raw_dict = {
            'name': 'Test-SS-Node',
            'type': 'ss',
            'server': '78.38.246.150',
            'port': 8446,
            'cipher': 'chacha20-poly1305',
            'password': 'password123'
        }
        node = Node(raw_dict)
        self.assertEqual(node.data['cipher'], 'chacha20-ietf-poly1305')

    def test_node_load_url_cipher_normalization(self):
        # 模拟从 ss:// 链接加载
        # base64(chacha20-poly1305:password123) = Y2hhY2hhMjAtcG9seTEzMDU6cGFzc3dvcmQxMjM=
        url = 'ss://Y2hhY2hhMjAtcG9seTEzMDU6cGFzc3dvcmQxMjM=@78.38.246.150:8446#TestSS'
        node = Node(url)
        self.assertEqual(node.data['cipher'], 'chacha20-ietf-poly1305')

    def test_processor_filter_and_clean_ss_node(self):
        proc = NodeProcessor()
        
        # 1. 带非标准 cipher 的节点应成功修正并通过过滤
        node_bad_cipher = Node({
            'name': '🇺🇸 US-Test',
            'type': 'ss',
            'server': '78.38.246.150',
            'port': 8446,
            'cipher': 'chacha20-poly1305',
            'password': 'pwd'
        })
        # 2. 完全非法 cipher 的节点应被剔除
        node_invalid = Node({
            'name': 'Invalid-SS',
            'type': 'ss',
            'server': '1.2.3.4',
            'port': 8388,
            'cipher': 'totally-bogus-cipher',
            'password': 'pwd'
        })
        
        valid = proc.filter_invalid([node_bad_cipher, node_invalid])
        self.assertEqual(len(valid), 1)
        self.assertEqual(valid[0].data['cipher'], 'chacha20-ietf-poly1305')

        # 3. clean_and_rename 同样保证正确性
        cleaned = proc.clean_and_rename(valid)
        self.assertEqual(cleaned[0].data['cipher'], 'chacha20-ietf-poly1305')

if __name__ == '__main__':
    unittest.main()
