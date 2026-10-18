"""Nabídky přímo z webů firem, škol a úřadů v okolí (kariérní stránky, úřední desky).

Každá stránka se stáhne; AI se volá jen tehdy, když se text od minula změnil
a obsahuje slova typická pro nabídky práce. Jinak se použije výsledek z minula."""
import hashlib
import json
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from ai import QuotaExhausted
from config import DATA_DIR
from util import clean_ws, excluded_reason, fold, session

TARGETS_FILE = DATA_DIR / "targets.json"
CACHE_FILE = DATA_DIR / "web_cache.json"
MAX_CHARS = 14000
MAX_DEPTH = 1  # kolik úrovní podstránek (rozcestníků) projít

JOB_WORDS = [fold(w) for w in (
    "volné místo", "volná místa", "volné pracovní", "pracovní místo", "pracovní místa", "přijme", "přijmeme",
    "hledáme", "nabídka práce", "nabídky práce", "kariéra", "výběrové řízení", "výběrová řízení",
    "zaměstnání", "pracovní příležitost", "obsadí", "pozice", "přidej se", "připoj se", "jobs", "career",
)]

PROMPT = """Níže je text webové stránky organizace „{name}“ ({place}). Najdi v něm AKTUÁLNÍ nabídky
zaměstnání (volná pracovní místa, výběrová řízení na zaměstnance). Ignoruj nabídky pro žáky, brigády
pro studenty jen tehdy, pokud jsou jasně jen pro studenty, zakázky, prodej, akce a zprávy, které nejsou
nabídkou práce. Ignoruj nabídky, u kterých text uvádí, že už jsou obsazené nebo ukončené.
Odkazy jsou ve tvaru [text](url) – pokud má nabídka vlastní odkaz, uveď ho.

Vrať JSON: {{"listings": [{{"title": "název pozice", "url": "odkaz na detail nebo prázdné",
"place": "místo výkonu, pokud je uvedeno", "contract": "HPP/zkrácený/DPP… pokud uvedeno",
"shift": "údaj o směnnosti/pracovní době, pokud uveden", "description": "shrnutí požadavků a náplně, max 60 slov"}}],
"more_pages": ["max 3 odkazy na podstránky téhož webu, kde jsou nabídky práce vypsány (rozcestník kategorií,
seznam volných míst, další stránka výpisu) – jen pokud tato stránka samotná nabídky nevypisuje celé"]}}
Pokud žádná nabídka není, vrať {{"listings": [], "more_pages": []}}.

TEXT STRÁNKY ({url}):
{text}"""


def load_targets():
    if not TARGETS_FILE.exists():
        return []
    return [t for t in json.loads(TARGETS_FILE.read_text(encoding="utf-8")) if t.get("enabled", True)]


def _load_cache():
    if CACHE_FILE.exists():
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    return {}


def _save_cache(cache):
    CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")


def page_text(html, base_url):
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "iframe", "form"]):
        tag.decompose()
    for tag in soup.select("header, footer, nav, [role=navigation], .cookie, #cookie, .cookies"):
        tag.decompose()
    for a in soup.find_all("a", href=True):
        label = clean_ws(a.get_text(" "))
        if label:
            a.replace_with(f" [{label}]({urljoin(base_url, a['href'])}) ")
    body = soup.body or soup
    total = len(clean_ws(body.get_text(" ")))
    main = body
    for cand in (soup.find("main"), soup.find(id=re.compile(r"^(main|content|obsah)", re.I))):
        # <main> bereme jen tehdy, když opravdu obsahuje většinu textu stránky
        if cand is not None and len(clean_ws(cand.get_text(" "))) >= 0.4 * total:
            main = cand
            break
    text = "\n".join(clean_ws(line) for line in main.get_text("\n").splitlines())
    return re.sub(r"\n{2,}", "\n", text).strip()


FOCUS_WORDS = JOB_WORDS + ["ucitel", "nastup", "pozic", "pracovnik", "pracovnici", "referent", "uvazek"]


def focus_text(text, limit=MAX_CHARS, window=1200):
    """Dlouhé stránky (mega-menu, patičky) zkrátí na začátek + okolí slov typických pro nabídky."""
    if len(text) <= limit:
        return text
    f = fold(text)  # fold zachovává délku (jen odstraní diakritiku) u běžného českého textu
    if len(f) != len(text):
        return text[:limit]
    spans = [(0, 2500)]
    for w in FOCUS_WORDS:
        for m in re.finditer(re.escape(w), f):
            spans.append((max(0, m.start() - window), m.end() + window))
    spans.sort()
    merged = []
    for s, e in spans:
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    out, size = [], 0
    for s, e in merged:
        chunk = text[s:e]
        if size + len(chunk) > limit:
            chunk = chunk[: limit - size]
        out.append(chunk)
        size += len(chunk)
        if size >= limit:
            break
    return "\n…\n".join(out)


