import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from cyberbot.learning import demo_rows
from cyberbot.tournament import tournament,TournamentJournal

def fake_discovery(raw,**kwargs):
    assert len(raw)==180
    return {"strategies":[{"id":"trend","name":"Trend","score":80,"status":"research_candidate","oos_return_pct":2,"oos_drawdown_pct":1,"closed_trades":30},{"id":"momentum","name":"Momentum","score":70,"status":"research_candidate","oos_return_pct":3,"oos_drawdown_pct":2,"closed_trades":30}]}

class TournamentTests(unittest.TestCase):
    def test_final_data_not_in_selection(self):
        rows=demo_rows()
        changed=rows[:180]+[{"open":"100","close":"90"} for _ in range(60)]
        with patch("cyberbot.tournament.evaluate",side_effect=fake_discovery):
            a=tournament(rows,mode="synthetic",market="BIST",symbol="demo")
            b=tournament(changed,mode="synthetic",market="BIST",symbol="demo")
        self.assertEqual(a["candidate"],b["candidate"])
        self.assertEqual(a["ranking"],b["ranking"])
        self.assertEqual(a["validation"]["window"],b["validation"]["window"])
        self.assertNotEqual(a["id"],b["id"])
        self.assertFalse(b["promotion_enabled"])
        self.assertIsNone(b["market_wide_champion"])
    def test_journal_and_no_forced_champion(self):
        rows=[{"open":"100","close":"100"} for _ in range(240)]
        d=tournament(rows,mode="synthetic",market="SOLANA",symbol="demo")
        self.assertEqual(d["status"],"no_eligible_candidate")
        self.assertIsNone(d["research_champion"])
        self.assertEqual(d["initial_capital"],"1000")
        with tempfile.TemporaryDirectory() as tmp:
            j=TournamentJournal(Path(tmp)/"learning.sqlite3")
            self.assertTrue(j.save(d))
            self.assertFalse(j.save(d))
            self.assertEqual(j.get(d["id"]),d)
            self.assertEqual(len(j.recent("SOLANA","synthetic")),1)
            self.assertEqual(j.recent("BIST","synthetic"),[])
    def test_bounds(self):
        with self.assertRaises(ValueError):tournament(demo_rows()[:100],mode="synthetic",market="BIST",symbol="demo")
