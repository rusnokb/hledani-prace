# Hledání práce – okolí Nýdku

Aplikace 2× týdně (po + čt ráno) projde nabídky práce v okruhu 33 km od Nýdku, vyřadí obchodní zástupce
a směnný provoz, nechá AI ohodnotit vhodnost podle životopisu a výsledek zveřejní jako webovou stránku.

## Odkud bere nabídky

| Zdroj | Co obsahuje |
|---|---|
| Otevřená data Úřadu práce ČR | všechna volná místa nahlášená na ÚP (včetně škol a úřadů), denně aktualizovaná, s údajem o směnnosti |
| Weby organizací v okolí | školy (z rejstříku škol MŠMT), obce a města, instituce (knihovny, muzea, sociální služby…) a firmy s 50+ zaměstnanci (z registru ČSÚ) – kariérní stránky, „volná místa“, „výběrová řízení“ |

Seznam organizací je v `data/targets.json` a obnovuje se automaticky jednou za čtvrt roku.

## Jak to funguje

1. **Sběr:** stáhne data ÚP a projde kariérní stránky organizací.
2. **Tvrdý filtr:** vzdálenost, směnnost (z dat ÚP), zakázaná slova (obchodní zástupce, akvizice, třísměnný…).
3. **AI (Gemini, bezplatný tarif):** z webů vytáhne jednotlivé nabídky a každé dá skóre 0–10 se zdůvodněním.
   Web se AI posílá jen tehdy, když se od minula změnil a obsahuje slova typická pro nabídky práce.
4. **Porovnání s minulým během:** nové nabídky se označí „Nové“. Nabídka, která chybí 2× po sobě, jde do archivu
   (a po 60 dnech zmizí úplně). Když nějaký web zrovna nejde načíst, nic se nemaže.
5. **Stránka:** `docs/index.html`, publikovaná přes GitHub Pages.

## Úpravy

- **`config.json`:** okruh (`radius_km`), zakázaná slova (`exclude_keywords`), vyřazené směny, minimální skóre pro zobrazení.
- **`profil.md`:** shrnutí životopisu a co hledá/nechce. Lokálně je to soubor; na GitHubu je uložený jako tajná
  hodnota `PROFIL_MD`, protože repozitář je veřejný. Po úpravě je potřeba aktualizovat i secret.
- **`manual_targets.json`:** vlastní organizace navíc, např.:
  ```json
  [{"id": "moje-1", "name": "Název firmy", "kind": "firma", "place": "Třinec", "km": 9,
    "website": "https://firma.cz", "check_urls": ["https://firma.cz/kariera"]}]
  ```
- Organizaci vypnete v `data/targets.json` nastavením `"enabled": false`.

## Ruční spuštění

Na GitHubu: záložka **Actions** → „Hledání nabídek práce“ → **Run workflow**.

Lokálně (Windows):
```
.venv\Scripts\python -X utf8 src\main.py
.venv\Scripts\python -X utf8 src\targets.py --search   # obnova seznamu organizací
```

## Omezení

- Weby, které načítají nabídky až JavaScriptem, aplikace nepřečte. Takové firmy ale často inzerují i na ÚP.
- Bezplatný tarif Gemini má denní limity. Když dojdou, zbytek se dokončí při dalším běhu.
- Velké portály (Jobs.cz, Prace.cz) se nestahují, protože to jejich podmínky zakazují. Většina místních
  zaměstnavatelů ale inzeruje i na ÚP nebo na svém webu.
