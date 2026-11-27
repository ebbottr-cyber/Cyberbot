"""Offline regression tests for the Futures-only aligned pilot CLI."""
import io
import unittest
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import patch, call
from tools import pilot_loop as cli


class FuturesAlignmentTests(unittest.TestCase):
    def test_exact_slots_and_minute_rollover(self):
        for now, expected in [(0, 10), (10, 0), (10.5, 19.5),
                              (30, 0), (50, 0), (59, 11), (60, 10)]:
            with self.subTest(now=now):
                self.assertAlmostEqual(cli.aligned_delay(now), expected)

    def test_cooldown_skips_missed_slot(self):
        self.assertAlmostEqual(cli.aligned_delay(15, 30.25), 35)
        self.assertAlmostEqual(cli.aligned_delay(31, 31), 19)
        self.assertAlmostEqual(cli.aligned_delay(50, 30), 0)

    def invoke(self, args):
        with patch("sys.argv", ["pilot_loop.py", *args]), redirect_stdout(io.StringIO()):
            return cli.main()

    def test_aligned_run_skips_slot_after_slow_cycle(self):
        with patch.object(cli, "selected", return_value=["FUTURES"]), \
             patch.object(cli.time, "time", side_effect=[9, 15]), \
             patch.object(cli.time, "sleep") as sleep, \
             patch.object(cli, "run_cycle", return_value={"status": "ok"}) as run:
            self.assertEqual(self.invoke(["--align-minute", "--cycles", "2"]), 0)
            self.assertEqual(run.call_count, 2)
            self.assertEqual(sleep.call_args_list, [call(1), call(35)])

    def test_alignment_rejects_non_futures_and_wrong_interval(self):
        for markets, args in [(["SOLANA"], []), (["FUTURES", "SOLANA"], []),
                              (["FUTURES"], ["--interval", "30"])]:
            with self.subTest(markets=markets, args=args), \
                 patch.object(cli, "selected", return_value=markets), \
                 patch.object(cli.time, "sleep") as sleep, \
                 patch.object(cli, "run_cycle") as run, redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as exc:
                    self.invoke(["--align-minute", *args])
                self.assertEqual(exc.exception.code, 2)
                sleep.assert_not_called()
                run.assert_not_called()

    def test_clock_regression_stops_without_retry(self):
        with patch.object(cli, "selected", return_value=["FUTURES"]), \
             patch.object(cli.time, "time", return_value=10), \
             patch.object(cli.time, "sleep") as sleep, \
             patch.object(cli, "run_cycle", return_value={"status": "clock_regressed"}) as run:
            self.assertEqual(self.invoke(["--align-minute", "--cycles", "3"]), 1)
            run.assert_called_once_with()
            sleep.assert_called_once_with(0)

    def test_default_mode_preserves_relative_interval(self):
        with patch.object(cli.time, "sleep") as sleep, \
             patch.object(cli, "selected") as selected, \
             patch.object(cli, "run_cycle", return_value={"status": "ok"}) as run:
            self.assertEqual(self.invoke(["--cycles", "2", "--interval", "25"]), 0)
            self.assertEqual(run.call_count, 2)
            sleep.assert_called_once_with(25)
            selected.assert_not_called()

    def test_status_never_starts_observation(self):
        with patch.object(cli, "snapshot", return_value={"status": "not_started"}) as snapshot, \
             patch.object(cli, "run_cycle") as run, \
             patch.object(cli.time, "sleep") as sleep:
            self.assertEqual(self.invoke(["--status"]), 0)
            snapshot.assert_called_once_with()
            run.assert_not_called()
            sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
