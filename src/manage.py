"""Přidání / odebrání webu ze seznamu kontrolovaných zdrojů.

    python manage.py pridat https://firma.cz/kariera --nazev "Firma s.r.o." --obec Třinec
    python manage.py odebrat <id nebo adresa>
    python manage.py issue telo_pozadavku.txt     # požadavek z GitHub Issues (formulář na stránce)

Vypíše zprávu o výsledku (použije se jako komentář k požadavku)."""
import argparse
import json
import re
import sys
from datetime import date
from urllib.parse import urlparse

import render
import state
from geo import load_obce
from sources.careers import TARGETS_FILE
from targets import MANUAL_FILE, _get, find_career_links
from util import clean_ws, fold


def _load(path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def _save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def _host(url):
    return urlparse(url).netloc.lower().removeprefix("www.")


def _normalize(url):
    url = url.strip().strip("<>")
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def add(url, name="", place=""):
    url = _normalize(url)
    host = _host(url)
    if not host or "." not in host:
        return False, f"Neplatná adresa: {url}"
    targets = _load(TARGETS_FILE)
    manual = _load(MANUAL_FILE)

    # už v seznamu? → zapnout / doplnit stránku
    for t in targets:
        hosts = {_host(u) for u in [t.get("website", "")] + t.get("check_urls", []) if u}
        if host in hosts:
            msg = []
            if not t.get("enabled", True):
                t["enabled"] = True
                msg.append("znovu zapnut")
            path = urlparse(url).path.strip("/")
            if path and url not in t.get("check_urls", []):
                t["check_urls"] = (t.get("check_urls") or [])[:2] + [url]
                msg.append(f"přidána stránka {url}")
            for m in manual:
                if m["id"] == t["id"]:
                    m.update({k: t[k] for k in ("enabled", "check_urls")})
            _save(TARGETS_FILE, targets)
            _save(MANUAL_FILE, manual)
            return True, f"„{t['name']}“ už v seznamu je" + (f" – {', '.join(msg)}." if msg else " a kontroluje se.")

    r = _get(url)
    if not r:
        return False, f"Stránku {url} se nepodařilo načíst – zkontrolujte adresu."
    if not name:
        title = re.search(r"<title[^>]*>(.*?)</title>", r.text, re.I | re.S)
        name = clean_ws(re.split(r"\s[|\-–]\s", title.group(1))[0]) if title else host
    km = None
    if place:
        hit = [o for o in load_obce().values() if fold(o["nazev"]) == fold(place)]
        if hit:
            place, km = hit[0]["nazev"], hit[0]["km"]
    is_home = urlparse(r.url).path.strip("/") == ""
    check = (find_career_links(r, r.url) if is_home else []) or [r.url]
    t = {"id": "m-" + re.sub(r"[^a-z0-9]+", "-", host), "ico": "", "name": name, "kind": "vlastní",
         "place": place, "km": km, "polish": False, "website": f"https://{urlparse(r.url).netloc}/",
         "check_urls": check, "enabled": True, "manual": True, "added": date.today().isoformat()}
    manual = [m for m in manual if m["id"] != t["id"]] + [t]
    targets = [x for x in targets if x["id"] != t["id"]] + [t]
    _save(MANUAL_FILE, manual)
    _save(TARGETS_FILE, targets)
    return True, f"Přidáno: „{name}“ – kontrolovat se bude {', '.join(check)}. Projde se při nejbližším běhu."


def remove(key):
    key = key.strip()
    targets = _load(TARGETS_FILE)
    manual = _load(MANUAL_FILE)
    host = _host(_normalize(key)) if "." in key else None
    hit = [t for t in targets if t["id"] == key or (host and host in
           {_host(u) for u in [t.get("website", "")] + t.get("check_urls", []) if u})]
    if not hit:
        return False, f"V seznamu jsem nenašel „{key}“."
    names = []
    for t in hit:
        names.append(t["name"])
        if t.get("manual"):
            targets = [x for x in targets if x["id"] != t["id"]]
            manual = [m for m in manual if m["id"] != t["id"]]
        else:
            t["enabled"] = False  # automaticky nalezené: jen vypnout, aby se při obnově seznamu nevrátilo
    _save(TARGETS_FILE, targets)
    _save(MANUAL_FILE, manual)
    # nabídky z odebraného webu hned přesunout do archivu
    db = state.load()
    gone = 0
    for x in db["listings"].values():
        if x.get("status") == "active" and any(x.get("source_key") == f"web:{t['id']}" for t in hit):
            x["status"], x["removed_on"] = "removed", date.today().isoformat()
            gone += 1
    state.save(db)
    msg = "Odebráno: " + ", ".join(names)
    if gone:
        msg += f" ({gone} nabídek přesunuto do archivu)"
    return True, msg if msg.endswith(".") else msg + "."


def from_issue(body):
    fields = {}
    for line in body.splitlines():
        m = re.match(r"\s*([a-zA-Zá-ž]+)\s*:\s*(.*)$", line)
        if m:
            fields[fold(m.group(1))] = m.group(2).strip()
    action = fold(fields.get("akce", ""))
    if action == "pridat" and fields.get("url"):
        return add(fields["url"], fields.get("nazev", ""), fields.get("obec", ""))
    if action == "odebrat" and (fields.get("id") or fields.get("url")):
        return remove(fields.get("id") or fields["url"])
    return False, "Požadavek nemá očekávaný tvar (akce: pridat/odebrat, url: …)."


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("pridat")
    a.add_argument("url")
    a.add_argument("--nazev", default="")
    a.add_argument("--obec", default="")
    r = sub.add_parser("odebrat")
    r.add_argument("klic")
    i = sub.add_parser("issue")
    i.add_argument("soubor")
    args = p.parse_args()
    if args.cmd == "pridat":
        ok, msg = add(args.url, args.nazev, args.obec)
    elif args.cmd == "odebrat":
        ok, msg = remove(args.klic)
    else:
        with open(args.soubor, encoding="utf-8") as f:
            ok, msg = from_issue(f.read())
    if ok:
        render.render(state.load())
    print(msg)
    sys.exit(0 if ok else 1)
