#!/usr/bin/env python3
"""Baut beinundfuß.de als statische Website (ohne WordPress) in den Ordner site/.

Quelle sind dieselben Importdateien wie für WooCommerce (import/*.csv), dazu daten/site.json
(Kontakt, Bezahllinks). Der Ordner site/ kann auf jeden Webspace hochgeladen werden.

Aufruf: python3 werkzeuge/build_site.py  ->  site/
"""
import csv
import html
import json
import os
import re
import shutil
import unicodedata
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote

from zeichnung import zeichnung

ROOT = Path(__file__).resolve().parent.parent
THEME = ROOT / "wp-content/themes/beinundfuss"
PLUGIN = ROOT / "wp-content/plugins/beinundfuss-shop"
OUT = ROOT / "site"
CFG = json.loads((ROOT / "daten/site.json").read_text(encoding="utf-8"))
RECHT = ROOT / "daten/rechtstexte"
# Unterordner, falls die Seite nicht direkt unter der Domain liegt (z. B. /Fu-undBein auf github.io).
BASIS = os.environ.get("SITE_BASIS", "").rstrip("/")
# AGB-Seite nur, wenn der Text vorliegt; Impressum und Datenschutz sind Pflicht (Build bricht sonst ab).
AGB_LINK = '<a href="/agb/">AGB</a>' if (RECHT / "agb.html").exists() else ""

FINDER = ["Anwendung", "Funktion", "Bauform", "Material", "Rohrmaß", "Gewinde", "Fußform", "Anschluss", "Bodenbefestigung"]

# Kategorien wie im WordPress-Plugin (includes/setup.php): Name → (Slug, Beschreibung, Eltern-Slug)
KATEGORIEN = {
    "Einschlagfüße": ("einschlagfuesse", "Für Vierkant- und Rundrohre: einschlagen, ausrichten, fertig.", None),
    "Vierkantrohr": ("vierkantrohr", "Einschlagfüße und Gewindeeinsätze für Vierkant- und Rechteckrohr.", "einschlagfuesse"),
    "Rundrohr": ("rundrohr", "Einschlagfüße und Gewindeeinsätze für Rundrohr.", "einschlagfuesse"),
    "Edelstahl-Stellbeine": ("edelstahl-stellbeine", "Höhenverstellbare Beine für Gastronomie, Großküche und Möbelbau.", None),
    "Gerätebeine": ("geraetebeine", "Gerätebeine und Möbelfüße.", "edelstahl-stellbeine"),
    "Maschinenfüße": ("maschinenfuesse", "Gewindespindel und Fußteller zum exakten Ausrichten von Maschinen.", None),
    "Gelenkfüße": ("gelenkfuesse", "Neigbarer Teller für unebene oder geneigte Böden.", None),
    "Füße mit Bodenbefestigung": ("fuesse-mit-bodenbefestigung", "Teller mit Befestigungslöchern gegen Verschieben, Vibration und Kippen.", None),
    "Schwingungsdämpfer": ("schwingungsdaempfer", "Metall und Elastomer zum Entkoppeln von Aggregaten und Klimageräten.", None),
    "Hygienefüße": ("hygienefuesse", "Edelstahlfüße für Lebensmittel-, Getränke- und Pharmaanlagen.", None),
    "Schwerlastfüße": ("schwerlastfuesse", "Große Teller und kräftige Spindeln für schwere Anlagen.", None),
    "Rollen & Sonderlösungen": ("rollen-sonderloesungen", "Rollen, Kombinationen aus Rolle und Fuß und Sonderanfertigungen.", None),
    "Zubehör": ("zubehoer", "Montageplatten und Ergänzungen.", None),
}
SLUG_NAME = {v[0]: k for k, v in KATEGORIEN.items()}

e = html.escape


def slug(text):
    t = text.lower().replace("ß", "ss").replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")


# ---------------------------------------------------------------- Daten

def vergleichspreise():
    """Verkaufspreise der Vergleichsprodukte (netto, schon mit Aufschlag), aus werkzeuge/preise_uebernehmen.py."""
    datei = ROOT / "daten/preise-vergleich.csv"
    if not datei.exists():
        return {}
    return {r["sku"]: r["preis_netto"] for r in csv.DictReader(datei.open(encoding="utf-8")) if r["preis_netto"]}


