import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)

# lokálně: klíče v souboru .env (není v gitu); na GitHubu: Secrets
_env = ROOT / ".env"
if _env.exists():
    for line in _env.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"'))

CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))

# profil ze životopisu: lokálně profil.md, na GitHubu secret PROFIL_MD (repo je veřejné)
_profile = ROOT / "profil.md"
PROFILE = _profile.read_text(encoding="utf-8") if _profile.exists() else os.environ.get("PROFIL_MD", "")
