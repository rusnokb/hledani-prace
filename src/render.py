"""Vygeneruje statickou stránku docs/index.html (GitHub Pages)."""
import json

from config import CONFIG, ROOT

OUT = ROOT / "docs" / "index.html"

FIELDS = ("id", "source", "title", "employer", "place", "km", "wage", "shift", "contract", "url", "description",
          "score", "category", "reason", "shift_risk", "first_seen", "last_seen", "status", "removed_on", "polish", "is_new")


def render(db):
    rows = [{k: x.get(k) for k in FIELDS if x.get(k) not in (None, "")} for x in db["listings"].values()]
    for r in rows:
        if r.get("description"):
            r["description"] = r["description"][:600]
    last = db["runs"][-1] if db["runs"] else {}
    payload = {
        "listings": rows,
        "lastRun": last,
        "prevRunDate": db["runs"][-2]["date"] if len(db["runs"]) > 1 else None,
        "minScore": CONFIG["min_score_to_show"],
        "radius": CONFIG["radius_km"],
        "home": CONFIG["home"]["name"],
    }
    data = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(TEMPLATE.replace("__DATA__", data), encoding="utf-8")
    (OUT.parent / ".nojekyll").write_text("", encoding="utf-8")
    return OUT


TEMPLATE = r"""<!doctype html>
<html lang="cs">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>Nabídky práce Nýdek</title>
<style>
:root{
  --bg:#f6f5f1; --surface:#ffffff; --surface-2:#efede7; --text:#1d1c1a; --muted:#6b675f; --line:#dedad1;
  --accent:#2f5d50; --accent-soft:#e1ece7; --new:#b4541f; --new-soft:#f7e6da;
  --good:#2f6b3a; --mid:#8a6a12; --low:#8c8780; --danger:#a33a2c;
  color-scheme: light;
}
@media (prefers-color-scheme: dark){
  :root:not([data-theme="light"]){
    --bg:#151614; --surface:#1e201d; --surface-2:#272a26; --text:#ecebe6; --muted:#a29e95; --line:#353832;
    --accent:#8cc2ae; --accent-soft:#233630; --new:#f0a46e; --new-soft:#3a2a1e;
    --good:#8fd19b; --mid:#e2c46a; --low:#8f8b84; --danger:#f08a7c; color-scheme: dark;
  }
}
:root[data-theme="dark"]{
  --bg:#151614; --surface:#1e201d; --surface-2:#272a26; --text:#ecebe6; --muted:#a29e95; --line:#353832;
  --accent:#8cc2ae; --accent-soft:#233630; --new:#f0a46e; --new-soft:#3a2a1e;
  --good:#8fd19b; --mid:#e2c46a; --low:#8f8b84; --danger:#f08a7c; color-scheme: dark;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:16px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
.wrap{max-width:980px;margin:0 auto;padding:24px 16px 64px}
header h1{font-size:1.6rem;margin:0 0 4px;letter-spacing:-.01em}
header p{margin:0;color:var(--muted);font-size:.93rem}
.stats{display:flex;gap:10px;flex-wrap:wrap;margin:18px 0 8px}
.stat{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:8px 14px;font-size:.9rem}
.stat b{font-size:1.15rem;margin-right:4px}
.tabs{display:flex;gap:4px;border-bottom:1px solid var(--line);margin:18px 0 14px;overflow-x:auto}
.tab{border:0;background:none;color:var(--muted);padding:10px 14px;font:inherit;cursor:pointer;border-bottom:2px solid transparent;white-space:nowrap}
.tab[aria-selected="true"]{color:var(--text);border-bottom-color:var(--accent);font-weight:600}
.filters{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:14px}
.filters input[type=search],.filters select{font:inherit;padding:8px 10px;border-radius:8px;border:1px solid var(--line);background:var(--surface);color:var(--text)}
.filters input[type=search]{flex:1 1 220px;min-width:0}
.chips{display:flex;gap:6px;flex-wrap:wrap}
.chip{font:inherit;font-size:.86rem;padding:5px 11px;border-radius:999px;border:1px solid var(--line);background:var(--surface);color:var(--text);cursor:pointer}
.chip[aria-pressed="true"]{background:var(--accent);border-color:var(--accent);color:var(--bg)}
label.check{font-size:.9rem;color:var(--muted);display:flex;align-items:center;gap:6px;cursor:pointer}
.list{display:grid;gap:10px}
.card{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:14px 16px;display:grid;grid-template-columns:auto 1fr;gap:4px 14px}
.card.dim{opacity:.55}
.score{grid-row:span 3;width:44px;height:44px;border-radius:10px;display:grid;place-items:center;font-weight:700;font-size:1.1rem;background:var(--surface-2)}
.score.s-good{color:var(--good)} .score.s-mid{color:var(--mid)} .score.s-low{color:var(--low)}
.card h2{font-size:1.05rem;margin:0;line-height:1.3}
.card h2 a{color:inherit;text-decoration:none} .card h2 a:hover{text-decoration:underline}
.meta{color:var(--muted);font-size:.88rem;display:flex;gap:4px 12px;flex-wrap:wrap}
.reason{font-size:.92rem;margin:2px 0 0}
.badge{display:inline-block;font-size:.72rem;font-weight:700;letter-spacing:.04em;text-transform:uppercase;padding:2px 7px;border-radius:5px;margin-right:6px;vertical-align:2px}
.b-new{background:var(--new-soft);color:var(--new)} .b-cat{background:var(--accent-soft);color:var(--accent)}
.b-warn{background:var(--new-soft);color:var(--danger)} .b-gone{background:var(--surface-2);color:var(--muted)}
details{grid-column:2;font-size:.88rem;color:var(--muted)} details summary{cursor:pointer}
.actions{grid-column:2;display:flex;gap:6px;flex-wrap:wrap;margin-top:6px}
.actions button,.actions a{font:inherit;font-size:.82rem;padding:4px 10px;border-radius:7px;border:1px solid var(--line);background:none;color:var(--text);cursor:pointer;text-decoration:none}
.actions a.primary{background:var(--accent);border-color:var(--accent);color:var(--bg)}
.actions button[aria-pressed="true"]{background:var(--surface-2);font-weight:600}
.empty{color:var(--muted);padding:30px 0;text-align:center}
.more{margin:16px 0;text-align:center} .more button{font:inherit;padding:8px 14px;border-radius:8px;border:1px solid var(--line);background:var(--surface);color:var(--text);cursor:pointer}
footer{margin-top:36px;color:var(--muted);font-size:.82rem}
@media (max-width:560px){.card{grid-template-columns:1fr}.score{grid-row:auto;width:auto;height:auto;padding:2px 8px;justify-self:start}details,.actions{grid-column:1}}
</style>
</head>
<body>
<div class="wrap">
<header>
  <h1>Nabídky práce v okolí Nýdku</h1>
  <p id="sub"></p>
</header>
<div class="stats" id="stats"></div>
<div class="tabs" role="tablist" id="tabs"></div>
<div class="filters">
  <input type="search" id="q" placeholder="Hledat pozici, firmu, obec…" aria-label="Hledat">
  <select id="sort" aria-label="Řazení">
    <option value="score">Nejvhodnější</option>
    <option value="new">Nejnovější</option>
    <option value="km">Nejblíže</option>
  </select>
  <label class="check"><input type="checkbox" id="hideNo"> skrýt „nezajímá“</label>
</div>
<div class="chips" id="cats" style="margin-bottom:14px"></div>
<div class="list" id="list"></div>
<div class="more" id="more"></div>
<footer id="foot"></footer>
</div>
<script id="data" type="application/json">__DATA__</script>
<script>
const D = JSON.parse(document.getElementById('data').textContent);
const store = {
  get(){ try { return JSON.parse(localStorage.getItem('jobmarks')||'{}'); } catch(e){ return {}; } },
  set(v){ try { localStorage.setItem('jobmarks', JSON.stringify(v)); } catch(e){} }
};
let marks = store.get();
const lastDate = D.lastRun && D.lastRun.date;
const isNew = x => x.status === 'active' && x.is_new;
const fmtDate = s => s ? new Date(s + 'T12:00:00').toLocaleDateString('cs-CZ') : '';
const state = { tab: 'active', cat: null, showLow: false };
const tabs = [
  ['new', 'Nové od minula'], ['active', 'Všechny aktivní'], ['mine', 'Moje označené'], ['removed', 'Archiv (smazané)']
];
const cats = ['Školství', 'Administrativa', 'Veřejná správa', 'Polština', 'Jiné'];
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

const active = D.listings.filter(x => x.status === 'active');
const good = active.filter(x => (x.score ?? 99) >= D.minScore);
document.getElementById('sub').textContent =
  `Do ${D.radius} km od obce ${D.home} · bez obchodních zástupců a směnného provozu · aktualizace 2× týdně` +
  (lastDate ? ` · poslední kontrola ${fmtDate(lastDate)}` : '');
document.getElementById('stats').innerHTML = [
  [good.length, 'vhodných aktivních'], [good.filter(isNew).length, 'nových od minula'],
  [D.listings.filter(x => x.status === 'removed').length, 'v archivu']
].map(([n, l]) => `<div class="stat"><b>${n}</b>${l}</div>`).join('');

function renderTabs(){
  document.getElementById('tabs').innerHTML = tabs.map(([k, l]) =>
    `<button class="tab" role="tab" aria-selected="${state.tab === k}" data-tab="${k}">${l}</button>`).join('');
  document.getElementById('cats').innerHTML = [null, ...cats].map(c =>
    `<button class="chip" aria-pressed="${state.cat === c}" data-cat="${c ?? ''}">${c ?? 'Vše'}</button>`).join('');
}
function scoreClass(s){ return s == null ? '' : s >= 7 ? 's-good' : s >= 5 ? 's-mid' : 's-low'; }
function card(x){
  const m = marks[x.id];
  const meta = [x.employer, x.place && (x.place + (x.km != null ? ` (${x.km} km)` : '')), x.wage, x.contract, x.shift, x.source]
    .filter(Boolean).map(esc).map(s => `<span>${s}</span>`).join('');
  const badges = (isNew(x) ? '<span class="badge b-new">Nové</span>' : '') +
    (x.status === 'removed' ? `<span class="badge b-gone">Smazáno ${fmtDate(x.removed_on)}</span>` : '') +
    (x.category ? `<span class="badge b-cat">${esc(x.category)}</span>` : '') +
    (x.shift_risk ? '<span class="badge b-warn">Ověřit směny</span>' : '');
  const btn = (k, l) => `<button data-mark="${k}" data-id="${esc(x.id)}" aria-pressed="${m === k}">${l}</button>`;
  return `<article class="card ${m === 'no' ? 'dim' : ''}">
    <div class="score ${scoreClass(x.score)}" title="Vhodnost 0–10">${x.score ?? '–'}</div>
    <h2>${badges}<a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.title)}</a></h2>
    <div class="meta">${meta}</div>
    <p class="reason">${esc(x.reason || (x.score == null ? 'Zatím neohodnoceno AI.' : ''))}</p>
    ${x.description ? `<details><summary>Popis</summary>${esc(x.description)}</details>` : ''}
    <div class="actions">
      <a class="primary" href="${esc(x.url)}" target="_blank" rel="noopener">Otevřít nabídku</a>
      ${btn('like', '★ Zájem')}${btn('sent', '✉ Odesláno')}${btn('no', 'Nezajímá')}
      <span style="color:var(--muted);font-size:.8rem;align-self:center">přidáno ${fmtDate(x.first_seen)}</span>
    </div>
  </article>`;
}
function renderList(){
  const q = document.getElementById('q').value.trim().toLowerCase();
  const hideNo = document.getElementById('hideNo').checked;
  let rows = D.listings.filter(x =>
    state.tab === 'removed' ? x.status === 'removed' :
    state.tab === 'mine' ? marks[x.id] && marks[x.id] !== 'no' :
    state.tab === 'new' ? isNew(x) : x.status === 'active');
  if (state.cat) rows = rows.filter(x => (x.category || 'Jiné') === state.cat);
  if (q) rows = rows.filter(x => [x.title, x.employer, x.place, x.description, x.reason].join(' ').toLowerCase().includes(q));
  if (hideNo) rows = rows.filter(x => marks[x.id] !== 'no');
  const sort = document.getElementById('sort').value;
  rows.sort(sort === 'km' ? (a, b) => (a.km ?? 99) - (b.km ?? 99) :
            sort === 'new' ? (a, b) => (b.first_seen || '').localeCompare(a.first_seen || '') :
            (a, b) => (b.score ?? 99) - (a.score ?? 99));
  const low = state.tab === 'mine' ? [] : rows.filter(x => x.score != null && x.score < D.minScore);
  const shown = state.showLow ? rows : rows.filter(x => !low.includes(x));
  document.getElementById('list').innerHTML = shown.length ? shown.map(card).join('') :
    `<div class="empty">${state.tab === 'new' ? (D.prevRunDate ? 'Od minulé kontroly nepřibylo nic nového.' : 'Toto je první běh – všechny nabídky najdete v záložce Všechny aktivní.') : 'Nic tu není.'}</div>`;
  document.getElementById('more').innerHTML = low.length ?
    `<button id="toggleLow">${state.showLow ? 'Skrýt méně vhodné' : `Zobrazit i méně vhodné (${low.length})`}</button>` : '';
}
document.addEventListener('click', e => {
  const t = e.target.closest('[data-tab],[data-cat],[data-mark],#toggleLow');
  if (!t) return;
  if (t.dataset.tab) { state.tab = t.dataset.tab; state.showLow = false; renderTabs(); }
  else if ('cat' in t.dataset) { state.cat = t.dataset.cat || null; renderTabs(); }
  else if (t.dataset.mark) { const id = t.dataset.id; marks[id] = marks[id] === t.dataset.mark ? undefined : t.dataset.mark; if (!marks[id]) delete marks[id]; store.set(marks); }
  else if (t.id === 'toggleLow') state.showLow = !state.showLow;
  renderList();
});
['q', 'sort', 'hideNo'].forEach(id => document.getElementById(id).addEventListener('input', renderList));
if (D.prevRunDate && good.some(isNew)) state.tab = 'new';
renderTabs(); renderList();
const r = D.lastRun || {};
document.getElementById('foot').innerHTML = `Zdroje: otevřená data Úřadu práce ČR a weby ${r.web_targets ?? 0} zaměstnavatelů v okolí. ` +
  `Hodnocení vhodnosti (0–10) dělá AI podle životopisu – berte ho jako vodítko. Značky „Zájem / Odesláno“ se ukládají jen v tomto prohlížeči.`;
</script>
</body>
</html>
"""
