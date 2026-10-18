"""Jeden běh hledání: sběr → filtr → AI hodnocení → porovnání s minulým během → web."""
import argparse
from datetime import date

import render
import state
from ai import AI
from scoring import score_listings
from sources import careers, upcr


def run(download=True, skip_web=False):
    db = state.load()
    ai = AI()
    if not ai.key:
        print("Upozornění: chybí GEMINI_API_KEY – nabídky se nebudou hodnotit a weby firem se nenačtou přes AI.")
    found, ok = [], set()

    print("Úřad práce ČR …")
    try:
        items, stats = upcr.fetch(download=download)
        found += items
        ok.add("upcr")
        print(f"  {stats['celkem']} nabídek v ČR, {stats['v_okoli']} v okolí, po filtru {len(items)} "
              f"(směny −{stats['vyrazeno_smeny']}, klíčová slova −{stats['vyrazeno_slova']}, jiný obor −{stats['mimo_obor']})")
    except Exception as e:
        print(f"  ! ÚP ČR selhal: {e}")

    targets = careers.load_targets()
    if not skip_web and targets:
        print(f"Weby zaměstnavatelů ({len(targets)}) …")
        items, ok_web = careers.fetch(ai)
        found += items
        ok |= ok_web
        print(f"  {len(items)} nabídek z webů, načteno {len(ok_web)}/{len(targets)} organizací")

    new_ids, removed_ids = state.merge(db, found, ok)
    print(f"Porovnání s minulým během: {len(new_ids)} nových, {len(removed_ids)} smazaných.")

    todo = [x for x in db["listings"].values() if x["status"] == "active" and state.needs_scoring(x)]
    if todo and ai.key:
        print(f"AI hodnocení {len(todo)} nabídek …")
        n = score_listings(ai, todo)
        for x in todo:
            if "score" in x:
                x["scored_hash"] = x["content_hash"]
        print(f"  ohodnoceno {n}, AI volání v tomto běhu: {ai.calls}")

    db["runs"].append({"date": date.today().isoformat(), "found": len(found), "new": len(new_ids),
                       "removed": len(removed_ids), "web_targets": len(targets), "ai_calls": ai.calls})
    db["runs"] = db["runs"][-50:]
    state.save(db)
    out = render.render(db)
    print(f"Hotovo → {out}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--no-download", action="store_true", help="použít už stažená data ÚP ČR")
    p.add_argument("--skip-web", action="store_true", help="nevolat weby zaměstnavatelů")
    a = p.parse_args()
    run(download=not a.no_download, skip_web=a.skip_web)
