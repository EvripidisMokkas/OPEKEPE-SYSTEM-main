from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agropekepe.app import run_server


if __name__ == "__main__":
    run_server(ROOT / "agroledger.sqlite3", ROOT / "configs" / "cap_rules.example.json")
