import unittest
from unittest.mock import patch
from tools.central_local_status import snapshot

class CentralLocalStatusTests(unittest.TestCase):
    def test_status_aggregates_without_authorizing_services(self):
        names=("central_preflight","integration_status","ai_status","dexterm_learning_status","read","notification_status")
        from contextlib import ExitStack
        with ExitStack() as stack:
            mocks=[stack.enter_context(patch("tools.central_local_status."+name,return_value={"status":"blocked"})) for name in names]
            result=snapshot()
        for m in mocks:m.assert_called_once_with()
        self.assertEqual(result["version"],"central-local-status-1")
        for key in ("preflight","markets","ai","dexterm_learning","dexterm_replay","notification_worker"):
            self.assertEqual(result[key]["status"],"blocked")
        for key in ("services_started","real_orders","network_probed","tests_executed"):
            self.assertIs(result[key],False)
