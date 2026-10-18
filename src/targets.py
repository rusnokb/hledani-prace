"""Sestaví seznam organizací v okolí (školy, obce, instituce, firmy 50+) a dohledá jejich
weby a stránky s volnými místy. Spouští se jednorázově / občas (např. 1× za čtvrt roku):

    python targets.py            # sestavit + dohledat weby (bez AI)
    python targets.py --search   # navíc dohledat chybějící weby (AI navrhne doménu, skript ji ověří)

Ruční úpravy v data/targets.json (enabled, check_urls, website) se při dalším sestavení zachovají."""
import argparse
import csv
import json
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from ai import AI, QuotaExhausted
from config import CONFIG, DATA_DIR
from geo import load_obce
from util import clean_ws, fold, session

RAW = DATA_DIR / "raw"
TARGETS_FILE = DATA_DIR / "targets.json"
MANUAL_FILE = DATA_DIR.parent / "manual_targets.json"
RES_URL = "https://opendata.csu.gov.cz/soubory/od/od_org03/res_data.csv"
UP_URL = "https://data.mpsv.cz/od/soubory/volna-mista/volna-mista.json"
RSSZ_URL = ("https://lkod-ftp.msmt.gov.cz/00022985/11f1f670-1a8a-4a8a-b188-0eed2d01fca7/"
            "RSSZ-Moravskoslezsky-kraj.jsonld")

BIG = {"240", "310", "320", "330", "340", "410", "420", "430", "440", "450", "460", "470", "480"}
MID = BIG | {"230"}
SCHOOL_KINDS = {"B00", "C00", "E00", "F10", "G11", "G21", "G22", "H22", "K10", "K20"}
OKRES_NUTS = {"CZ0802": 3802, "CZ0803": 3803, "CZ0806": 3807}
FREE_MAIL = {"seznam.cz", "email.cz", "post.cz", "centrum.cz", "volny.cz", "atlas.cz", "gmail.com", "outlook.com",
             "hotmail.com", "quick.cz", "tiscali.cz", "po-msk.cz", "msk.cz", "icloud.com", "yahoo.com", "o2active.cz",
             "outlook.cz", "live.com", "mpsv.cz", "tiscali.com", "onet.pl", "wp.pl", "interia.pl"}
PORTALS = ("jobs.cz", "prace.cz", "profesia", "uradprace", "up.gov.cz", "linkedin", "facebook", "instagram",
           "indeed", "jenda.mpsv", "grafton", "manpower", "startupjobs")
# text odkazu (jen krátké položky menu, ne titulky článků)
CAREER_LABEL_RE = re.compile(
    r"^(kari[eé]ra|kari[eé]rn[ií]|volna[-_ ]?mista|voln[aá] (pracovn[ií] )?m[ií]sta|voln[eé] (pracovn[ií] )?m[ií]sto|"
    r"pracovn[ií] (m[ií]sta|p[rř][ií]le[zž]itosti|nab[ií]dky)|nab[ií]dk[ay] (pr[aá]ce|zam[eě]stn[aá]n[ií])|"
    r"zam[eě]stn[aá]n[ií]|jobs?|careers?|pracuj(te)? u n[aá]s|p[rř]idej(te)? se k n[aá]m|hled[aá]me (posily|kolegy|v[aá]s)|"
    r"v[yý]b[eě]rov[aá] [rř][ií]zen[ií]|personalistika|chci u v[aá]s pracovat)\b",
    re.I,
)
# cesta v URL
CAREER_PATH_RE = re.compile(
    r"(^|/)(kariera|career|careers|jobs?|volna-?mista|volne-?misto|volna-pracovni-mista|nabidka-prace|nabidky-prace|"
    r"nabidka-zamestnani|zamestnani|pracovni-mista|pracovni-prilezitosti|vyberova-rizeni|prace-u-nas|pracuj-u-nas)"
    r"(/|$|\.|-|\?)",
    re.I,
)
REGION_PSC_RE = re.compile(r"\b73\d\s?\d\d\b")
REGION_WORDS = ("moravskoslezsk", "frydek-mistek", "frydku-mistku", "karvin", "tesin", "trinec", "trinci", "havirov",
                "jablunkov", "beskyd", "slezsk")


def _download(url, path):
    if path.exists():
        return
    print(f"Stahuji {url} …")
    with session.get(url, stream=True, timeout=600) as r:
        r.raise_for_status()
        with open(path, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)


