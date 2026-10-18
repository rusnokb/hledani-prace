import re
import unicodedata

import requests

from config import CONFIG

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) job-seeker/1.0 (osobni hledani prace, 2x tydne)"

session = requests.Session()
session.headers.update({"User-Agent": UA, "Accept-Language": "cs,en;q=0.5"})


def fold(text):
    """Malá písmena bez diakritiky – pro porovnávání klíčových slov."""
    text = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


_EXCLUDE = [fold(k) for k in CONFIG["exclude_keywords"]]
_OZ = re.compile(r"\bOZ\b")  # zkratka obchodního zástupce (ne "OZP")


def excluded_reason(*texts):
    """Vrátí důvod vyřazení podle klíčových slov, nebo None."""
    joined = " ".join(t or "" for t in texts)
    folded = fold(joined)
    for kw in _EXCLUDE:
        if kw in folded:
            return f"klíčové slovo „{kw}“"
    if _OZ.search(joined):
        return "obchodní zástupce (OZ)"
    return None


def clean_ws(text):
    return re.sub(r"\s+", " ", text or "").strip()
