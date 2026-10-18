"""Evidence nabídek mezi běhy: nové / aktivní / smazané (archiv)."""
import json
from datetime import date, timedelta

from config import DATA_DIR

FILE = DATA_DIR / "listings.json"
MISSING_RUNS_TO_REMOVE = 2   # kolikrát po sobě musí nabídka chybět, než jde do archivu
ARCHIVE_DAYS = 60            # jak dlouho archiv držet

KEEP_FROM_PREVIOUS = ("first_seen", "score", "category", "reason", "shift_risk", "scored_hash")


def load():
    if FILE.exists():
        return json.loads(FILE.read_text(encoding="utf-8"))
    return {"runs": [], "listings": {}}


def save(db):
    FILE.write_text(json.dumps(db, ensure_ascii=False, indent=1), encoding="utf-8")


def content_hash(x):
    import hashlib
    key = "|".join(str(x.get(k, "")) for k in ("title", "employer", "description", "shift", "contract"))
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def merge(db, found, ok_sources, today=None):
    """found: listingy z tohoto běhu; ok_sources: zdroje, které se podařilo načíst.

    Vrací (nové, odstraněné) seznamy id."""
    today = today or date.today().isoformat()
    old = db["listings"]
    new_ids, removed_ids = [], []
    seen = set()
    for x in found:
        seen.add(x["id"])
        prev = old.get(x["id"])
        x["content_hash"] = content_hash(x)
        if prev:
            for k in KEEP_FROM_PREVIOUS:
                if k in prev and k not in x:
                    x[k] = prev[k]
            if prev.get("status") == "removed":   # znovu se objevila
                x["first_seen"] = today
                new_ids.append(x["id"])
        else:
            x["first_seen"] = today
            new_ids.append(x["id"])
        x["last_seen"] = today
        x["missing_runs"] = 0
        x["status"] = "active"
        old[x["id"]] = x

    for lid, x in old.items():
        x["is_new"] = lid in new_ids and bool(db["runs"])  # v úplně prvním běhu není nic „nové“

    for lid, x in list(old.items()):
        if lid in seen:
            continue
        if x.get("status") == "removed":
            if x.get("removed_on", today) < (date.fromisoformat(today) - timedelta(days=ARCHIVE_DAYS)).isoformat():
                del old[lid]
            continue
        if x.get("source_key") not in ok_sources:
            continue  # zdroj tentokrát nešel načíst – nic nemažeme
        x["missing_runs"] = x.get("missing_runs", 0) + 1
        if x["missing_runs"] >= MISSING_RUNS_TO_REMOVE:
            x["status"] = "removed"
            x["removed_on"] = today
            removed_ids.append(lid)
    return new_ids, removed_ids


def needs_scoring(x):
    return "score" not in x or x.get("scored_hash") != x.get("content_hash")
