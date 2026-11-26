import unittest
from cyberbot.chronos_research import benchmark,ChronosError
from cyberbot.learning import demo_rows

class ChronosTests(unittest.TestCase):
    def test_baselines_and_interval(self):
        def fake(contexts):
            self.assertEqual(len(contexts),17)
            self.assertTrue(all(len(c)==60 for c in contexts))
            return [[-.01,0,.01] for c in contexts]
        d=benchmark([100]*120,mode="synthetic",predict=fake)
        self.assertEqual(d["interval_coverage_pct"],100)
        self.assertTrue(all(m["mae_pct"]==0 for m in d["models"]))
        self.assertFalse(d["promotion_enabled"])

    def test_no_target_in_context(self):
        prices=[float(r["close"]) for r in demo_rows()]
        seen=[]
        def fake(contexts):
            seen.extend(contexts)
            return [[-.1,0,.1] for c in contexts]
        benchmark(prices,mode="synthetic",predict=fake,windows=8)
        returns=[b/a-1 for a,b in zip(prices,prices[1:])]
        self.assertEqual(seen[0],returns[-68:-8])
        self.assertEqual(seen[-1],returns[-60:])

    def test_bad_output(self):
        with self.assertRaises(ChronosError):
            benchmark([100]*120,mode="synthetic",predict=lambda x:[[1,0,-1] for _ in x])
        with self.assertRaises(ChronosError):
            benchmark([100]*120,mode="synthetic",predict=lambda x:[])
