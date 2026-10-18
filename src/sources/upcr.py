"""Volná místa z otevřených dat Úřadu práce ČR (MPSV), aktualizace 1× denně."""
import json

from config import CONFIG, DATA_DIR
from geo import load_obce
from util import clean_ws, excluded_reason, fold, session

URL = "https://data.mpsv.cz/od/soubory/volna-mista/volna-mista.json"
DETAIL = "https://up.gov.cz/volna-mista-v-cr#/volna-mista-detail/{}"
RAW = DATA_DIR / "raw" / "volna-mista.json"

SHIFT_LABEL = {
    "jednoSm": "jednosměnný", "pruznaPd": "pružná pracovní doba", "neurceno": "neurčeno",
    "dvouSm": "dvousměnný", "triSm": "třísměnný", "ctyrSm": "čtyřsměnný", "turnus": "turnusový",
    "nepretrzity": "nepřetržitý", "nocni": "noční", "deleneSm": "dělené směny",
}
VZTAH_LABEL = {"plny": "HPP", "zkraceny": "zkrácený úvazek", "dpp": "DPP", "dpc": "DPČ"}


def _download():
    RAW.parent.mkdir(parents=True, exist_ok=True)
    with session.get(URL, stream=True, timeout=300) as r:
        r.raise_for_status()
        with open(RAW, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)


def _obec_kody(x):
    m = x.get("mistoVykonuPrace") or {}
    kody = []
    for pr in m.get("pracoviste") or []:
        o = (pr.get("adresa") or {}).get("obec")
        if o:
            kody.append(o["id"].split("/")[1])
    if m.get("obec"):
        kody.append(m["obec"]["id"].split("/")[1])
    return kody


def _wage(x):
    od, do = x.get("mesicniMzdaOd"), x.get("mesicniMzdaDo")
    unit = "Kč/hod" if (x.get("typMzdy") or {}).get("id", "").endswith("hod") else "Kč/měs"
    if od and do and od != do:
        return f"{od:,}–{do:,} {unit}".replace(",", " ")
    if od or do:
        return f"{(od or do):,} {unit}".replace(",", " ")
    return ""


def _wants_polish(x):
    return any(
        (j.get("jazyk") or {}).get("id") == "Jazyk/polJ" for j in x.get("pozadovanaJazykovaZnalost") or []
    )


def fetch(download=True):
    """Vrací (seznam kandidátů po tvrdém filtru, statistiky)."""
    if download or not RAW.exists():
        _download()
    items = json.loads(RAW.read_text(encoding="utf-8"))["polozky"]
    obce = load_obce()
    radius = CONFIG["radius_km"]
    isco_ok = tuple(CONFIG["isco_prefixes_include"])
    bad_shifts = set(CONFIG["exclude_shifts"])
    employer_kw = [fold(k) for k in CONFIG["employer_keywords_include"]]
    stats = {"celkem": len(items), "v_okoli": 0, "vyrazeno_smeny": 0, "vyrazeno_slova": 0, "mimo_obor": 0}
    out = []
    for x in items:
        near = [obce[k] for k in _obec_kody(x) if k in obce and obce[k]["km"] <= radius]
        if not near:
            continue
        stats["v_okoli"] += 1
        place = min(near, key=lambda o: o["km"])
        title = clean_ws((x.get("pozadovanaProfese") or {}).get("cs"))
        desc = (x.get("upresnujiciInformace") or {}).get("cs") or ""
        isco = (x.get("profeseCzIsco") or {}).get("id", "").split("/")[-1]
        polish = _wants_polish(x)
        employer = (x.get("zamestnavatel") or {}).get("nazev") or "(zaměstnavatel neuveden)"
        public = any(k in fold(employer) for k in employer_kw)
        if not (isco.startswith(isco_ok) or polish or public or x.get("statniSpravaSamosprava")):
            stats["mimo_obor"] += 1
            continue
        shift = (x.get("smennost") or {}).get("id", "")
        if shift in bad_shifts:
            stats["vyrazeno_smeny"] += 1
            continue
        if excluded_reason(title, desc):
            stats["vyrazeno_slova"] += 1
            continue
        vztahy = [VZTAH_LABEL.get(v["id"].split("/")[-1], v["id"].split("/")[-1])
                  for v in x.get("pracovnePravniVztahy") or []]
        out.append({
            "id": f"upcr:{x['portalId']}",
            "source_key": "upcr",
            "source": "Úřad práce ČR",
            "title": title,
            "employer": clean_ws(employer),
            "place": place["nazev"],
            "km": place["km"],
            "wage": _wage(x),
            "shift": SHIFT_LABEL.get(shift.split("/")[-1], ""),
            "contract": ", ".join(vztahy),
            "hours": x.get("pocetHodinTydne"),
            "polish": polish,
            "posted": (x.get("datumVlozeni") or "")[:10],
            "url": DETAIL.format(x["portalId"]),
            "source_url": "https://up.gov.cz/volna-mista-v-cr",
            "employer_url": x.get("urlAdresa") or "",
            "description": desc.strip()[:3000],
        })
    return out, stats
