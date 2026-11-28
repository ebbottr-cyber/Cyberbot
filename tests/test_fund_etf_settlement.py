"""Historical paper settlement tests using synthetic calendars, not real product terms."""
import unittest
from decimal import Decimal
from tools.fund_etf_settlement import replay


class SettlementTests(unittest.TestCase):
    def setUp(self):
        self.days=["2025-01-02","2025-01-03","2025-01-06","2025-01-07","2025-01-08"]
        self.args=dict(market="TEFAS",symbol="TEST",currency="TRY",
            rules=dict(source="fixture",calendar_source="fixture",corporate_actions_reviewed=True,
                       timezone="UTC",valid_from=self.days[0],valid_to=self.days[-1],
                       buy_price_lag=0,buy_publication_lag=1,buy_settlement_lag=2,
                       sell_price_lag=0,sell_publication_lag=1,sell_settlement_lag=2,fee_bps=100),
            sessions=[dict(date=d,cutoff="13:00") for d in self.days],
            prices={d:"10" for d in self.days},orders=[],as_of=self.days[-1],initial_cash=100)

    def buy(self,stamp="2025-01-02T12:00:00+00:00",amount=100):
        return dict(id="B1",timestamp=stamp,side="BUY",amount=amount)

    def test_after_cutoff_and_weekend(self):
        self.args["orders"]=[self.buy("2025-01-03T13:00:00+00:00")]
        result=replay(**self.args)
        event=result["events"][0]
        self.assertEqual(event["effective_session"],"2025-01-06")
        self.assertEqual(event["settlement_session"],"2025-01-08")
        self.assertFalse(result["real_orders"])

    def test_unpublished_nav_not_consumed(self):
        self.args.update(orders=[self.buy()],as_of=self.days[0])
        self.args["prices"][self.days[0]]="not-yet-published"
        result=replay(**self.args)
        self.assertEqual(Decimal(result["reserved_cash"]),100)
        self.assertEqual(result["pending"][0]["state"],"awaiting_price")
        self.assertEqual(Decimal(result["available_units"]),0)

    def test_no_double_spend(self):
        self.args["orders"]=[self.buy(),dict(id="B2",timestamp="2025-01-02T12:01:00+00:00",side="BUY",amount=100)]
        result=replay(**self.args)
        self.assertTrue(any(e["event"]=="rejected" for e in result["events"]))
        self.assertEqual(Decimal(result["reserved_cash"]),0)
        self.assertAlmostEqual(float(result["available_units"]),100/1.01/10)

    def test_missing_price_blocks(self):
        self.args["orders"]=[self.buy()]
        self.args["prices"]={}
        result=replay(**self.args)
        self.assertEqual(result["status"],"review_required")
        self.assertEqual(Decimal(result["reserved_cash"]),100)

    def test_sale_proceeds_unavailable_until_settlement(self):
        self.args.update(initial_cash=0,initial_units=10,as_of=self.days[1],
                         orders=[dict(id="S1",timestamp="2025-01-02T12:00:00+00:00",side="SELL",amount=5)])
        result=replay(**self.args)
        self.assertEqual(Decimal(result["available_cash"]),0)
        self.assertEqual(Decimal(result["reserved_units"]),5)
        self.args["as_of"]=self.days[2]
        result=replay(**self.args)
        self.assertEqual(Decimal(result["available_cash"]),Decimal("49.5"))

    def test_etf_distribution_only_on_pay_session(self):
        self.args.update(market="ETF",currency="USD",initial_cash=0,initial_units=10,
                         dividends=[dict(record_session=self.days[0],pay_session=self.days[2],net_per_unit=".5",source="fixture")],
                         as_of=self.days[1])
        self.assertEqual(Decimal(replay(**self.args)["available_cash"]),0)
        self.args["as_of"]=self.days[2]
        self.assertEqual(Decimal(replay(**self.args)["available_cash"]),5)


if __name__=="__main__":
    unittest.main()
