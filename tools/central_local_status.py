"""Local aggregate status; no worker startup, network probe or write authorization."""
import json
from cyberbot.integration_api import (central_preflight, integration_status, ai_status,
    notification_status, dexterm_learning_status)
from cyberbot.dexterm_replay_status import read


def snapshot():
    return {"version":"central-local-status-1","preflight":central_preflight(),
            "markets":integration_status(),"ai":ai_status(),
            "dexterm_learning":dexterm_learning_status(),"dexterm_replay":read(),
            "notification_worker":notification_status(),"network_probed":False,
            "tests_executed":False,"services_started":False,"real_orders":False}


if __name__=="__main__":
    print(json.dumps(snapshot(),ensure_ascii=True,indent=2,allow_nan=False))
