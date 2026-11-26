import os,tempfile,unittest
from datetime import datetime,timezone
from pathlib import Path
from unittest.mock import patch
from cyberbot.news import save
from cyberbot.news_graph import graph,asset_link,canvas_summary
class NewsGraphTests(unittest.TestCase):
    def test_graph_and_links(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);db=p/"learning.sqlite3"
            env={"CYBERBOT_LEARNING_DB":str(db),"CYBERBOT_DB":str(p/"paper.sqlite3"),"CYBERBOT_WORKER_DB":str(p/"worker.sqlite3"),"CYBERBOT_EBBOT_DB":"","CYBERBOT_NEWS_ENABLED":"0"}
            with patch.dict(os.environ,env):
                self.assertEqual(graph()["record_count"],0)
                self.assertFalse(db.exists())
                x=save({"market":"BIST","kind":"company","event_type":"news","url":"https://example.org/event","event_at":datetime.now(timezone.utc).isoformat(),"label":"Örnek şirket duyurusu"})
                g=graph()
                self.assertEqual(g["record_count"],1)
                self.assertTrue(any(e["relation"]=="research_hypothesis" for e in g["edges"]))
                self.assertFalse(any(n["kind"]=="asset" for n in g["nodes"]))
                ref="manual:"+x["id"]
                self.assertTrue(asset_link(ref,"BIST","THYAO.IS","https://example.org/evidence")["new"])
                self.assertFalse(asset_link(ref,"BIST","THYAO.IS","https://example.org/evidence")["new"])
                with self.assertRaises(ValueError):asset_link(ref,"BIST","THYAO.IS","javascript:alert(1)")
                with self.assertRaises(ValueError):asset_link("manual:"+"0"*64,"BIST","THYAO.IS","https://example.org/evidence")
                before=db.read_bytes()
                g=graph("BIST")
                self.assertEqual(len(g["asset_links"]),1)
                self.assertFalse(g["asset_links"][0]["verified"])
                self.assertFalse(g["causal_impact_verified"])
                self.assertEqual(graph("NASDAQ")["record_count"],0)
                c=canvas_summary()
                self.assertNotIn("Örnek şirket",str(c))
                self.assertNotIn("example.org",str(c))
                self.assertEqual(db.read_bytes(),before)
                self.assertFalse((p/"paper.sqlite3").exists())
