#!/usr/bin/env python3
"""Baut eine statische Vorschau (eine HTML-Datei) der Startseite mit funktionierendem Produktfinder.

Die Produktdaten kommen aus import/produkte-woocommerce.csv und werden in das Format
der WooCommerce Store API umgewandelt, damit assets/finder.js unverändert läuft.

Aufruf: python3 werkzeuge/build_preview.py  ->  vorschau/index.html
"""
import base64
import csv
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
THEME = ROOT / "wp-content/themes/beinundfuss"
PLUGIN = ROOT / "wp-content/plugins/beinundfuss-shop"
OUT = ROOT / "vorschau/index.html"

FINDER = ["Anwendung", "Funktion", "Bauform", "Material", "Rohrmaß", "Gewinde", "Fußform", "Anschluss", "Bodenbefestigung"]


def store_api_produkte():
    rows = []
    for datei in ("produkte-woocommerce.csv", "vergleichsprodukte-woocommerce.csv"):
        pfad = ROOT / "import" / datei
        if pfad.exists():
            rows += list(csv.DictReader(pfad.open(encoding="utf-8")))
    preise = {}
    for r in rows:
        if r["Type"] == "variation" and r["Regular price"]:
            preise.setdefault(r["Parent"], []).append(round(float(r["Regular price"]) * 100))
    out = []
    for i, r in enumerate(x for x in rows if x["Type"] != "variation"):
        attrs = []
        for n in range(1, 20):
            name = r.get(f"Attribute {n} name")
            if name in FINDER:
                attrs.append({"name": name, "terms": [{"name": v.strip()} for v in r[f"Attribute {n} value(s)"].split(",")]})
        p = preise.get(r["SKU"])
        out.append({
            "id": i + 1,
            "name": r["Name"],
            "permalink": "#produkt-" + r["SKU"],
            "images": [],
            "attributes": attrs,
            "prices": {
                "currency_code": "EUR", "currency_minor_unit": 2,
                "price": str(min(p)) if p else "",
                "price_range": {"min_amount": str(min(p)), "max_amount": str(max(p))} if p else None,
            },
        })
    return out


def pattern_html(name):
    """Führt die einfachen PHP-Muster für die Vorschau grob aus (Schleifen über Arrays)."""
    return (THEME / "patterns" / f"{name}.php").read_text(encoding="utf-8")


def data_uri(path):
    return "data:image/jpeg;base64," + base64.b64encode(path.read_bytes()).decode()


