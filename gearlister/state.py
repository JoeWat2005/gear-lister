"""Records what has already been created so re-runs skip finished items."""
import csv
from datetime import datetime, timezone

from .config import OUT_DIR

RESULTS = OUT_DIR / "results.csv"
FIELDS = ["timestamp", "sku", "platform", "status", "id", "url", "note"]


def load() -> dict[tuple[str, str], dict]:
    done: dict[tuple[str, str], dict] = {}
    if not RESULTS.exists():
        return done
    with open(RESULTS, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("status") in ("created", "scheduled", "published"):
                done[(row["sku"], row["platform"])] = row
    return done


def record(sku: str, platform: str, status: str, id_: str = "", url: str = "", note: str = ""):
    OUT_DIR.mkdir(exist_ok=True)
    new = not RESULTS.exists()
    with open(RESULTS, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerow({
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "sku": sku, "platform": platform, "status": status,
            "id": id_, "url": url, "note": note[:500],
        })
