import os,tempfile,unittest
from pathlib import Path
from datetime import datetime,timezone,timedelta
from email.utils import format_datetime
from unittest.mock import patch
from cyberbot.news_feed import parse,refresh,read,analysis,FeedError
class NewsFeedTests(unittest.TestCase):
    def test_feed(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);now=datetime.now(timezone.utc)
            item="<item><title>FOMC monetary policy decision</title><link>https://www.federalreserve.gov/newsevents/pressreleases/test.htm</link><pubDate>"+format_datetime(now.replace(microsecond=0))+"</pubDate><description>Do not store this article</description></item>"
            raw=("<rss version='2.0'><channel>"+item+item+"</channel></rss>").encode()
            with patch.dict(os.environ,{"CYBERBOT_NEWS_ENABLED":"1","CYBERBOT_NEWS_APPROVED":"fed","CYBERBOT_LEARNING_DB":str(p/"learning.sqlite3"),"CYBERBOT_DB":str(p/"paper.sqlite3"),"CYBERBOT_WORKER_DB":str(p/"worker.sqlite3"),"CYBERBOT_EBBOT_DB":""}):
                self.assertEqual(refresh("fed",transport=lambda _:raw,clock=lambda:now)["new"],1)
                with self.assertRaises(FeedError):refresh("fed",transport=lambda _:self.fail("network"),clock=lambda:now)
                self.assertEqual(refresh("fed",transport=lambda _:raw,clock=lambda:now+timedelta(seconds=900))["new"],0)
                d=read("NASDAQ");self.assertEqual(len(d["items"]),1)
                self.assertNotIn("Do not store",str(d))
                self.assertEqual(analysis("NASDAQ")["categories"],{"monetary_policy":1})
                self.assertEqual(read("BIST")["items"],[])
                with self.assertRaises(FeedError):refresh("ecb",transport=lambda _:self.fail("network"))
                self.assertFalse((p/"paper.sqlite3").exists())
                with patch.dict(os.environ,{"CYBERBOT_NEWS_ENABLED":"0"}):self.assertEqual(read()["items"],[])
    def test_xml_safety(self):
        with self.assertRaises(FeedError):parse(b'<!DOCTYPE rss [<!ENTITY x "x">]><rss/>',"fed",datetime.now(timezone.utc))
        with self.assertRaises(FeedError):parse(b"<html/>","fed",datetime.now(timezone.utc))
    def test_disabled(self):
        with patch.dict(os.environ,{"CYBERBOT_NEWS_ENABLED":"0"}):
            with self.assertRaises(FeedError):refresh("fed",transport=lambda _:self.fail("network"))
