"""Obce v okolí domova a jejich vzdálenost (vzdušnou čarou) z RÚIAN (ČÚZK)."""
import json
import math
from pathlib import Path

import requests

from config import CONFIG, DATA_DIR

RUIAN_OBCE = "https://ags.cuzk.cz/arcgis/rest/services/RUIAN/MapServer/12/query"
OBCE_FILE = DATA_DIR / "obce.json"


def haversine_km(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _ring_centroid(ring):
    # těžiště polygonu (dostatečně přesné pro malé plochy v lon/lat)
    a = cx = cy = 0.0
    for (x0, y0), (x1, y1) in zip(ring, ring[1:]):
        f = x0 * y1 - x1 * y0
        a += f
        cx += (x0 + x1) * f
        cy += (y0 + y1) * f
    if abs(a) < 1e-12:
        xs, ys = zip(*ring)
        return sum(xs) / len(xs), sum(ys) / len(ys), 0.0
    return cx / (3 * a), cy / (3 * a), abs(a / 2)


def build_obce():
    home = CONFIG["home"]
    params = {
        "geometry": f"{home['lon']},{home['lat']}",
        "geometryType": "esriGeometryPoint",
        "inSR": 4326,
        "spatialRel": "esriSpatialRelIntersects",
        "distance": int((CONFIG["radius_km"] + 15) * 1000),
        "units": "esriSRUnit_Meter",
        "outFields": "kod,nazev,okres",
        "returnGeometry": "true",
        "outSR": 4326,
        "maxAllowableOffset": 0.002,
        "f": "json",
    }
    resp = requests.get(RUIAN_OBCE, params=params, timeout=120)
    resp.raise_for_status()
    obce = {}
    for f in resp.json()["features"]:
        rings = f["geometry"]["rings"]
        lon, lat, _ = max((_ring_centroid(r) for r in rings), key=lambda c: c[2])
        a = f["attributes"]
        obce[str(a["kod"])] = {
            "nazev": a["nazev"],
            "okres": a["okres"],
            "lat": round(lat, 5),
            "lon": round(lon, 5),
            "km": round(haversine_km(home["lat"], home["lon"], lat, lon), 1),
        }
    OBCE_FILE.write_text(json.dumps(obce, ensure_ascii=False, indent=1), encoding="utf-8")
    return obce


def load_obce():
    if not OBCE_FILE.exists():
        return build_obce()
    return json.loads(OBCE_FILE.read_text(encoding="utf-8"))


if __name__ == "__main__":
    o = build_obce()
    for kod, v in sorted(o.items(), key=lambda kv: kv[1]["km"]):
        print(f"{v['km']:5.1f} km  {v['nazev']}  ({kod}, okres {v['okres']})")
