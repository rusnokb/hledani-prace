"""Hodnocení vhodnosti nabídek vůči profilu uchazečky (AI, po dávkách)."""
from ai import QuotaExhausted
from config import PROFILE

# zvyšte při změně pravidel hodnocení → všechny nabídky se při dalším běhu přehodnotí
SCORING_VERSION = "2"

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
- UČITELSKÉ POZICE hodnoť podle PŘEDMĚTU a STUPNĚ, ne podle toho, že jde o školu:
  Aprobace „technická výchova“ = školní předmět na ZŠ (pracovní činnosti, dílny, technika, svět práce).
  NENÍ to kvalifikace pro odborné předměty středních odborných škol (strojírenství, elektrotechnika,
  IT/informatika, odborný výcvik, stavebnictví, ekonomika apod.) – ty vyžadují odborné vzdělání v daném oboru.
  Tabulka (výchozí skóre, uprav max o ±1 podle místa, úvazku a dalších podmínek):
    * matematika na 2. stupni ZŠ nebo víceletém gymnáziu ................................ 10
    * fyzika na ZŠ; technická výchova / pracovní činnosti / dílny na ZŠ ................. 9
    * matematika (příp. fyzika) na SŠ / SOU / gymnáziu ................................... 8
    * tělesná výchova na ZŠ ................................................................ 7
    * kombinace, kde aspoň jeden hlavní předmět je M / F / TV / pracovní činnosti ......... 7–9
    * „učitel 2. stupně“ bez určení předmětů, zástup na ZŠ ................................ 6
    * asistent/ka pedagoga, vychovatel/ka ŠD či DD, pedagog volného času, doučování ....... 6
    * lektor/ka kroužků (krátké úvazky), vedení technických či sportovních kroužků ......... 5
    * 1. stupeň ZŠ, MŠ, speciální pedagog ................................................. 3
    * jiné všeobecné předměty (ČJ, cizí jazyky, dějepis, zeměpis, přírodopis, chemie,
      informatika, hudební/výtvarná výchova, „všeobecné předměty“ bez M/F) ............... 2
    * odborné předměty SŠ (strojírenské, elektro, IT, stavební, ekonomické…), odborný výcvik, mistr OV 1
    * psycholog, logoped, speciální pedagog-poradce (vyžadují jiné VŠ studium) ........... 1
  Na polské škole (s polským jazykem vyučovacím) přidej +1 (polština je její silná stránka).
- VEDOUCÍ POZICE (ředitel/ka školy či ústavu, vedoucí odboru, vedoucí oddělení, manažer/ka) max 3 –
  nemá řídící praxi. Výjimka: vedoucí malého kolektivu v administrativě (např. vedoucí kanceláře) max 5.
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