def produkte_laden():
    vk = vergleichspreise()
    rows = []
    for datei in ("produkte-woocommerce.csv", "vergleichsprodukte-woocommerce.csv"):
        rows += list(csv.DictReader((ROOT / "import" / datei).open(encoding="utf-8")))
    varianten = defaultdict(list)
    for r in rows:
        if r["Type"] == "variation":
            ausf = next((r[f"Attribute {i} value(s)"] for i in range(1, 20) if r.get(f"Attribute {i} name") == "Ausführung"), "")
            varianten[r["Parent"]].append({"sku": r["SKU"], "ausfuehrung": ausf, "preis": r["Regular price"]})
    produkte, belegt = [], set()
    for r in rows:
        if r["Type"] == "variation" or str(r["Published"]) != "1":
            continue
        s = slug(r["Name"])[:80].strip("-")
        if s in belegt:
            s = f"{s}-{slug(r['SKU'])}"
        belegt.add(s)
        merkmale = {}
        for i in range(1, 20):
            name = r.get(f"Attribute {i} name")
            if name and name != "Ausführung":
                werte = [w.strip() for w in r[f"Attribute {i} value(s)"].split(",") if w.strip()]
                merkmale[name] = werte if name in FINDER else ", ".join(werte)
        kats = []
        for pfad in r["Categories"].split(","):
            teile = [t.strip() for t in pfad.split(">")]
            kats += [KATEGORIEN[t][0] for t in teile if t in KATEGORIEN]
        produkte.append({
            "sku": r["SKU"], "slug": s, "name": r["Name"], "kurz": r["Short description"], "text": r["Description"],
            "bild": (r["Images"] or "").split(",")[0].strip(), "marke": r.get("Brands", ""),
            "kategorien": list(dict.fromkeys(kats)), "merkmale": merkmale,
            "preis": r["Regular price"] or vk.get(r["SKU"], ""), "varianten": varianten.get(r["SKU"], []),
            "preis_ab": r["SKU"] in vk,  # Serienpreis: günstigste Ausführung
            "vergleich": r.get("Meta: _bf_herkunft") == "vergleich",
        })
    return produkte


def preise(p):
    werte = [float(v["preis"]) for v in p["varianten"] if v["preis"]] or ([float(p["preis"])] if p["preis"] else [])
    return werte


def euro(betrag):
    return f"{betrag:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def preis_text(p):
    w = preise(p)
    if not w:
        return "Preis auf Anfrage"
    return ("ab " if len(set(w)) > 1 or p.get("preis_ab") else "") + euro(min(w)) + " zzgl. MwSt."


def mailto(betreff, text):
    return f"mailto:{CFG['anfrage_email']}?subject={quote(betreff)}&body={quote(text)}"


def anfrage_link(p, ausfuehrung="", bestellung=False):
    art = "Bestellung" if bestellung else "Anfrage"
    zeile = p["name"] + (f" – {ausfuehrung}" if ausfuehrung else "")
    text = (f"Guten Tag,\n\n{'ich möchte bestellen' if bestellung else 'bitte senden Sie mir ein Angebot für'}:\n{zeile}\nMenge: \n\n"
            "Firma: \nAnsprechpartner: \nLieferadresse: \nTelefon: \n")
    return mailto(f"{art}: {zeile} ({p['sku']})", text)


# ---------------------------------------------------------------- Layout

NAV = [("Produktwelten", "/#welten"), ("Produktfinder", "/produktfinder/"), ("Anwendungen", "/#anwendungen"), ("Kontakt", "/kontakt/")]


def seite(titel, inhalt, beschreibung="", extra_kopf=""):
    nav = "".join(f'<a href="{h}">{t}</a>' for t, h in NAV)
    return f"""<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(titel)}</title>
<meta name="description" content="{e(beschreibung or 'Einschlagfüße, Stellbeine und Maschinenfüße: Immer die passende Stabilität.')}">
<link rel="stylesheet" href="/assets/site.css">
<link rel="icon" href="/assets/favicon.svg" type="image/svg+xml">
{extra_kopf}</head>
<body>
<header class="kopf"><div class="wrap"><a class="bf-wordmark" href="/">bein<span class="bf-und">und</span>fuß<span class="bf-dot">.</span>de</a>
<nav>{nav}</nav></div></header>
<main>
{inhalt}
</main>
<footer><div class="wrap fuss">
<div><p class="fuss-marke">beinundfuß.de</p><p>Immer die passende Stabilität. {e(CFG['betreiber_zeile'])}</p>
<p class="grau">Alle Preise zzgl. MwSt. und Versand. Verkauf an Gewerbetreibende.</p></div>
<div class="fuss-links"><a href="/kontakt/">Kontakt</a><a href="/impressum/">Impressum</a><a href="/datenschutz/">Datenschutz</a>{AGB_LINK}</div>
</div></footer>
</body>
</html>
"""


