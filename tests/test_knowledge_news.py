import io,json,os,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
from datetime import datetime,timezone
from cyberbot.knowledge import snapshot,vault_zip
from cyberbot.news import list_refs,save
class KnowledgeNewsTests(unittest.TestCase):
    def test_empty_and_news(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            env={"CYBERBOT_LEARNING_DB":str(p/"learning.sqlite3"),"CYBERBOT_DB":str(p/"paper.sqlite3"),"CYBERBOT_WORKER_DB":str(p/"worker.sqlite3"),"CYBERBOT_EBBOT_DB":""}
            with patch.dict(os.environ,env):
                d=snapshot("synthetic")
                self.assertEqual(len(d["markets"]),5)
                self.assertFalse((p/"learning.sqlite3").exists())
                with zipfile.ZipFile(io.BytesIO(vault_zip("synthetic"))) as z:
                    self.assertIn("Arastirmalar.base",z.namelist())
                    canvas=json.loads(z.read("Cyberbot.canvas"))
                    self.assertEqual(len(canvas["nodes"]),6)
                    for n in canvas["nodes"]:
                        if n["type"]=="file":self.assertIn(n["file"],z.namelist())
                self.assertEqual(list_refs()["items"],[])
                x={"market":"BIST","kind":"macro","event_type":"news","url":"https://example.org/event","event_at":datetime.now(timezone.utc).isoformat(),"label":"Test etiketi","note":""}
                self.assertTrue(save(x)["new"])
                self.assertFalse(save(x)["new"])
                self.assertEqual(len(list_refs("BIST")["items"]),1)
                self.assertEqual(list_refs("FUTURES")["items"],[])
                self.assertFalse(list_refs()["automatic_feed_enabled"])
                with self.assertRaises(ValueError):save({**x,"url":"javascript:alert(1)"})
                self.assertFalse((p/"paper.sqlite3").exists())
