"""Run Solana tests with Python network and child-process access denied.

Run only from an isolated checkout: python -m tools.solana_offline_test_suite.
This is a test guard, not an operating-system sandbox.
"""
import ast
import importlib.util
import json
import os
import socket
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from contextlib import ExitStack

def denied(*args,**kwargs):
    raise RuntimeError("External access disabled by offline test suite")

def main():
    root=Path(__file__).resolve().parents[1]
    if Path.cwd().resolve()!=root:
        print("Run from the isolated repository root.",file=sys.stderr);return 2
    files=sorted(set(root.glob("tools/solana*.py"))|set(root.glob("tools/dexterm*.py"))|
                 set(root.glob("tests/test_solana*.py"))|
                 {root/"cyberbot"/"solana_research_api.py"})
    for path in files:ast.parse(path.read_text(encoding="utf-8-sig"),filename=str(path.relative_to(root)))
    env={k:v for k,v in os.environ.items() if not k.upper().startswith(("CYBERBOT_","DEXTERM_","HELIUS_","JUPITER_"))}
    env.update(CYBERBOT_PILOT_KILL_SWITCH="1",CYBERBOT_SOLANA_DATA_RIGHTS_CONFIRMED="0")
    with ExitStack() as stack:
        stack.enter_context(patch.dict(os.environ,env,clear=True))
        for name in ("connect","connect_ex","sendto","sendall"):
            stack.enter_context(patch.object(socket.socket,name,denied))
        for name in ("create_connection","getaddrinfo"):
            stack.enter_context(patch.object(socket,name,denied))
        stack.enter_context(patch.object(subprocess,"Popen",denied))
        suite=unittest.defaultTestLoader.discover(str(root/"tests"),pattern="test_solana*.py")
        result=unittest.TextTestRunner(verbosity=2).run(suite)
    optional={name:importlib.util.find_spec(name) is not None for name in ("lightgbm","river")}
    print(json.dumps({"status":"passed" if result.wasSuccessful() else "failed",
                      "syntax_files":len(files),"tests_run":result.testsRun,
                      "failures":len(result.failures),"errors":len(result.errors),
                      "skipped":len(result.skipped),"optional_packages_discoverable":optional,
                      "native_optional_model_fit_verified":False,
                      "live_provider_verified":False,"production_training_performed":False,
                      "real_orders":False},indent=2))
    return 0 if result.wasSuccessful() and result.testsRun else 1

if __name__=="__main__":raise SystemExit(main())