def main():
    css_theme = (THEME / "style.css").read_text(encoding="utf-8")
    css_theme = re.sub(r"/\*.*?\*/", "", css_theme, count=1, flags=re.S)
    css_finder = (PLUGIN / "assets/finder.css").read_text(encoding="utf-8")
    js_finder = (PLUGIN / "assets/finder.js").read_text(encoding="utf-8")
    produkte = store_api_produkte()
    global TS_ANZAHL
    TS_ANZAHL = sum(1 for p in produkte if not p["permalink"].startswith("#produkt-BF-V-"))

    welten = re.findall(r"array\( '([^']+)', '([^']+)', '([^']+)' \)", pattern_html("produktwelten"))
    anwendungen = re.findall(r"array\( '([^']+)', '([^']+)' \)", pattern_html("anwendungen"))
    vorteile = re.findall(r"array\( '([^']+)', '(<[^']+)' \)", pattern_html("vorteile"))

    kacheln = "".join(
        f'<div class="bf-kachel"><a href="#finder"><h3>{html.escape(n)}</h3><p>{html.escape(t)}</p></a></div>'
        for _, n, t in welten)
    anw = "".join(
        f'<div class="bf-kachel"><a href="#finder" data-anwendung="{html.escape(a)}"><h3><span class="bf-nummer">{i + 1}</span>{html.escape(t)}</h3>'
        f'<img loading="lazy" src="{data_uri(THEME / "assets/anwendungen" / f"anwendung-{i + 1:02d}.jpg")}" alt=""></a></div>'
        for i, (t, a) in enumerate(anwendungen))
    band = "".join(f'<div class="bf-band-item"><svg viewBox="0 0 24 24" aria-hidden="true">{svg}</svg><span>{html.escape(t)}</span></div>'
                   for t, svg in vorteile)

    seite = f"""<title>beinundfuß.de Shopvorschau</title>
<style>
:root {{ --wp--preset--color--navy:#1b2836; --wp--preset--color--gruen:#4fa82e; --wp--preset--color--gruen-dunkel:#3d8a22; --wp--preset--color--grau:#8b939b; --wp--preset--color--grau-dunkel:#4a5560; --wp--preset--color--hell:#f2f4f6; color-scheme: light; }}
html {{ background:#fff; }}
* {{ box-sizing: border-box; }}
body {{ margin:0; background:#fff; color:#1b2836; font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif; }}
h1,h2,h3 {{ font-weight:800; line-height:1.2; }}
.wrap {{ max-width:1240px; margin:0 auto; padding:0 16px; }}
.hinweis {{ background:#fff7d6; color:#5c4700; font-size:.85rem; text-align:center; padding:.5rem 16px; }}
header.kopf {{ border-bottom:1px solid #f2f4f6; padding:14px 0; }}
header.kopf .wrap {{ display:flex; align-items:center; justify-content:space-between; gap:1rem; flex-wrap:wrap; }}
nav {{ display:flex; flex-wrap:wrap; gap:.25rem 1.2rem; }}
nav a {{ color:#1b2836; font-weight:600; text-decoration:none; }}
.btn {{ display:inline-block; background:#4fa82e; color:#fff; font-weight:700; padding:.7rem 1.3rem; border-radius:6px; text-decoration:none; border:2px solid #4fa82e; }}
.btn.outline {{ background:transparent; color:#1b2836; border-color:#1b2836; }}
.hero {{ text-align:center; padding:56px 0 40px; }}
.hero h1 {{ font-size:clamp(2rem,5vw,2.75rem); margin:.3rem 0 .6rem; }}
.hero p.lead {{ font-size:1.25rem; color:#4a5560; max-width:760px; margin:0 auto 1.4rem; }}
.hero .btns {{ display:flex; gap:.8rem; justify-content:center; flex-wrap:wrap; margin-bottom:2rem; }}
.hero img {{ width:100%; height:auto; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(240px,1fr)); gap:1.25rem; }}
.grid.klein {{ grid-template-columns:repeat(auto-fill,minmax(220px,1fr)); }}
section.block {{ padding:40px 0; }}
section.block > .wrap > h2 {{ text-align:center; }}
.hell {{ background:#f2f4f6; }}
.bf-kachel img {{ width:100%; height:auto; margin-top:.5rem; border-radius:4px; }}
.bf-band {{ padding:28px 0; }}
.bf-band .wrap {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(200px,1fr)); gap:1rem; }}
footer {{ background:#1b2836; color:#fff; padding:40px 0 28px; font-size:.9rem; }}
footer .grau {{ color:#8b939b; }}
.bf-ohne-bild {{ background:#fff url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Cg fill='none' stroke='%238b939b' stroke-width='2'%3E%3Cpath d='M32 8v30'/%3E%3Cpath d='M26 14h12M26 20h12'/%3E%3Cellipse cx='32' cy='46' rx='18' ry='6'/%3E%3Cpath d='M14 46v4c0 3 8 6 18 6s18-3 18-6v-4'/%3E%3C/g%3E%3C/svg%3E") center/45% no-repeat; }}
.ki-hinweis {{ position:fixed; right:16px; bottom:76px; max-width:min(320px,calc(100vw - 32px)); background:#fff; color:#1b2836; border-radius:10px; padding:.8rem 1rem; box-shadow:0 8px 30px rgb(27 40 54/25%); margin:0; font-size:.9rem; }}
.bf-ki-knopf {{ position:fixed; right:16px; bottom:16px; background:#1b2836; color:#fff; border:0; border-radius:999px; padding:.8rem 1.2rem; font-weight:700; cursor:pointer; box-shadow:0 6px 20px rgb(27 40 54/25%); }}
{css_theme}
{css_finder}
</style>
<div class="hinweis">Vorschau mit dem TS-Sortiment und {len(produkte) - TS_ANZAHL} Vergleichsprodukten anderer Hersteller (Preis auf Anfrage). Shop, Warenkorb und KI-Berater werden erst auf dem echten Server aktiv.</div>
<header class="kopf"><div class="wrap"><a class="bf-wordmark" href="#">bein<span class="bf-und">und</span>fuß<span class="bf-dot">.</span>de</a>
<nav><a href="#welten">Produktwelten</a><a href="#finder">Produktfinder</a><a href="#anwendungen">Anwendungen</a><a href="#">Kontakt</a></nav></div></header>
<main>
<section class="hero"><div class="wrap">
<p class="bf-claim">Einschlagfüße · Stellbeine · Maschinenfüße</p>
<h1>Immer die passende Stabilität.</h1>
<p class="lead">Aufstellen, ausrichten, stabilisieren, entkoppeln, befestigen: Finden Sie den Fuß, der zu Ihrer Maschine, Ihrem Tisch oder Gerät passt.</p>
<div class="btns"><a class="btn" href="#finder">Zum Produktfinder</a><a class="btn outline" href="#welten">Alle Produkte</a></div>
<img src="{data_uri(THEME / 'assets/hero-fuesse.jpg')}" alt="Auswahl an Maschinenfüßen, Edelstahl-Stellbeinen und Einschlagfüßen">
</div></section>
<section class="block" id="welten"><div class="wrap"><h2>Unsere Produktwelten</h2><div class="grid">{kacheln}</div></div></section>
<section class="block hell" id="finder"><div class="wrap"><h2>Produktfinder</h2><div id="bf-finder" class="bf-finder"></div></div></section>
<section class="block" id="anwendungen"><div class="wrap"><h2>Stabile Lösungen für jede Anwendung</h2><div class="grid klein">{anw}</div></div></section>
<div class="bf-band"><div class="wrap">{band}</div></div>
</main>
<footer><div class="wrap"><p style="font-size:1.4rem;font-weight:800;margin:0">beinundfuß.de</p>
<p>Immer die passende Stabilität. Ein Angebot der TS Systemtechnik.</p>
<p class="grau">Alle Preise zzgl. MwSt. und Versand. Verkauf an Gewerbetreibende.</p></div></footer>
<p id="ki-hinweis" class="ki-hinweis" hidden>Der KI-Berater wird auf dem echten Server mit dem Produktkatalog verbunden und beantwortet dann Fragen wie „Fuß für 40er Vierkantrohr, Tisch mit 300 kg“.</p>
<button class="bf-ki-knopf" type="button" onclick="const h=document.getElementById('ki-hinweis'); h.hidden=!h.hidden;">Produktberater</button>
<script>
const BF_DATEN = {json.dumps(produkte, ensure_ascii=False)};
window.bfFinder = {{ api: "vorschau://produkte", preset: {{}} }};
const echtesFetch = window.fetch;
const seite = (url) => {{ const q = new URLSearchParams(url.split("?")[1]); const n = +q.get("per_page") || 100, s = +q.get("page") || 1; return BF_DATEN.slice((s - 1) * n, s * n); }};
window.fetch = (url, o) => String(url).startsWith("vorschau://")
  ? Promise.resolve(new Response(JSON.stringify(seite(String(url))), {{ status: 200, headers: {{ "Content-Type": "application/json" }} }}))
  : echtesFetch(url, o);
</script>
<script>{js_finder}</script>
<script>
document.querySelectorAll('[data-anwendung]').forEach(a => a.addEventListener('click', () => {{
  setTimeout(() => {{
    let aktiv;
    while ((aktiv = document.querySelector('.bf-option.ist-aktiv'))) aktiv.click();
    const ziel = [...document.querySelectorAll('.bf-option')].find(b => b.firstChild.textContent === a.dataset.anwendung);
    if (ziel) ziel.click();
  }}, 50);
}}));
</script>
"""
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(seite, encoding="utf-8")
    print(f"{OUT.relative_to(ROOT)}: {len(seite) // 1024} KB, {len(produkte)} Produkte")


if __name__ == "__main__":
    main()