def bild_url(p):
    """Produktfoto, sonst die eigene Prinzipskizze."""
    return p["bild"] or f"/assets/skizzen/{p['slug']}.svg"


def karte(p):
    bild = f'<img src="{e(bild_url(p))}" alt="" loading="lazy">'
    return (f'<a class="bf-karte" href="/produkt/{p["slug"]}/">{bild}<h3>{e(p["name"])}</h3>'
            f'<p class="bf-preis">{e(preis_text(p))}</p><span class="bf-mehr">Ansehen</span></a>')


def knopf_kaufen(p, v=None):
    sku = v["sku"] if v else p["sku"]
    link = CFG.get("bezahllinks", {}).get(sku)
    if link:
        return f'<a class="btn" href="{e(link)}">Kaufen</a>'
    return f'<a class="btn" href="{e(anfrage_link(p, v["ausfuehrung"] if v else "", bestellung=True))}">Bestellen</a>'


def produktseite(p):
    kat = next((k for k in p["kategorien"]), None)
    pfad = ['<a href="/">Start</a>']
    if kat:
        eltern = KATEGORIEN[SLUG_NAME[kat]][2]
        if eltern:
            pfad.append(f'<a href="/kategorie/{eltern}/">{e(SLUG_NAME[eltern])}</a>')
        pfad.append(f'<a href="/kategorie/{kat}/">{e(SLUG_NAME[kat])}</a>')
    bild = f'<img src="{e(p["bild"])}" alt="{e(p["name"])}">' if p["bild"] else zeichnung(p)

    if p["varianten"]:
        zeilen = "".join(
            f'<tr><td>{e(v["ausfuehrung"])}</td><td class="klein">{e(v["sku"])}</td>'
            f'<td class="zahl">{euro(float(v["preis"])) if v["preis"] else "auf Anfrage"}</td>'
            f'<td>{knopf_kaufen(p, v) if v["preis"] else ""}</td></tr>'
            for v in p["varianten"])
        kauf = (f'<table class="varianten"><thead><tr><th>Ausführung</th><th>Art.-Nr.</th><th class="zahl">Preis netto</th><th></th></tr></thead>'
                f'<tbody>{zeilen}</tbody></table>')
    elif p["preis"]:
        kauf = f'<p class="preis-gross">{e(preis_text(p))}</p><p>{knopf_kaufen(p)}</p>'
        if p.get("preis_ab"):
            kauf += ('<p class="klein grau">Preis für die günstigste Ausführung dieser Serie. Bitte Gewinde und Maß in der '
                     'Bestellung angeben; wir bestätigen Preis und Lieferzeit.</p>')
    else:
        kauf = (f'<p class="preis-gross">Preis auf Anfrage</p><p><a class="btn" href="{e(anfrage_link(p))}">Angebot anfragen</a></p>'
                '<p class="klein grau">Wir melden uns mit Preis, passender Ausführung und Lieferzeit.</p>')

    merkmale = "".join(f'<tr><th>{e(k)}</th><td>{e(", ".join(v) if isinstance(v, list) else v)}</td></tr>'
                       for k, v in p["merkmale"].items() if v)
    inhalt = f"""<div class="wrap produkt">
<nav class="pfad">{' › '.join(pfad)}</nav>
<div class="produkt-raster">
<div class="produkt-bild">{bild}</div>
<div>
{f'<p class="marke">{e(p["marke"])}</p>' if p["marke"] else ''}
<h1>{e(p["name"])}</h1>
<p class="lead">{e(p["kurz"])}</p>
{kauf}
</div>
</div>
<section class="beschreibung"><h2>Beschreibung</h2>{p["text"]}</section>
{f'<section><h2>Merkmale</h2><table class="merkmale"><tbody>{merkmale}</tbody></table></section>' if merkmale else ''}
</div>"""
    return seite(f"{p['name']} | beinundfuß.de", inhalt, p["kurz"])