def _rssz_url():
    """Aktuální odkaz na rejstřík škol MSK z Národního katalogu otevřených dat (adresa se mění)."""
    q = ('PREFIX dct: <http://purl.org/dc/terms/> PREFIX dcat: <http://www.w3.org/ns/dcat#> '
         'SELECT ?url WHERE { ?ds dct:title "Rejstřík škol a školských zařízení - Moravskoslezský kraj"@cs ; '
         'dcat:distribution/dcat:downloadURL ?url } LIMIT 1')
    try:
        r = session.get("https://data.gov.cz/sparql", params={"query": q},
                        headers={"Accept": "application/sparql-results+json"}, timeout=60)
        return r.json()["results"]["bindings"][0]["url"]["value"]
    except Exception:
        return RSSZ_URL


def _slug(name):
    return re.sub(r"[^a-z0-9]+", "-", fold(name)).strip("-")


def _short_name(firma):
    return clean_ws(re.sub(r",?\s*(příspěvková organizace|p\.\s?o\.)\s*$", "", firma, flags=re.I))


def candidates():
    obce = load_obce()
    radius = CONFIG["radius_km"]
    near = {k: v for k, v in obce.items() if v["km"] <= radius}
    by_name = {(v["nazev"], v["okres"]): v for v in near.values()}
    out = {}

    # 1) školy z rejstříku škol (mají e-maily → doména webu, jazyk výuky)
    RAW.mkdir(parents=True, exist_ok=True)
    _download(_rssz_url(), RAW / "rssz_msk.jsonld")
    for x in json.loads((RAW / "rssz_msk.jsonld").read_text(encoding="utf-8"))["list"]:
        a = x["adresa"]
        o = by_name.get((a["obec"], OKRES_NUTS.get(a.get("okres"))))
        druhy = {s["druh"] for s in x["skolyAZarizeni"]}
        if not o or not (druhy & SCHOOL_KINDS):
            continue
        domains = sorted({e.split("@")[-1].lower() for e in x.get("emaily") or []} - FREE_MAIL)
        out[x["ico"]] = {
            "id": x["ico"], "ico": x["ico"], "name": _short_name(x["uplnyNazev"]), "kind": "škola",
            "place": o["nazev"], "km": o["km"],
            "polish": any(s.get("jazyk") == "500" for s in x["skolyAZarizeni"]),
            "hints": domains,
        }

    # 2) obce, instituce a větší firmy z registru ekonomických subjektů ČSÚ
    _download(RES_URL, RAW / "res_data.csv")
    with open(RAW / "res_data.csv", encoding="utf-8", newline="") as f:
        for x in csv.DictReader(f):
            o = near.get(x["ICZUJ"])
            if not o or x["DDATZAN"] or x["ICO"] in out:
                continue
            forma, kat, nace = x["FORMA"], x["KATPO"], x["NACE"]
            if forma == "801":
                kind = "obec"
            elif forma in ("331", "325") and (kat in MID or forma == "325") and not nace.startswith("85"):
                kind = "instituce"
            elif kat in BIG and forma not in ("331", "325", "421", "801") and not nace.startswith("85"):
                kind = "firma"
            else:
                continue
            out[x["ICO"]] = {"id": x["ICO"], "ico": x["ICO"], "name": _short_name(x["FIRMA"]), "kind": kind,
                             "place": o["nazev"], "km": o["km"], "polish": False, "hints": []}

    # 3) weby, které firmy uvedly u Úřadu práce (URL a domény kontaktních e-mailů)
    up_file = RAW / "volna-mista.json"
    _download(UP_URL, up_file)
    if up_file.exists():
        for v in json.loads(up_file.read_text(encoding="utf-8"))["polozky"]:
            ico = ((v.get("zamestnavatel") or {}).get("ico") or "").zfill(8)
            if ico not in out:
                continue
            hints = out[ico]["hints"]
            url = v.get("urlAdresa") or ""
            if url and not any(p in url for p in PORTALS):
                hints.append(urlparse(url if "//" in url else "https://" + url).netloc.lower().removeprefix("www."))
            mail = (((v.get("prvniKontaktSeZamestnavatelem") or {}).get("komuSeHlasit") or {}).get("email") or "")
            if "@" in mail and mail.split("@")[-1].lower() not in FREE_MAIL:
                hints.append(mail.split("@")[-1].lower())
    for c in out.values():
        c["hints"] = list(dict.fromkeys(h for h in c["hints"] if h))
        if c["kind"] == "obec":
            s = _slug(c["place"])
            s2 = s.replace("-", "")
            c["hints"] += [f"{s}.cz", f"{s2}.cz", f"obec{s2}.cz", f"obec-{s}.cz", f"mesto{s2}.cz",
                           f"mesto-{s}.cz", f"{s}-obec.cz", f"{s2}-obec.cz"]
            c["hints"] = list(dict.fromkeys(c["hints"]))
    return list(out.values())


