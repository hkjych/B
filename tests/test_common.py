import unittest
from utils.common import b64encodes, b64decodes, b64decodes_safe

class TestCommon(unittest.TestCase):
    def test_b64encodes_and_decodes(self):
        raw = "hello world"
        encoded = b64encodes(raw)
        self.assertEqual(b64decodes(encoded), raw)

    def test_b64decodes_missing_padding(self):
        raw = "vmess://eyJhZGQiOiIxMjcuMC4wLjEiLCJwb3J0IjoiNDQzIn0"
        decoded = b64decodes(raw[8:])
        self.assertIn("127.0.0.1", decoded)

    def test_b64decodes_empty_or_invalid(self):
        self.assertEqual(b64decodes(""), "")
        self.assertEqual(b64decodes("!!!invalid_base64!!!"), "")

    def test_b64decodes_with_whitespace(self):
        raw = "hello whitespace test"
        encoded = "  \r\n" + b64encodes(raw) + " \n\r "
        self.assertEqual(b64decodes(encoded), raw)
        self.assertEqual(b64decodes_safe(encoded), raw)

    def test_b64decodes_urlsafe_with_hyphens_and_underscores(self):
        import base64
        # 1. 包含 - 的 urlsafe 密文
        raw1 = ">>>?hello"
        enc1 = base64.urlsafe_b64encode(raw1.encode('utf-8')).decode('utf-8')
        self.assertIn('-', enc1)
        self.assertEqual(b64decodes(enc1), raw1)
        self.assertEqual(b64decodes_safe(enc1), raw1)

        # 2. 包含 _ 的 urlsafe 密文
        raw2 = "hello?world?test"
        enc2 = base64.urlsafe_b64encode(raw2.encode('utf-8')).decode('utf-8')
        self.assertIn('_', enc2)
        self.assertEqual(b64decodes(enc2), raw2)
        self.assertEqual(b64decodes_safe(enc2), raw2)

    def test_b64encodes_none_or_empty(self):
        self.assertEqual(b64encodes(None), "")
        self.assertEqual(b64encodes(""), "")

    def test_deep_sanitize_strict(self):
        from utils.common import deep_sanitize
        dirty = {
            "name\x00": "test\x07node\r\n",
            "list": ["item\x08", "clean", "\u200bhidden"]
        }
        cleaned = deep_sanitize(dirty, preserve_newlines=False)
        self.assertEqual(cleaned["name"], "testnode")
        self.assertEqual(cleaned["list"], ["item", "clean", "hidden"])

    def test_deep_sanitize_preserve_newlines(self):
        from utils.common import deep_sanitize
        dirty = {
            "yaml_text": "line1\nline2\r\n\tindented\x00bad",
            "key\x07": "val"
        }
        cleaned = deep_sanitize(dirty, preserve_newlines=True)
        self.assertEqual(cleaned["yaml_text"], "line1\nline2\r\n\tindentedbad")
        self.assertEqual(cleaned["key"], "val")

if __name__ == "__main__":
    unittest.main()