def kategorieseite(slug_, liste, unter):
    name = SLUG_NAME[slug_]
    beschr = KATEGORIEN[name][1]
    chips = "".join(f'<a class="chip" href="/kategorie/{u}/">{e(SLUG_NAME[u])}</a>' for u in unter)
    inhalt = f"""<section class="block"><div class="wrap">
<nav class="pfad"><a href="/">Start</a> › {e(name)}</nav>
<h1>{e(name)}</h1><p class="lead">{e(beschr)}</p>
{f'<p class="chips">{chips}</p>' if chips else ''}
<p class="grau">{len(liste)} {"Produkt" if len(liste) == 1 else "Produkte"} · <a href="/produktfinder/">im Produktfinder filtern</a></p>
<div class="bf-karten">{''.join(karte(p) for p in liste)}</div>
</div></section>"""
    return seite(f"{name} | beinundfuß.de", inhalt, beschr)


def startseite(anzahl):
    pat = lambda n: (THEME / "patterns" / f"{n}.php").read_text(encoding="utf-8")
    welten = re.findall(r"array\( '([^']+)', '([^']+)', '([^']+)' \)", pat("produktwelten"))
    anwendungen = re.findall(r"array\( '([^']+)', '([^']+)' \)", pat("anwendungen"))
    vorteile = re.findall(r"array\( '([^']+)', '(<[^']+)' \)", pat("vorteile"))
    kacheln = "".join(f'<div class="bf-kachel"><a href="/kategorie/{s}/"><h3>{e(n)}</h3><p>{e(t)}</p></a></div>' for s, n, t in welten)
    anw = "".join(
        f'<div class="bf-kachel"><a href="/produktfinder/?anwendung={quote(a)}"><h3><span class="bf-nummer">{i + 1}</span>{e(t)}</h3>'
        f'<img loading="lazy" src="/assets/anwendungen/anwendung-{i + 1:02d}.jpg" alt=""></a></div>'
        for i, (t, a) in enumerate(anwendungen))
    band = "".join(f'<div class="bf-band-item"><svg viewBox="0 0 24 24" aria-hidden="true">{svg}</svg><span>{e(t)}</span></div>' for t, svg in vorteile)
    inhalt = f"""<section class="hero"><div class="wrap">
<p class="bf-claim">Einschlagfüße · Stellbeine · Maschinenfüße</p>
<h1>Immer die passende Stabilität.</h1>
<p class="lead">Aufstellen, ausrichten, stabilisieren, entkoppeln, befestigen: Finden Sie unter {anzahl} Produkten den Fuß, der zu Ihrer Maschine, Ihrem Tisch oder Gerät passt.</p>
<div class="btns"><a class="btn" href="/produktfinder/">Zum Produktfinder</a><a class="btn outline" href="#welten">Alle Produktwelten</a></div>
<img src="/assets/hero-fuesse.jpg" alt="Auswahl an Maschinenfüßen, Edelstahl-Stellbeinen und Einschlagfüßen">
</div></section>
<section class="block" id="welten"><div class="wrap"><h2>Unsere Produktwelten</h2><div class="grid">{kacheln}</div></div></section>
<section class="block hell"><div class="wrap teaser"><h2>In sechs Schritten zum passenden Fuß</h2>
<p>Anwendung, Funktion, Bauform, Rohrmaß, Gewinde und Material wählen: Der Produktfinder zeigt nur, was zusammenpasst.</p>
<p><a class="btn" href="/produktfinder/">Produktfinder starten</a></p></div></section>
<section class="block" id="anwendungen"><div class="wrap"><h2>Stabile Lösungen für jede Anwendung</h2><div class="grid klein">{anw}</div></div></section>
<div class="bf-band"><div class="wrap">{band}</div></div>"""
    return seite("beinundfuß.de – Einschlagfüße, Stellbeine und Maschinenfüße", inhalt)


def finderseite():
    inhalt = """<section class="block hell"><div class="wrap"><h1>Produktfinder</h1>
<p class="lead">Wählen Sie Schritt für Schritt aus. Angezeigt werden nur Optionen, zu denen es passende Produkte gibt.</p>
<div id="bf-finder" class="bf-finder"><p>Produkte werden geladen …</p></div></div></section>
<script>
const q = new URLSearchParams(location.search);
window.bfFinder = { api: "/daten/produkte.json", kontakt: "/kontakt/", shop: "/#welten", einmal: true, preset: { Anwendung: q.get("anwendung") || "" } };
</script>
<script src="/assets/finder.js" defer></script>"""
    return seite("Produktfinder | beinundfuß.de", inhalt, "Den passenden Fuß in sechs Schritten finden.",
                 '<link rel="stylesheet" href="/assets/finder.css">\n')


