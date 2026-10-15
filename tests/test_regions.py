import unittest
from utils.regions import match_region

class TestRegions(unittest.TestCase):
    def test_substring_collision_fixes(self):
        # 1. Austria (AT) vs AUS (Australia)
        self.assertEqual(match_region("Austria 01 | 优质专线"), "AT")
        self.assertEqual(match_region("AUT-Vienna-01"), "AT")
        self.assertEqual(match_region("Australia Sydney 01"), "AU")
        self.assertEqual(match_region("AUS-01"), "AU")

        # 2. Korea Busan (KR) vs USA (United States)
        self.assertEqual(match_region("Korea Busan 01"), "KR")
        self.assertEqual(match_region("Busan-01"), "KR")
        self.assertEqual(match_region("Server-USA-01"), "US")

        # 3. Indonesia (ID) vs IND (India)
        self.assertEqual(match_region("Indonesia 01"), "ID")
        self.assertEqual(match_region("Jakarta-01"), "ID")
        self.assertEqual(match_region("India Mumbai 01"), "IN")
        self.assertEqual(match_region("IND-01"), "IN")

        # 4. Cyprus (CY) vs RUS (Russia)
        self.assertEqual(match_region("Cyprus Server 01"), "CY")
        self.assertEqual(match_region("Russia Moscow 01"), "RU")
        self.assertEqual(match_region("RUS-01"), "RU")

    def test_english_word_collision_fixes(self):
        # "No." or "No" should NOT match Norway (NO)
        self.assertIsNone(match_region("Node No.1"))
        self.assertIsNone(match_region("Proxy No 5"))
        self.assertEqual(match_region("NO-01"), "NO")
        self.assertEqual(match_region("Norway Oslo 01"), "NO")

        # "ID:" or "ID=" should NOT match Indonesia (ID)
        self.assertIsNone(match_region("Server ID: 05"))
        self.assertIsNone(match_region("Node ID=12345"))
        self.assertEqual(match_region("ID-01"), "ID")
        self.assertEqual(match_region("[ID] Server 01"), "ID")

        # "us" (pronoun) should NOT match United States (US)
        self.assertIsNone(match_region("Join us for updates"))
        self.assertIsNone(match_region("Contact us on Telegram"))
        self.assertEqual(match_region("US-01"), "US")
        self.assertEqual(match_region("[US] 01"), "US")

    def test_emoji_and_chinese_matching(self):
        self.assertEqual(match_region("🇯🇵 日本 01"), "JP")
        self.assertEqual(match_region("🇭🇰 香港 01 | BGP"), "HK")
        self.assertEqual(match_region("🇨🇵 法国海外属地"), "FR")
        self.assertEqual(match_region("首尔 01"), "KR")
        self.assertEqual(match_region("法兰克福 01"), "DE")

if __name__ == '__main__':
    unittest.main()
