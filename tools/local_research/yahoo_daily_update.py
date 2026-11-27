import sys
import subprocess

from pathlib import Path
from datetime import datetime, timezone

root = Path(__file__).resolve().parents[2]

collector = (
    Path(__file__).with_name("yahoo_collector_v2.py")
)

folder = root / "var/providers/logs"
folder.mkdir(parents=True,exist_ok=True)

stamp = datetime.now(timezone.utc).strftime(
    "%Y%m%d-%H%M%S-%f"
)

log = folder / ("daily-update-" + stamp + ".txt")

with log.open("x",encoding="utf-8") as f:

    try:

        result = subprocess.run(
            [
                sys.executable,
                "-B",
                str(collector),
                "--collect"
            ],
            cwd=root,
            stdout=f,
            stderr=subprocess.STDOUT,
            timeout=600,
            check=False
        )

        code = result.returncode

    except subprocess.TimeoutExpired:

        f.write("\nTIMEOUT: STOPPED\n")
        code = 1

    f.write(
        "\nCOLLECTION_EXIT: " + str(code) + "\n"
    )

raise SystemExit(code)