def textseite(titel, absaetze):
    return seite(f"{titel} | beinundfuß.de", f'<section class="block"><div class="wrap text"><h1>{e(titel)}</h1>{absaetze}</div></section>')


def store_api(produkte):
    """Format wie die WooCommerce Store API, damit finder.js unverändert läuft."""
    out = []
    for i, p in enumerate(produkte, 1):
        w = [round(x * 100) for x in preise(p)]
        out.append({
            "id": i, "name": p["name"], "permalink": f"/produkt/{p['slug']}/",
            "images": [{"src": bild_url(p)}],
            "attributes": [{"name": k, "terms": [{"name": t} for t in v]} for k, v in p["merkmale"].items() if k in FINDER and v],
            "prices": {"currency_code": "EUR", "currency_minor_unit": 2, "price": str(min(w)) if w else "",
                       "price_range": {"min_amount": str(min(w)), "max_amount": str(max(w))} if len(set(w)) > 1 or (w and p.get("preis_ab")) else None},
        })
    return out


CSS = """
:root { --navy:#1b2836; --gruen:#4fa82e; --gruen-dunkel:#3d8a22; --grau:#8b939b; --grau-dunkel:#4a5560; --hell:#f2f4f6;
  --wp--preset--color--navy:var(--navy); --wp--preset--color--gruen:var(--gruen); --wp--preset--color--grau:var(--grau);
  --wp--preset--color--grau-dunkel:var(--grau-dunkel); --wp--preset--color--hell:var(--hell); color-scheme: light; }
* { box-sizing: border-box; }
html { background:#fff; }
body { margin:0; background:#fff; color:var(--navy); font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif; }
a { color:var(--gruen-dunkel); }
h1,h2,h3 { font-weight:800; line-height:1.2; }
h1 { font-size:clamp(1.7rem,4vw,2.4rem); margin:.4rem 0 .6rem; }
img { max-width:100%; height:auto; }
.wrap { max-width:1240px; margin:0 auto; padding:0 16px; }
.klein { font-size:.85rem; } .grau { color:var(--grau-dunkel); }
header.kopf { border-bottom:1px solid var(--hell); padding:14px 0; }
header.kopf .wrap { display:flex; align-items:center; justify-content:space-between; gap:1rem; flex-wrap:wrap; }
header nav { display:flex; flex-wrap:wrap; gap:.25rem 1.2rem; }
header nav a { color:var(--navy); font-weight:600; text-decoration:none; }
header nav a:hover { color:var(--gruen-dunkel); }
.btn { display:inline-block; background:var(--gruen); color:#fff; font-weight:700; padding:.6rem 1.2rem; border-radius:6px; text-decoration:none; border:2px solid var(--gruen); white-space:nowrap; }
.btn:hover { background:var(--gruen-dunkel); border-color:var(--gruen-dunkel); }
.btn.outline { background:transparent; color:var(--navy); border-color:var(--navy); }
.hero { text-align:center; padding:48px 0 32px; }
.hero h1 { font-size:clamp(2rem,5vw,2.75rem); }
.lead { font-size:1.15rem; color:var(--grau-dunkel); max-width:760px; }
.hero .lead { margin:0 auto 1.4rem; }
.hero .btns { display:flex; gap:.8rem; justify-content:center; flex-wrap:wrap; margin-bottom:2rem; }
.grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(240px,1fr)); gap:1.25rem; }
.grid.klein { grid-template-columns:repeat(auto-fill,minmax(220px,1fr)); }
section.block { padding:40px 0; }
section.block > .wrap > h2, .teaser { text-align:center; }
.hell { background:var(--hell); }
.bf-kachel img { width:100%; height:auto; margin-top:.5rem; border-radius:4px; }
.bf-band { padding:28px 0; }
.bf-band .wrap { display:grid; grid-template-columns:repeat(auto-fill,minmax(200px,1fr)); gap:1rem; }
footer { background:var(--navy); color:#fff; padding:40px 0 28px; font-size:.9rem; }
footer .grau { color:var(--grau); }
.fuss { display:flex; justify-content:space-between; gap:2rem; flex-wrap:wrap; }
.fuss-marke { font-size:1.4rem; font-weight:800; margin:0; }
.fuss-links { display:flex; flex-direction:column; gap:.4rem; }
.fuss-links a { color:#fff; }
.pfad { font-size:.85rem; color:var(--grau-dunkel); margin:1.2rem 0 .5rem; }
.pfad a { color:var(--grau-dunkel); }
.chips { display:flex; flex-wrap:wrap; gap:.5rem; }
.chip { border:1px solid #cfd6dd; border-radius:999px; padding:.3rem .9rem; text-decoration:none; color:var(--navy); font-weight:600; }
.produkt { padding-bottom:40px; }
.produkt-raster { display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1.2fr); gap:2.5rem; align-items:start; margin-top:1rem; }
.produkt-bild img, .produkt-bild .bf-ohne-bild, .produkt-bild .bf-skizze { width:100%; aspect-ratio:1; object-fit:contain; background-color:var(--hell); border-radius:8px; }
.marke { text-transform:uppercase; letter-spacing:.12em; font-size:.8rem; color:var(--grau-dunkel); margin:0; }
.preis-gross { font-size:1.4rem; font-weight:800; margin:.5rem 0; }
table { border-collapse:collapse; width:100%; font-size:.92rem; }
th, td { text-align:left; padding:.45rem .6rem; border-bottom:1px solid #e3e7eb; vertical-align:top; }
.varianten .btn { padding:.35rem .8rem; font-size:.85rem; }
.zahl { text-align:right; white-space:nowrap; }
.merkmale th, .beschreibung th { width:38%; color:var(--grau-dunkel); font-weight:600; }
.beschreibung, .produkt section { max-width:860px; margin-top:2rem; }
.tabelle-scroll { overflow-x:auto; }
.text { max-width:820px; }
.bf-ohne-bild { background:#fff url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Cg fill='none' stroke='%238b939b' stroke-width='2'%3E%3Cpath d='M32 8v30'/%3E%3Cpath d='M26 14h12M26 20h12'/%3E%3Cellipse cx='32' cy='46' rx='18' ry='6'/%3E%3Cpath d='M14 46v4c0 3 8 6 18 6s18-3 18-6v-4'/%3E%3C/g%3E%3C/svg%3E") center/45% no-repeat; }
.bf-karten { display:grid; grid-template-columns:repeat(auto-fill,minmax(190px,1fr)); gap:1rem; }
.bf-karte { display:flex; flex-direction:column; background:var(--hell); border-radius:8px; padding:.9rem; text-decoration:none; color:inherit; }
.bf-karte:hover { box-shadow:0 6px 20px rgb(27 40 54/12%); }
.bf-karte img, .bf-karte .bf-ohne-bild { width:100%; aspect-ratio:1; object-fit:contain; background-color:#fff; border-radius:6px; }
.bf-karte h3 { font-size:.95rem; margin:.6rem 0 .3rem; line-height:1.3; }
.bf-preis { margin:0 0 .5rem; font-weight:600; font-size:.9rem; }
.bf-mehr { margin-top:auto; color:var(--gruen-dunkel); font-weight:700; font-size:.875rem; }
@media (max-width:781px) {
  .produkt-raster { grid-template-columns:1fr; gap:1.2rem; }
  .varianten thead { display:none; }
  .varianten tr { display:grid; grid-template-columns:1fr auto; gap:.2rem .8rem; border-bottom:1px solid #e3e7eb; padding:.5rem 0; }
  .varianten td { border:0; padding:0; }
  .varianten td:first-child { grid-column:1 / -1; font-weight:600; }
}
"""


