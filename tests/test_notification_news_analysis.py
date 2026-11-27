import unittest
from tools.notification_news_analysis import analyze_news

class NewsAnalysisTest(unittest.TestCase):
    def test_policy(self):
        result = analyze_news("FED faiz kararı", "", "FED")
        self.assertEqual(result["priority"], "high")
        self.assertIn("NASDAQ", result["candidate_markets"])
        self.assertFalse(result["orders_enabled"])
        self.assertFalse(result["impact_verified"])
        self.assertEqual(result["direction"], "unknown")

    def test_symbols(self):
        result = analyze_news("Apple financial results", "", "SEC", {"AAPL": ["Apple"], "OTHER": ["App"]})
        self.assertEqual(result["candidate_symbols"], ["AAPL"])
        self.assertEqual(result["priority"], "medium")

    def test_unclassified(self):
        self.assertEqual(analyze_news("General update", "", "Unknown")["priority"], "low")
