"""Hodnocení vhodnosti nabídek vůči profilu uchazečky (AI, po dávkách)."""
from ai import QuotaExhausted
from config import PROFILE

CATEGORIES = ["Školství", "Administrativa", "Veřejná správa", "Polština", "Jiné"]

PROMPT = """Jsi kariérní poradce. Posuď, jak dobře každá nabídka práce odpovídá profilu uchazečky.

PROFIL:
{profile}

PRAVIDLA:
- score 0–10: 9–10 téměř ideální shoda (kvalifikace i zaměření), 7–8 dobrá shoda, 5–6 stojí za zvážení,
  3–4 slabá shoda, 0–2 nevhodné.
- Pokud jde o obchodního zástupce / prodej na provizi / akvizice, nebo text naznačuje směnný či nepřetržitý
  provoz (ranní+odpolední, noční, turnusy, víkendové směny), dej score 0 a do reason napiš proč.
- Pokud jde o manuální, výrobní, zdravotnickou (sestra, ošetřovatel), gastro nebo úklidovou práci, dej max 2.
- Učitelské pozice bez její aprobace (např. angličtina, odborný výcvik) hodnoť nízko (2–4), pokud nejde
  o zástup / nekvalifikovaný úvazek, kde by mohla obstát.
- reason: 1 krátká věta česky (max 25 slov) – proč sedí / co chybí.
- category: jedna z {categories}.
- shift_risk: true, pokud text naznačuje směny, i když to není jisté.

NABÍDKY (JSON):
{items}

Vrať JSON pole objektů: [{{"id": "...", "score": 0, "category": "...", "reason": "...", "shift_risk": false}}]
Zahrň každé id přesně jednou."""


def score_listings(ai, listings, batch_size=15):
    """Doplní do listingů score/category/reason. Vrací počet ohodnocených."""
    import json

    done = 0
    for i in range(0, len(listings), batch_size):
        batch = listings[i:i + batch_size]
        items = [{
            "id": x["id"], "pozice": x["title"], "zamestnavatel": x["employer"], "misto": x["place"],
            "smennost": x.get("shift", ""), "uvazek": x.get("contract", ""),
            "popis": (x.get("description") or "")[:700],
        } for x in batch]
        prompt = PROMPT.format(profile=PROFILE, categories=", ".join(CATEGORIES),
                               items=json.dumps(items, ensure_ascii=False))
        try:
            result = ai.json(prompt, max_tokens=200 * len(batch) + 500)
        except QuotaExhausted as e:
            print(f"  AI hodnocení přerušeno: {e}")
            break
        except Exception as e:  # jedna vadná dávka nesmí shodit celý běh
            print(f"  AI chyba v dávce: {e}")
            continue
        by_id = {r.get("id"): r for r in result if isinstance(r, dict)}
        for x in batch:
            r = by_id.get(x["id"])
            if not r:
                continue
            x["score"] = int(r.get("score", 0))
            x["category"] = r.get("category") if r.get("category") in CATEGORIES else "Jiné"
            x["reason"] = r.get("reason", "")
            x["shift_risk"] = bool(r.get("shift_risk"))
            done += 1
    return done