def main():
    produkte = produkte_laden()
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "assets").mkdir(parents=True)
    (OUT / "daten").mkdir()

    theme_css = re.sub(r"/\*.*?\*/", "", (THEME / "style.css").read_text(encoding="utf-8"), count=1, flags=re.S)
    (OUT / "assets/site.css").write_text(CSS + theme_css, encoding="utf-8")
    shutil.copy(PLUGIN / "assets/finder.js", OUT / "assets/finder.js")
    shutil.copy(PLUGIN / "assets/finder.css", OUT / "assets/finder.css")
    shutil.copy(THEME / "assets/hero-fuesse.jpg", OUT / "assets/hero-fuesse.jpg")
    shutil.copytree(THEME / "assets/anwendungen", OUT / "assets/anwendungen")
    (OUT / "assets/favicon.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="6" fill="#1b2836"/>'
        '<path d="M16 6v14M12 10h8" stroke="#fff" stroke-width="2.5" fill="none"/><ellipse cx="16" cy="23" rx="8" ry="3" fill="#4fa82e"/></svg>',
        encoding="utf-8")
    (OUT / "assets/skizzen").mkdir()
    for p in produkte:
        if not p["bild"]:
            (OUT / "assets/skizzen" / f"{p['slug']}.svg").write_text(zeichnung(p, klein=True), encoding="utf-8")
    (OUT / "daten/produkte.json").write_text(json.dumps(store_api(produkte), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    def schreibe(pfad, text):
        ziel = OUT / pfad / "index.html" if pfad else OUT / "index.html"
        ziel.parent.mkdir(parents=True, exist_ok=True)
        ziel.write_text(text, encoding="utf-8")

    schreibe("", startseite(len(produkte)))
    schreibe("produktfinder", finderseite())
    for p in produkte:
        schreibe(f"produkt/{p['slug']}", produktseite(p))

    nach_kat = defaultdict(list)
    for p in produkte:
        for k in p["kategorien"]:
            nach_kat[k].append(p)
    for name, (s, _, eltern) in KATEGORIEN.items():
        unter = [u for u, (_, _, el) in ((v[0], v) for v in KATEGORIEN.values()) if el == s]
        liste = nach_kat[s] + [p for u in unter for p in nach_kat[u] if p not in nach_kat[s]]
        if not liste:
            continue
        liste.sort(key=lambda p: (p["vergleich"], p["name"].lower()))  # eigenes Sortiment zuerst
        schreibe(f"kategorie/{s}", kategorieseite(s, liste, unter))

    mail = e(CFG["anfrage_email"])
    schreibe("kontakt", textseite("Kontakt", f"<p>Fragen zu Produkten, Sonderanfertigungen oder Mengenpreisen? Schreiben Sie uns.</p>"
                                             f'<p><a class="btn" href="mailto:{mail}">{mail}</a></p>'
                                             f"<p>{e(CFG['betreiber_zeile'])}</p>"))
    for pfad, titel in (("impressum", "Impressum"), ("datenschutz", "Datenschutzerklärung"), ("agb", "Allgemeine Geschäftsbedingungen")):
        datei = RECHT / f"{pfad}.html"
        if not datei.exists():
            if pfad == "agb":
                continue
            raise SystemExit(f"Rechtstext fehlt: {datei}")
        schreibe(pfad, textseite(titel, datei.read_text(encoding="utf-8")))
    (OUT / "404.html").write_text(textseite("Seite nicht gefunden", '<p>Diese Seite gibt es nicht (mehr). <a href="/">Zur Startseite</a> oder <a href="/produktfinder/">zum Produktfinder</a>.</p>'), encoding="utf-8")
    (OUT / "robots.txt").write_text("User-agent: *\nAllow: /\n", encoding="utf-8")

    if BASIS:  # interne Links auf den Unterordner umschreiben
        for f in OUT.rglob("*.html"):
            t = f.read_text(encoding="utf-8")
            t = re.sub(r'((?:href|src)=")/(?!/)', rf"\1{BASIS}/", t)
            t = re.sub(r'(api|kontakt|shop): "/', rf'\1: "{BASIS}/', t)
            f.write_text(t, encoding="utf-8")
        j = OUT / "daten/produkte.json"
        j.write_text(j.read_text(encoding="utf-8").replace('"permalink":"/', f'"permalink":"{BASIS}/')
                     .replace('"src":"/', f'"src":"{BASIS}/'), encoding="utf-8")
        if (ROOT / "CNAME").exists():
            raise SystemExit("SITE_BASIS und eigene Domain (CNAME) schließen sich aus")
    if (ROOT / "CNAME").exists():
        shutil.copy(ROOT / "CNAME", OUT / "CNAME")
    seiten = sum(1 for _ in OUT.rglob("*.html"))
    groesse = sum(f.stat().st_size for f in OUT.rglob("*") if f.is_file()) // 1024
    print(f"site/: {seiten} Seiten, {len(produkte)} Produkte, {groesse} KB")


if __name__ == "__main__":
    main()
