import unittest
from utils.notify import format_tg_summary

class TestNotify(unittest.TestCase):
    def test_format_tg_summary_normal(self):
        gen_stats = {
            'total_nodes': 950,
            'region_nodes': {'HK': ['n1', 'n2'], 'US': ['n3']},
            'others': ['n4'],
            'timestamp': '2026-10-19 08:30:00',
            'source_count': 12,
            'raw_count': 1600,
            'elapsed_time': 5.23,
        }
        text = format_tg_summary(gen_stats)
        self.assertIn("<b>950</b>", text)
        self.assertIn("<code>2026-10-19 08:30:00</code>", text)
        self.assertIn("🇭🇰 香港 2", text)
        self.assertIn("🇺🇸 美国 1", text)
        self.assertIn("🌍 其他 1", text)
        self.assertIn("https://github.com/lanzm/MetaFetch", text)

    def test_format_tg_summary_html_escaping(self):
        # 验证插入的特殊 HTML 字符不会破坏 Telegram HTML 解析，而是被正确转义
        gen_stats = {
            'total_nodes': 100,
            'region_nodes': {
                'CUSTOM': ['n1'],  # REGION_NAMES 中未包含，直接取 key 作为名字
            },
            'others': [],
            'timestamp': '2026-10-19 <UTC> & "alert"',
            'source_count': 1,
            'raw_count': 100,
            'elapsed_time': 1.0,
        }
        # 模拟自定义地区名包含特殊字符
        from utils.regions import REGION_NAMES
        REGION_NAMES['CUSTOM'] = '🏴 地区 <Test & Demo>'

        try:
            text = format_tg_summary(gen_stats)
            # 1. 验证时间戳中的 <, >, & 均被转义
            self.assertNotIn('<UTC>', text)
            self.assertIn('&lt;UTC&gt;', text)
            self.assertIn('&amp;', text)

            # 2. 验证地区名称中的 <, > 和 & 被正确转义
            self.assertNotIn('<Test & Demo>', text)
            self.assertIn('&lt;Test &amp; Demo&gt;', text)

            # 3. 验证既有的 Telegram 格式化标签未受影响
            self.assertIn('<b>MetaFetch 节点自动抓取更新通知</b>', text)
            self.assertIn('<code>', text)
            self.assertIn('</code>', text)
        finally:
            REGION_NAMES.pop('CUSTOM', None)

if __name__ == '__main__':
    unittest.main()