def _get(url):
    try:
        r = session.get(url, timeout=20, allow_redirects=True)
        if r.status_code == 200 and "html" in r.headers.get("content-type", ""):
            r.encoding = r.apparent_encoding if r.encoding in (None, "ISO-8859-1") else r.encoding
            return r
    except Exception:
        pass
    return None


def _verify_home(domain, c):
    for url in (f"https://www.{domain}", f"https://{domain}", f"http://www.{domain}"):
        r = _get(url)
        if not r:
            continue
        if c["kind"] == "obec":  # u odhadnutých domén ověř, že jde opravdu o tu obec
            t = fold(BeautifulSoup(r.text, "html.parser").get_text(" "))
            if (fold(c["place"]) not in t or not any(w in t for w in ("obec", "mesto", "urad", "starost"))
                    or not (REGION_PSC_RE.search(t) or any(w in t for w in REGION_WORDS))):
                return None
        return r
    return None


def find_career_links(resp, website):
    soup = BeautifulSoup(resp.text, "html.parser")
    host = urlparse(resp.url).netloc.removeprefix("www.")
    found = []
    for a in soup.find_all("a", href=True):
        label = clean_ws(a.get_text(" "))
        href = urljoin(resp.url, a["href"])
        if href.startswith(("mailto:", "tel:", "javascript:")) or href.lower().endswith((".pdf", ".doc", ".docx")):
            continue
        path = urlparse(href).path
        label_ok = len(label) <= 40 and CAREER_LABEL_RE.search(label)
        if not (label_ok or CAREER_PATH_RE.search(path)) or "karierov" in fold(label + path):
            continue
        h = urlparse(href).netloc.removeprefix("www.")
        if h != host and not any(k in h for k in ("kariera", "career", "jobs", "teamio", "recruitis", "prace")):
            continue
        if any(p in h for p in ("facebook", "linkedin", "instagram")):
            continue
        found.append(href.split("#")[0])
    # preferuj odkazy s nejsilnějšími slovy
    found = list(dict.fromkeys(found))
    found.sort(key=lambda u: 0 if CAREER_PATH_RE.search(urlparse(u).path) else 1)
    return found[:2]


def discover(c, prev):
    if prev and (prev.get("manual") or prev.get("website") or prev.get("searched")):
        return prev  # ručně upraveno nebo už dohledáno – nesahat
    t = {k: c[k] for k in ("id", "ico", "name", "kind", "place", "km", "polish")}
    t.update({"website": "", "check_urls": [], "enabled": True})
    for d in c["hints"]:
        r = _verify_home(d, c)
        if r:
            t["website"] = r.url
            links = find_career_links(r, r.url)
            # u škol a obcí se volná místa často objeví mezi aktualitami na úvodní stránce
            t["check_urls"] = links or ([r.url] if c["kind"] in ("škola", "obec", "instituce") else [])
            break
    return t


LEGAL = {"sro", "s", "r", "o", "as", "a", "spol", "spolecnost", "akciova", "obec", "mesto", "statutarni", "prispevkova",
         "organizace", "druzstvo", "cz", "czech", "republic", "group", "k", "v", "se", "z", "u", "na", "ve", "o.p.s"}


def _name_tokens(name):
    return [w for w in re.findall(r"[a-z0-9]{4,}", fold(name)) if w not in LEGAL]