def _has_job_words(text):
    f = fold(text)
    return any(w in f for w in JOB_WORDS)


def fetch(ai, log=print):
    """Vrací (listingy, množina úspěšně načtených source_key, stav jednotlivých organizací)."""
    targets = load_targets()
    cache = _load_cache()
    out, ok, status = [], set(), {}
    ai_skipped = 0
    seen_pages = {}  # url -> název organizace, která ji kontroluje
    for n, t in enumerate(targets, 1):
        if n % 50 == 0:
            log(f"  … {n}/{len(targets)} organizací, AI volání: {ai.calls}")
        key = f"web:{t['id']}"
        pages = frozenset(u.strip() for u in t.get("check_urls", []))
        if pages and pages <= set(seen_pages):  # stejná kariérní stránka jako jiná firma ze skupiny
            ok.add(key)
            status[t["id"]] = {"ok": True, "listings": 0, "shared": seen_pages[next(iter(pages))]}
            continue
        for u in pages:
            seen_pages.setdefault(u, t["name"])
        found = []
        failed = False
        queue = [(u.strip(), 0) for u in t.get("check_urls", [])]
        visited = set()
        while queue:
            url, depth = queue.pop(0)
            if url in visited:
                continue
            visited.add(url)
            try:
                r = session.get(url, timeout=30)
                if r.status_code in (404, 410):  # stránka zrušena = nabídky tam už nejsou
                    cache[url] = {"hash": "gone", "listings": []}
                    continue
                r.raise_for_status()
                r.encoding = r.apparent_encoding if r.encoding in (None, "ISO-8859-1") else r.encoding
                text = focus_text(page_text(r.text, r.url))
            except Exception as e:
                log(f"  ! {t['name']}: {url} nelze načíst ({e.__class__.__name__})")
                failed = True
                continue
            h = hashlib.sha1(text.encode("utf-8")).hexdigest()
            prev = cache.get(url)
            if prev and prev["hash"] == h:
                found.extend(dict(i, page=url) for i in prev["listings"])
                if depth < MAX_DEPTH:
                    queue += [(m, depth + 1) for m in prev.get("more", [])]
                continue
            if not _has_job_words(text):
                cache[url] = {"hash": h, "listings": []}
                continue
            if not ai.available_for_web:
                ai_skipped += 1
                if prev:
                    found.extend(dict(i, page=url) for i in prev["listings"])  # zkusíme příště
                else:
                    failed = True  # nepotvrzeno – nic nemazat
                continue
            try:
                res = ai.json(PROMPT.format(name=t["name"], place=t.get("place", ""), url=url, text=text),
                              max_tokens=8192)
            except QuotaExhausted:
                ai_skipped += 1
                failed = True
                if prev:
                    found.extend(dict(i, page=url) for i in prev["listings"])
                continue
            except Exception as e:
                log(f"  ! {t['name']}: AI chyba ({e})")
                failed = True
                continue
            items = [i for i in res.get("listings", []) if clean_ws(i.get("title"))]
            for i in items:
                i["url"] = urljoin(url, i["url"]) if i.get("url") else url
            host = urlparse(url).netloc
            more = [urljoin(url, m) for m in res.get("more_pages", []) if isinstance(m, str)]
            more = [m for m in more if urlparse(m).netloc == host and m != url][:3]
            cache[url] = {"hash": h, "listings": items, "more": more}
            found.extend(dict(i, page=url) for i in items)
            if depth < MAX_DEPTH:
                queue += [(m, depth + 1) for m in more]
        if not failed:
            ok.add(key)
        before = len(out)
        for i in found:
            title = clean_ws(i.get("title"))
            if excluded_reason(title, i.get("shift"), i.get("description")):
                continue
            uid = hashlib.sha1(f"{fold(title)}|{i.get('url')}".encode("utf-8")).hexdigest()[:10]
            out.append({
                "id": f"web:{t['id']}:{uid}",
                "source_key": key,
                "source": "Web zaměstnavatele",
                "title": title,
                "employer": t["name"],
                "place": clean_ws(i.get("place")) or t.get("place", ""),
                "km": t.get("km"),
                "wage": "",
                "shift": clean_ws(i.get("shift")),
                "contract": clean_ws(i.get("contract")),
                "url": i.get("url") or t["check_urls"][0],
                "source_url": i.get("page") or t["check_urls"][0],
                "description": clean_ws(i.get("description")),
            })
        if t.get("check_urls"):
            status[t["id"]] = {"ok": not failed, "listings": len(out) - before}
    _save_cache(cache)
    if ai_skipped:
        log(f"  Weby: {ai_skipped} změněných stránek čeká na AI (limit) – dokončí se příště.")
    # stejná nabídka může být na více stránkách jedné organizace
    uniq = {x["id"]: x for x in out}
    return list(uniq.values()), ok, status
