import unittest
from datetime import datetime,timezone,timedelta
from tools.dexterm_exit_history import bound
from tools.dexterm_paper_positions import simulate
from tools.dexterm_learning_dataset import build

BASE=datetime(2026,1,1,tzinfo=timezone.utc)
def stamp(s):return (BASE+timedelta(seconds=s)).isoformat()
def entry(s,qty=200,index=0):
    return {"mint":"m","timestamp":stamp(s),"input_raw":100000000,"token_amount_raw":qty,
            "return_raw":99000000,"source_digest":"entry","source_index":index}
def exit_quote(e,s,returned=110000000,index=0):
    return {"mint":e["mint"],"timestamp":stamp(s),"entry_timestamp":e["timestamp"],
            "entry_source_digest":e["source_digest"],"entry_source_index":e["source_index"],
            "token_amount_raw":e["token_amount_raw"],"return_raw":returned,
            "source_digest":"exit","source_index":index,"exit_only":True}

class ExitHistoryTests(unittest.TestCase):
    def test_exact_exit_closes_without_creating_new_entry(self):
        e=entry(0);q=exit_quote(e,180)
        d=simulate([e],exit_quotes=[q])
        self.assertEqual(d["closed_positions"],1)
        self.assertEqual(d["open_positions"],0)
        self.assertEqual(len(d["events"]),2)
        self.assertEqual(d["closed"][0]["exit_source_digest"],"exit")
        self.assertEqual(d["realized_net_raw"],9475000)
    def test_wrong_entry_and_quantity_rejected(self):
        e=entry(0);q=exit_quote(e,180)
        self.assertEqual(bound([e],[dict(q,entry_source_index=99)]),[])
        with self.assertRaises(ValueError):bound([e],[dict(q,token_amount_raw=201)])
    def test_same_timestamp_conflicting_exits_not_selected(self):
        e=entry(0);q=exit_quote(e,180)
        d=simulate([e],exit_quotes=[q,dict(q,return_raw=90000000,source_index=1)])
        self.assertEqual(d["open_positions"],1)
        self.assertEqual(d["skips"]["ambiguous_same_time_exit"],1)
    def test_explicit_exit_enables_label_without_matching_later_buy(self):
        rows=[entry(i*180,qty=200+i,index=i) for i in range(100)]
        q=exit_quote(rows[1],360)
        d=build(rows,exit_quotes=[q])
        self.assertEqual(d["example_count"],1)
        self.assertEqual(d["examples"][0]["exit_source"]["digest"],"exit")
        self.assertTrue(d["examples"][0]["label"]["positive_quote_net"])
        self.assertEqual(d["observation_count"],100)
        self.assertFalse(d["training_allowed"])
    def test_exit_for_unopened_entry_does_not_close_other_position(self):
        e=entry(0);other=entry(180,index=1,qty=201)
        d=simulate([e,other],exit_quotes=[exit_quote(other,360)])
        self.assertEqual(d["closed_positions"],0)
        self.assertEqual(d["open_positions"],1)