def _page_matches(resp, t):
    txt = fold(BeautifulSoup(resp.text, "html.parser").get_text(" "))
    if t.get("ico") and t["ico"].lstrip("0") in txt.replace(" ", ""):
        return True
    toks = _name_tokens(t["name"])
    return bool(toks) and sum(1 for w in toks if w in txt) >= max(1, (len(toks) + 1) // 2)


def guess_missing(targets, limit):
    """Bez vyhledávače: AI navrhne pravděpodobné domény, každá se ověří stažením a kontrolou názvu/IČO."""
    ai = AI()
    todo = [t for t in targets if not t["website"] and not t.get("manual") and not t.get("guessed")][:limit]
    found = 0
    for i in range(0, len(todo), 20):
        batch = todo[i:i + 20]
        items = [{"id": t["id"], "nazev": t["name"], "ico": t["ico"], "obec": t["place"]} for t in batch]
        try:
            res = ai.json(
                "U každé české organizace uveď 1–3 nejpravděpodobnější domény jejích oficiálních webových stránek "
                "(např. \"trz.cz\"). Pokud web nejspíš nemá nebo nevíš, vrať prázdný seznam. Domény ověříme.\n"
                f"{json.dumps(items, ensure_ascii=False)}\n"
                'Vrať JSON pole: [{"id": "...", "domains": ["..."]}]')
        except QuotaExhausted as e:
            print(f"  dohledávání zastaveno: {e}")
            break
        except Exception as e:
            print(f"  ! AI chyba: {e}")
            continue
        by_id = {r.get("id"): r.get("domains") or [] for r in res if isinstance(r, dict)}
        for t in batch:
            t["guessed"] = True
            for d in by_id.get(t["id"], [])[:3]:
                d = urlparse(d if "//" in d else "https://" + d).netloc.removeprefix("www.")
                if not d or any(p in d for p in PORTALS):
                    continue
                r = _verify_home(d, t) if t["kind"] == "obec" else None
                if t["kind"] != "obec":
                    for url in (f"https://www.{d}", f"https://{d}"):
                        r = _get(url)
                        if r and _page_matches(r, t):
                            break
                        r = None
                if r:
                    t["website"] = r.url
                    links = find_career_links(r, r.url)
                    t["check_urls"] = links or ([r.url] if t["kind"] in ("škola", "obec", "instituce") else [])
                    found += 1
                    print(f"  ✓ {t['name']}: {t['website']}  {t['check_urls']}")
                    break
    print(f"Dohledáno {found} z {len(todo)} chybějících webů.")


def search_missing(targets, limit):
    """Dohledá web (a kariérní stránku) přes Gemini + Google Search (jen placený tarif)."""
    ai = AI()
    n = 0
    no_careers = lambda t: not t["check_urls"] or t["check_urls"] == [t["website"]]
    for t in sorted(targets, key=lambda t: (bool(t["website"]), t["km"] or 0)):
        if t.get("manual") or t.get("searched") or not (not t["website"] or no_careers(t)) or n >= limit:
            continue
        n += 1
        try:
            res = ai.search_json(
                f"Najdi oficiální webové stránky organizace „{t['name']}“ (IČO {t['ico']}, {t['place']}, Česko) "
                f"a pokud existuje, i stránku s nabídkou volných pracovních míst / kariéra. "
                f'Vrať JSON {{"website": "https://…", "careers": "https://… nebo prázdné"}}. Nevymýšlej si – '
                f"pokud si nejsi jistý, vrať prázdné hodnoty.")
        except QuotaExhausted as e:
            print(f"  vyhledávání zastaveno: {e}")
            break
        except Exception as e:
            print(f"  ! {t['name']}: {e}")
            continue
        t["searched"] = True
        site = (res.get("website") or "").strip() or t["website"]
        careers = (res.get("careers") or "").strip()
        if not site.startswith("http"):
            continue
        r = _get(site)
        if not r:
            continue
        t["website"] = t["website"] or r.url
        if careers.startswith("http") and not any(p in careers for p in PORTALS) and _get(careers):
            t["check_urls"] = [careers]
        elif not t["check_urls"]:
            links = find_career_links(r, r.url)
            t["check_urls"] = links or ([r.url] if t["kind"] in ("škola", "obec", "instituce") else [])
        print(f"  ✓ {t['name']}: {t['website']}  {t['check_urls']}")
    return n


def build(search=False, search_limit=150):
    prev = {}
    if TARGETS_FILE.exists():
        prev = {t["id"]: t for t in json.loads(TARGETS_FILE.read_text(encoding="utf-8"))}
    cands = candidates()
    print(f"Kandidátů: {len(cands)} (" + ", ".join(
        f"{k}: {sum(1 for c in cands if c['kind'] == k)}" for k in ("škola", "obec", "instituce", "firma")) + ")")
    with ThreadPoolExecutor(8) as pool:
        targets = list(pool.map(lambda c: discover(c, prev.get(c["id"])), cands))
    if MANUAL_FILE.exists():
        for m in json.loads(MANUAL_FILE.read_text(encoding="utf-8")):
            m.setdefault("enabled", True)
            m["manual"] = True
            targets = [t for t in targets if t["id"] != m["id"]] + [m]
    if search == "google":
        search_missing(targets, search_limit)
    elif search:
        guess_missing(targets, search_limit)
    targets.sort(key=lambda t: (t["kind"], t["km"] or 0, t["name"]))
    TARGETS_FILE.write_text(json.dumps(targets, ensure_ascii=False, indent=1), encoding="utf-8")
    with_site = sum(1 for t in targets if t["website"])
    with_check = sum(1 for t in targets if t["check_urls"])
    print(f"Uloženo {len(targets)} organizací, web nalezen u {with_site}, ke kontrole {with_check} → {TARGETS_FILE}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--search", action="store_true", help="dohledat chybějící weby (AI návrh domény + ověření)")
    p.add_argument("--google", action="store_true", help="dohledat přes Gemini + Google Search (placený tarif)")
    p.add_argument("--limit", type=int, default=150)
    a = p.parse_args()
    build(search="google" if a.google else a.search, search_limit=a.limit)
