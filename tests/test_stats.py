import unittest
import os
import tempfile
import datetime
from utils.stats import (
    build_overview_markdown,
    build_source_stats_markdown,
    apply_readme_updates,
    update_readme_all,
    prepare_source_stats,
)


class TestStats(unittest.TestCase):
    def setUp(self):
        self.sample_readme = (
            "# Project\n\n"
            "<!-- STATS_BADGE_START -->\nold_badges\n<!-- STATS_BADGE_END -->\n\n"
            "<!-- STATS_TABLE_START -->\nold_table\n<!-- STATS_TABLE_END -->\n\n"
            "<!-- SOURCE_STATS_TABLE_START -->\nold_sources\n<!-- SOURCE_STATS_TABLE_END -->\n"
        )
        self.gen_stats = {
            'total_nodes': 100,
            'region_nodes': {'HK': ['node1', 'node2'], 'US': ['node3']},
            'others': ['node4'],
            'timestamp': '2026-10-08 12:00:00',
            'source_count': 5,
            'raw_count': 200,
            'elapsed_time': 3.14,
        }
        self.source_results = [
            {'name': 'Source A', 'valid_count': 80},
            {'name': 'Source B', 'valid_count': 20},
        ]

    def test_apply_readme_updates_both(self):
        updated = apply_readme_updates(
            self.sample_readme,
            gen_stats=self.gen_stats,
            source_results=self.source_results,
            now=datetime.datetime(2026, 10, 8, 12, 0, 0),
        )

        self.assertNotIn("old_badges", updated)
        self.assertNotIn("old_table", updated)
        self.assertNotIn("old_sources", updated)

        self.assertIn("Valid_Nodes-100", updated)
        self.assertIn("Updated-2026--10--08_12%3A00%3A00-green.svg", updated)
        self.assertIn("香港", updated)
        self.assertIn("美国", updated)
        self.assertIn("Source A", updated)
        self.assertIn("80.00%", updated)

    def test_update_readme_all_file_io(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "README.md")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(self.sample_readme)

            update_readme_all(
                self.gen_stats,
                self.source_results,
                now=datetime.datetime(2026, 10, 8, 12, 0, 0),
                readme_path=file_path,
            )

            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            self.assertIn("Valid_Nodes-100", content)
            self.assertIn("Source A", content)

    def test_prepare_source_stats_single_private(self):
        class DummyNode:
            def __init__(self, name, source):
                self.data = {'name': name, '_source': source}

        raw_results = [
            {'name': 'Public Source 1', 'nodes': [{'name': 'n1'}], 'is_private': False},
            {'name': 'Secret Airport (user@abc.com)', 'nodes': [{'name': 'p1'}], 'is_private': True},
        ]
        final_nodes = [
            DummyNode('n1', 'Public Source 1'),
            DummyNode('p1', 'Secret Airport (user@abc.com)')
        ]
        stats = prepare_source_stats(raw_results, final_nodes=final_nodes)
        self.assertEqual(len(stats), 2)
        self.assertEqual(stats[0]['name'], 'Public Source 1')
        self.assertEqual(stats[0]['valid_count'], 1)
        # Private source must be masked
        self.assertEqual(stats[1]['name'], '👑 我的私有订阅')
        self.assertEqual(stats[1]['valid_count'], 1)

    def test_prepare_source_stats_multiple_private(self):
        class DummyNode:
            def __init__(self, name, source):
                self.data = {'name': name, '_source': source}

        raw_results = [
            {'name': 'Secret Airport A', 'nodes': [{'name': 'p1'}], 'is_private': True},
            {'name': 'Public Source 1', 'nodes': [{'name': 'n1'}], 'is_private': False},
            {'name': 'Secret VPS B', 'nodes': [{'name': 'p2'}, {'name': 'p3'}], 'is_private': True},
        ]
        final_nodes = [
            DummyNode('p1', 'Secret Airport A'),
            DummyNode('n1', 'Public Source 1'),
            DummyNode('p2', 'Secret VPS B'),
            DummyNode('p3', 'Secret VPS B'),
        ]
        stats = prepare_source_stats(raw_results, final_nodes=final_nodes)
        self.assertEqual(len(stats), 3)
        self.assertEqual(stats[0]['name'], '👑 我的私有订阅 01')
        self.assertEqual(stats[0]['valid_count'], 1)
        self.assertEqual(stats[1]['name'], 'Public Source 1')
        self.assertEqual(stats[1]['valid_count'], 1)
        self.assertEqual(stats[2]['name'], '👑 我的私有订阅 02')
        self.assertEqual(stats[2]['valid_count'], 2)

    def test_build_source_stats_markdown_safe_escaping(self):
        source_results = [
            {'name': 'Source | with | pipes', 'valid_count': 10},
            {'name': 'Source `with` backticks', 'valid_count': 5},
            {'name': 'Source\nwith\r\nnewlines', 'valid_count': 3},
        ]
        table = build_source_stats_markdown(source_results)
        # Pipes inside name must be replaced by - so table doesn't split columns
        self.assertNotIn("`Source | with | pipes`", table)
        self.assertIn("`Source - with - pipes`", table)
        # Backticks inside code block must be replaced
        self.assertNotIn("`Source `with` backticks`", table)
        self.assertIn("`Source 'with' backticks`", table)
        # Newlines inside name must be stripped/replaced
        self.assertNotIn("\nwith\r\n", table)
        self.assertIn("`Source with newlines`", table)

    def test_build_overview_shields_badge_escaping(self):
        badges, _ = build_overview_markdown(
            total_nodes=500,
            region_nodes={'HK': ['n1']},
            others=[],
            timestamp='2026-10-19 15:30:45',
            source_count=8,
            raw_count=1000,
            elapsed_time=2.5,
        )
        # 验证连字符 - 转义为 --，空格转义为 _，冒号转义为 %3A
        self.assertIn("Updated-2026--10--19_15%3A30%3A45-green.svg", badges)
        self.assertNotIn("2026-10-19", badges)
        self.assertIn("Valid_Nodes-500-orange.svg", badges)
        self.assertIn("Active_Sources-8-blue.svg", badges)

    def test_prepare_source_stats_scheme_a_dedup_attribution(self):
        class DummyNode:
            def __init__(self, name, source):
                self.data = {'name': name, '_source': source}

        raw_results = [
            {'name': 'Source A', 'nodes': [DummyNode('n1', 'Source A'), DummyNode('n2_dup', 'Source A')], 'is_private': False},
            {'name': 'Source B', 'nodes': [DummyNode('n3', 'Source B')], 'is_private': False},
        ]
        final_nodes = [DummyNode('n1', 'Source A'), DummyNode('n3', 'Source B')]
        stats = prepare_source_stats(raw_results, final_nodes=final_nodes)
        self.assertEqual(stats[0]['name'], 'Source A')
        self.assertEqual(stats[0]['valid_count'], 1)
        self.assertEqual(stats[1]['name'], 'Source B')
        self.assertEqual(stats[1]['valid_count'], 1)

        table = build_source_stats_markdown(stats)
        self.assertIn("去重后总计", table)
        self.assertIn("**2** 个", table)


if __name__ == "__main__":
    unittest.main()
