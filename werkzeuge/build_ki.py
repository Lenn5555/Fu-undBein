#!/usr/bin/env python3
"""Baut die KI-Version von beinundfuß.de: eine Beraterseite statt Katalog.

Schreibt
  site/                          Beraterseite, Kontakt, Impressum, Datenschutz, Skizzen (GitHub Pages)
  ki/worker/src/katalog.json     alle Produkte MIT Preis, öffentlich unbedenklich (nur Verkaufspreise)
  /mnt/project-files/katalog/intern/ki-bezugsquellen.json
                                 Händler, Bestell-Link und EK je Artikelnummer. NICHT ins Repo,
                                 wird in den Cloudflare-Speicher (KV) des Workers geladen.

Aufruf: python3 werkzeuge/build_ki.py
"""
import base64
import csv
import gzip
import json
import re
import shutil
import sys
from datetime import date
from html import escape as e
from urllib.parse import quote
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_site as b  # noqa: E402
from zeichnung import zeichnung  # noqa: E402

ROOT, OUT, CFG = b.ROOT, b.OUT, b.CFG
b.NAV = [("Berater", "/"), ("Kontakt", "/kontakt/")]
INTERN = Path("/mnt/project-files/katalog/intern")
KATALOG = ROOT / "ki/worker/src/katalog.json"
# Öffentliche Adresse für Canonical, Sitemap und Vorschaubilder. Mit Datei CNAME gilt die eigene Domain,
# so zieht Google beim Umzug auf beinundfuß.de automatisch mit.
CNAME = (ROOT / "CNAME").read_text(encoding="utf-8").strip() if (ROOT / "CNAME").exists() else ""
SITE_URL = f"https://{CNAME}" if CNAME else "https://lenn5555.github.io/Fu-undBein"
SEITEN = []  # (pfad, priorität) für sitemap.xml


def ohne_html(text):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text or "")).strip()


def wahl_gewinde(p):
    """Gewinde zum Anklicken, wenn eine Serie mehrere anbietet. Nicht bei Einzelartikeln mit zwei Gewinden am selben Teil
    (z. B. GN 360-52-M12: M12 und M36, Halder 25120.0024: M12 und M30); die erkennt man an Gewinde oder Artikelcode im Namen."""
    g = p["merkmale"].get("Gewinde")
    if p["varianten"] or not isinstance(g, list) or len(g) < 2:
        return {}
    name = p.get("name_alt", p["name"])  # Herstellername mit Artikelcode, nicht der eigene Name mit „M16/M20“
    if any(re.search(rf"(?<![\w]){re.escape(w)}(?!\d)", name) for w in g) or re.search(r"\.\d{4}\b", name):
        return {}
    return {"Gewinde": g}


NAMEN = ROOT / "daten/produktnamen.csv"


def neutral(produkte):
    """Eigene Produktnamen ohne Herstellernamen (Lenn, 22.10.2026): Name und Kurztext aus daten/produktnamen.csv.
    Hersteller und Herstellerartikel stehen nur noch intern in den Bezugsquellen (Bestellmail).
    Die alte Adresse jeder Produktseite wird gemerkt und leitet weiter."""
    namen = {r["sku"]: r for r in csv.DictReader(NAMEN.open(encoding="utf-8"))}
    belegt = {p["slug"] for p in produkte if p["sku"] not in namen}
    for p in produkte:
        p["marke"] = ""
        r = namen.get(p["sku"])
        if not r:
            continue
        p["name_alt"], p["name"] = p["name"], r["name"]
        if r["kurz"]:
            p["kurz"] = r["kurz"]
        s = b.slug(r["name"].replace("–", "-").replace("×", "x").replace("Ø", ""))[:80].strip("-")
        if s in belegt:
            s = f"{s}-{b.slug(p['sku'])}"
        belegt.add(s)
        p["slug_alt"], p["slug"] = p["slug"], s


def katalog(produkte):
    """Kompakte Liste für den Berater; nur was einen Preis hat."""
    liste = []
    for p in produkte:
        if not b.preise(p):
            continue
        kurz = re.sub(r"\s*Preis und Lieferzeit auf Anfrage\.?", "", p["kurz"]).strip()
        merkmale = {k: (", ".join(v) if isinstance(v, list) else v) for k, v in p["merkmale"].items()}
        liste.append({
            "sku": p["sku"], "name": p["name"], "marke": p["marke"], "kurz": kurz, "merkmale": merkmale,
            "preis": float(p["preis"]) if p["preis"] else None,
            "preis_ab": p["preis_ab"],  # Preis gilt für die günstigste Ausführung der Serie
            "varianten": [{"sku": v["sku"], "ausfuehrung": v["ausfuehrung"], "preis": float(v["preis"])}
                          for v in p["varianten"] if v["preis"]],
            # Serien ohne eigene Variantenpreise: das Gewinde ist trotzdem vor der Bestellung zu wählen
            "optionen": wahl_gewinde(p),
            "bild": b.bild_url(p),
        })
    return liste


def bezugsquellen(produkte):
    """Interne Zuordnung Artikelnummer -> Händler; enthält EK, darf nie veröffentlicht werden."""
    eingabe, bezug = {}, {}
    for f in sorted(INTERN.glob("eingabe-*.csv")):
        eingabe.update({r["sku"]: r for r in csv.DictReader(f.open(encoding="utf-8"))})
    for f in sorted(INTERN.glob("bezug-*.csv")):
        bezug.update({r["sku"]: r for r in csv.DictReader(f.open(encoding="utf-8"))})
    daten = {}
    for p in produkte:
        if not b.preise(p):
            continue
        if not p["vergleich"]:
            daten[p["sku"]] = {"bezugsquelle": "TS Systemtechnik, eigenes Sortiment", "hersteller": "TS Systemtechnik"}
            continue
        q, r = bezug.get(p["sku"], {}), eingabe.get(p["sku"], {})
        daten[p["sku"]] = {
            "hersteller": r.get("hersteller", ""), "artikel": r.get("serie_artikel", ""),
            "bezugsquelle": q.get("bezugsquelle", ""), "bestell_url": q.get("bestell_url", ""),
            "ek_netto": float(q["preis_netto_eur"]) if q.get("preis_netto_eur") else None,
            "preis_bezug": q.get("preis_bezug", ""), "notiz": q.get("notiz", ""),
        }
    return daten


# Einsätze für das Akkordeon: Bild aus dem Theme, Name, Text (mit Zahlen aus dem Katalog), Frage an den Berater
EINSAETZE = [
    (1, "Gastronomie", "Edelstahl-Stellbeine für Arbeitstische, Spülen und Kühlmöbel, höhenverstellbar und leicht zu reinigen. {Gastronomiegerät} Modelle für Gastronomiegeräte.",
     "Ich brauche höhenverstellbare Füße für einen Edelstahl-Arbeitstisch in der Gastronomie."),
    (3, "Maschinen", "Maschinenfüße mit Gewindespindel von {gew_min} bis {gew_max}, mit oder ohne Bodenbefestigung. {Maschine / Anlage} Modelle für Maschinen und Anlagen.",
     "Ich suche Maschinenfüße für eine Produktionsmaschine. Was brauchen Sie von mir?"),
    (4, "CNC", "Schwere Maschinen mit Vibrationen stehen auf Schwingungsdämpfern und Nivellierelementen. {Schwingungsdämpfer} Dämpfer und {Nivellierelement} Nivellierelemente.",
     "Welche Füße eignen sich für eine schwere CNC-Maschine mit Vibrationen?"),
    (5, "Fördertechnik", "Gelenkfüße gleichen schiefe Böden aus und halten Förderbänder in der Flucht. {Gelenkfuß} Gelenkfüße mit Preis.",
     "Ich brauche Gelenkfüße für ein Förderband, der Boden ist uneben."),
    (9, "Schaltschränke", "Kompakte Stellfüße für Schaltschränke und Gehäuse, die genau im Lot stehen müssen. {Schaltschrank / Gehäuse} Modelle.",
     "Welche Stellfüße passen unter einen Schaltschrank?"),
    (10, "Gestelle", "Einschlagfüße für Vierkant- und Rundrohr: ins offene Rohrende schlagen, ohne Schweißen und Bohren. {Einschlagfuß} Einschlagfüße und {Gewindestopfen} Gewindestopfen.",
     "Ich brauche Einschlagfüße für eine Werkbank aus Vierkantrohr."),
]

# Reihenfolge der Preisliste nach Bauform, mit Mehrzahl für die Überschrift
BAUFORMEN = [("Stellfuß", "Stellfüße"), ("Stellbein", "Stellbeine"), ("Gelenkfuß", "Gelenkfüße"), ("Einschlagfuß", "Einschlagfüße"),
             ("Schwingungsdämpfer", "Schwingungsdämpfer"), ("Nivellierelement", "Nivellierelemente"),
             ("Gewindestopfen", "Gewindestopfen"), ("Spezialausführung", "Spezialausführungen")]


BEISPIELE = [
    "Stellfuß M12 für eine Maschine, ca. 400 kg",
    "Einschlagfuß für 40er Vierkantrohr",
    "Edelstahl für die Lebensmittelindustrie",
    "Ich weiß nicht, was ich brauche",
]


STANDARD_BESCHREIBUNG = ("Stellfüße, Einschlagfüße, Stellbeine und Maschinenfüße mit festem Nettopreis kaufen. "
                         "Anwendung beschreiben, passenden Fuß finden und direkt bestellen. Für Gewerbekunden.")


def euro(x):
    return f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " €"


def min_preis(p):
    w = [v["preis"] for v in p["varianten"]] or [p["preis"]]
    return min(x for x in w if x)


def kennzahlen(liste):
    z = {}
    for p in liste:
        m = p["merkmale"]
        z[m["Bauform"]] = z.get(m["Bauform"], 0) + 1
        for a in m["Anwendung"].split(", "):
            z[a] = z.get(a, 0) + 1
    gew = sorted({int(g.strip()[1:]) for p in liste for g in p["merkmale"].get("Gewinde", "").split(",") if re.fullmatch(r"M\d+", g.strip())})
    z["gew_min"], z["gew_max"] = f"M{gew[0]}", f"M{gew[-1]}"
    return z


def seitenrahmen(titel, inhalt, beschreibung="", kopf="", feld="bone", pfad="", index=True, seite=None):
    """Eigener Rahmen der KI-Seite: feste helle Kopfleiste, dunkler Fuß mit Wortmarke."""
    # Seitenart für die anonyme Zählung (Einstiegsseite), siehe ki/seite/zaehlen.js
    seite = seite or ("start" if pfad == "" and index else "uebersicht" if pfad == "produkte/" else "sonstige")
    nav = "".join(f'<a href="{h}">{t}</a>' for t, h in (("Berater", "/#berater"), ("Einsätze", "/#einsaetze"), ("Preise", "/#preise"), ("Kontakt", "/#kontakt")))
    mail = e(CFG["anfrage_email"])
    return f"""<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(titel)}</title>
<meta name="description" content="{e(beschreibung or STANDARD_BESCHREIBUNG)}">
<meta name="theme-color" content="#111827">
{seo_kopf(titel, beschreibung, pfad, index)}
<link rel="icon" href="/assets/favicon.svg" type="image/svg+xml"><link rel="icon" href="/assets/favicon-48.png" sizes="48x48" type="image/png"><link rel="apple-touch-icon" href="/assets/favicon-180.png">
<link rel="preload" href="/assets/fonts/poppins-600.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="/assets/ki.css">
<script>document.documentElement.classList.add("js")</script>
{kopf}</head>
<body>
<a class="bf-skip" href="#inhalt">Zum Inhalt</a>
<header class="bf-kopf" data-feld="{feld}">
<a class="bf-marke" href="/"><span class="bf-marke-zeichen" aria-hidden="true"></span>beinundfuß.de</a>
<nav class="bf-nav" aria-label="Hauptmenü">{nav}</nav>
<a class="bf-knopf bf-knopf-kopf" href="/#berater">Fuß finden</a>
</header>
<main id="inhalt">
{inhalt}
</main>
<footer class="bf-fuss" data-feld="dunkel">
<div class="bf-fuss-kopf"><a class="bf-wortmarke" href="/">beinundfuß.de</a><p>Stellfüße, Einschlagfüße und Maschinenfüße mit festem Nettopreis. Ein Angebot von TS Systemtechnik, Pfungstadt.</p></div>
<div class="bf-fuss-raster">
<nav class="bf-fuss-links" aria-label="Seite"><a href="/#berater">Berater</a><a href="/#einsaetze">Einsätze</a><a href="/#preise">Preise</a><a href="/#kontakt">Kontakt</a><a href="/produkte/">Alle Produkte</a><a href="/versandkosten/">Versandkosten</a></nav>
<nav class="bf-fuss-links" aria-label="Rechtliches"><a href="/kontakt/">Kontaktseite</a><a href="/impressum/">Impressum</a><a href="/datenschutz/">Datenschutz</a>{b.AGB_LINK}</nav>
<div class="bf-fuss-adresse"><p>{e(CFG['betreiber_zeile'])}<br>TS Systemtechnik, Pfungstadt</p><p><a href="mailto:{mail}">{mail}</a></p></div>
</div>
<div class="bf-fuss-ende"><p>Alle Preise netto zzgl. MwSt. und <a href="/versandkosten/">Versand</a>. Verkauf an Gewerbetreibende.</p><a class="bf-knopf bf-knopf-klein" href="#inhalt">Nach oben</a></div>
</footer>
<script src="/assets/seite.js" defer></script>
<script>window.bfZaehlen = {{ api: "{e(CFG.get('ki_api', ''))}", basis: "", seite: "{seite}" }};</script>
<script src="/assets/zaehlen.js" defer></script>
</body>
</html>
"""


def seo_kopf(titel, beschreibung, pfad, index):
    """Canonical, Open Graph und Search-Console-Bestätigung; Seiten ohne Index bekommen noindex."""
    if not index:
        return '<meta name="robots" content="noindex">'
    url = f"{SITE_URL}/{pfad}"
    besch = e(beschreibung or STANDARD_BESCHREIBUNG)
    zeilen = [f'<link rel="canonical" href="{url}">',
              '<meta property="og:type" content="website">', '<meta property="og:locale" content="de_DE">',
              '<meta property="og:site_name" content="beinundfuß.de">', f'<meta property="og:url" content="{url}">',
              f'<meta property="og:title" content="{e(titel)}">', f'<meta property="og:description" content="{besch}">',
              f'<meta property="og:image" content="{SITE_URL}/assets/vorschau.jpg">',
              '<meta property="og:image:width" content="1200">', '<meta property="og:image:height" content="630">',
              '<meta name="twitter:card" content="summary_large_image">']
    if CFG.get("google_bestaetigung"):
        zeilen.append(f'<meta name="google-site-verification" content="{e(CFG["google_bestaetigung"])}">')
    return "\n".join(zeilen)


def textseite(titel, absaetze, pfad, beschreibung="", prio="0.3"):
    SEITEN.append((pfad, prio))
    return seitenrahmen(f"{titel} | beinundfuß.de", f'<section class="bf-text" data-feld="weiss"><h1>{e(titel)}</h1>{absaetze}</section>',
                        beschreibung=beschreibung, pfad=pfad)


def strukturierte_daten(liste):
    """schema.org für Google: Händler (Shop) mit Kontakt und Website."""
    daten = {"@context": "https://schema.org", "@graph": [
        {"@type": "OnlineStore", "@id": f"{SITE_URL}/#shop", "name": "beinundfuß.de", "url": f"{SITE_URL}/",
         "logo": f"{SITE_URL}/assets/favicon.svg", "image": f"{SITE_URL}/assets/vorschau.jpg",
         "description": STANDARD_BESCHREIBUNG, "email": CFG["anfrage_email"],
         "parentOrganization": {"@type": "Organization", "name": "T&S Systemtechnik GmbH",
                                "address": {"@type": "PostalAddress", "addressLocality": "Pfungstadt", "addressCountry": "DE"}},
         "areaServed": "DE", "currenciesAccepted": "EUR",
         "knowsAbout": ["Stellfüße", "Einschlagfüße", "Stellbeine", "Gelenkfüße", "Maschinenfüße", "Nivellierelemente", "Schwingungsdämpfer"]},
        {"@type": "WebSite", "@id": f"{SITE_URL}/#website", "url": f"{SITE_URL}/", "name": "beinundfuß.de", "inLanguage": "de-DE",
         "publisher": {"@id": f"{SITE_URL}/#shop"}},
    ]}
    return f'<script type="application/ld+json">{json.dumps(daten, ensure_ascii=False)}</script>'


def sitemap():
    heute = date.today().isoformat()
    urls = "".join(f"<url><loc>{e(SITE_URL)}/{pfad}</loc><lastmod>{heute}</lastmod><priority>{prio}</priority></url>"
                   for pfad, prio in SEITEN)
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>\n'


def beraterseite(liste):
    api = CFG.get("ki_api", "")
    anzahl = len(liste)
    z = kennzahlen(liste)
    chips = "".join(f'<button type="button" class="kb-chip" data-frage="{e(x)}">{e(x)}</button>' for x in BEISPIELE)

    panels = []
    for i, (nr, name, text, frage) in enumerate(EINSAETZE):
        offen = " ist-offen" if i == 0 else ""
        panels.append(
            f'<div class="kb-akk-panel{offen}" style="--stufe:{i}">'
            f'<button type="button" class="kb-akk-kopf" aria-expanded="{"true" if i == 0 else "false"}" aria-controls="einsatz-{i}"><span>{e(name)}</span></button>'
            f'<div class="kb-akk-inhalt" id="einsatz-{i}">'
            f'<div class="kb-akk-text"><h3>{e(name)}</h3><p>{e(text.format(**z))}</p>'
            f'<button type="button" class="bf-knopf kb-anw" data-frage="{e(frage)}">Berater fragen</button></div>'
            f'<img class="kb-sticker" src="/assets/anwendungen/anwendung-{nr:02d}.jpg" width="266" height="180" loading="lazy" '
            f'alt="Beispiel: {e(name)} mit passendem Fuß"></div></div>')

    gruppen = {}
    for p in liste:
        gruppen.setdefault(p["merkmale"]["Bauform"], []).append(p)
    bars = []
    for i, (bauform, mehrzahl) in enumerate(BAUFORMEN):
        l = sorted(gruppen.get(bauform, []), key=min_preis)
        if not l:
            continue
        # Alle Modelle der Bauform, jedes führt zu seiner Produktseite
        zeilen = "".join(f'<li><a href="{produkt_url(p)}"><span>{e(p["name"])}</span><span class="kb-preis">{preis_ab_text(p)}</span></a></li>' for p in l)
        bars.append(f'<details class="kb-bar"{" open" if i == 0 else ""}><summary><span>{e(mehrzahl)}</span>'
                    f'<span class="kb-bar-info">{len(l)} Modelle ab {euro(min_preis(l[0]))}</span></summary><ul>{zeilen}</ul>'
                    f'<p class="kb-bar-alle"><a href="{kat_url(bauform)}">Alle {e(mehrzahl)} im Überblick</a></p></details>')

    band = "".join(f"<span>{e(x)}</span>" for x in (
        f"{anzahl} Modelle mit Preis", f"Gewinde {z['gew_min']} bis {z['gew_max']}", "Edelstahl", "Zinkdruckguss", "Gelenkfüße",
        "Einschlagfüße für Vierkantrohr", "Schwingungsdämpfer", "Nivellierelemente", f"ab {euro(min(map(min_preis, liste)))} netto"))
    kopf = strukturierte_daten(liste)
    SEITEN.append(("", "1.0"))
    mail = e(CFG["anfrage_email"])
    return seitenrahmen("Stellfüße und Einschlagfüße kaufen, mit festem Preis | beinundfuß.de", f"""
<section class="kb-hero" data-feld="hell">
<div class="kb-hero-text">
<h1 class="kb-titel" data-rein>Stellfüße und <span>Einschlagfüße</span> mit festem Preis</h1>
<p class="kb-hero-lead" data-rein>Sagen Sie, was Ihr Fuß tragen muss. Sie bekommen passende Modelle mit Nettopreis und bestellen direkt.</p>
<p class="kb-aktionen" data-rein><a class="bf-knopf bf-knopf-gelb bf-knopf-gross" href="#berater">Passenden Fuß finden</a><a class="bf-knopf bf-knopf-rand bf-knopf-gross" href="#preise">Alle Preise ansehen</a></p>
<dl class="kb-fakten" data-rein>
<div><dt>Modelle mit Preis</dt><dd>{anzahl}</dd></div>
<div><dt>Gewinde</dt><dd>{z['gew_min']} bis {z['gew_max']}</dd></div>
<div><dt>Preise ab, netto</dt><dd>{euro(min(map(min_preis, liste)))}</dd></div>
</dl>
</div>
<figure class="kb-hero-bildfeld" data-rein><img class="kb-hero-bild" src="/assets/fuesse-freigestellt.webp" width="1344" height="390"
 alt="Stellfüße, Edelstahl-Stellbeine, ein Einschlagfuß mit Flansch und ein Nivellierelement nebeneinander"></figure>
</section>

<div class="kb-band" data-feld="dunkel" aria-hidden="true"><div class="kb-band-lauf">{band}{band}</div></div>

<section class="kb-berater" id="berater" data-feld="dunkel">
<div class="kb-berater-text">
<h2 data-rein>Beschreiben Sie Ihre Anwendung</h2>
<p data-rein>Gerät, Gewinde oder Rohrmaß, ungefähre Last, Boden: Was Sie wissen, reicht. Was fehlt, fragt der Berater nach und zeigt danach passende Füße mit Preis.</p>
<form class="kb-rechner" id="kb-rechner" data-rein>
<h3>Last pro Fuß</h3>
<p class="kb-rechner-wert"><output id="kb-last" for="kb-kg kb-anzahl">990 N</output></p>
<p class="kb-rechner-notiz" id="kb-last-notiz">pro Fuß, gleichmäßig verteilt auf 4 Füße.</p>
<p class="kb-rechner-reserve" id="kb-last-reserve">Mit Reserve: <strong>1.310 N</strong>. Auf unebenem Boden trägt ein Fuß oft kaum mit, bis das Gestell ausgerichtet ist. Dann verteilt sich die Last auf 3 Füße.</p>
<div class="kb-rechner-felder">
<label>Gewicht in kg<input type="number" id="kb-kg" min="1" max="100000" value="400" inputmode="numeric"></label>
<label>Anzahl Füße<input type="number" id="kb-anzahl" min="1" max="64" value="4" inputmode="numeric"></label>
</div>
<button type="button" class="bf-knopf bf-knopf-gelb" id="kb-last-frage" data-frage="Mein Gerät wiegt 400 kg und steht auf 4 Füßen, also etwa 990 N pro Fuß bei gleichmäßiger Verteilung, mit Reserve für unebenen Boden 1.310 N. Welche Füße passen?">Damit Füße suchen</button>
</form>
<p class="kb-ablauf" data-rein>Danach wählen Sie Ausführung und Menge und senden die Bestellung ab. Verbindlich wird sie mit unserer Auftragsbestätigung per E-Mail.</p>
</div>

<div class="kb-chat" data-rein>
<div class="kb-chat-kopf"><strong>Berater</strong><button type="button" class="kb-neu" id="ki-neu">Neu starten</button></div>
<div id="ki" class="kb-verlauf" aria-live="polite"></div>
<div class="kb-chips" id="ki-chips">{chips}</div>
<form id="ki-eingabe" class="kb-eingabe">
<textarea id="ki-text" rows="1" maxlength="1500" placeholder="Was soll der Fuß tragen?" aria-label="Ihre Frage" required></textarea>
<button class="kb-senden" type="submit">Senden</button>
</form>
<p class="kb-hinweis">Der Berater ist ein KI-System. Angaben vor der Bestellung bitte prüfen, verbindlich sind Auftragsbestätigung und Datenblatt.
Ihre Eingaben gehen zur Beantwortung an Anthropic, siehe <a href="/datenschutz/">Datenschutz</a>.</p>
</div>
</section>

<section class="kb-einsaetze" id="einsaetze" data-feld="weiss">
<div class="kb-intro">
<h2 data-rein>Wo Füße arbeiten</h2>
<p data-rein>Sechs typische Einsätze und was dafür im Sortiment steht. „Berater fragen“ beginnt das Gespräch mit genau diesem Fall.</p>
</div>
<div class="kb-akk" data-rein>{"".join(panels)}</div>
</section>

<section class="kb-preise" id="preise" data-feld="hell">
<div class="kb-preise-text">
<h2 data-rein>Preise</h2>
<p data-rein>Jeder Preis gilt netto pro Stück, zzgl. MwSt. und <a href="/versandkosten/">Versand</a>. Verkauf an Gewerbetreibende.</p>
<p data-rein>Tippen Sie auf ein Modell für Datenblatt, Ausführungen und Preise. Insgesamt {anzahl} Modelle, <a href="/produkte/">alle Produkte im Überblick</a>.</p>
</div>
<div class="kb-preise-liste">
{"".join(bars)}
</div>
</section>

<section class="kb-kontakt" id="kontakt" data-feld="weiss">
<form class="kb-coupon" id="kb-coupon" action="mailto:{mail}" method="post" enctype="text/plain" data-rein>
<div class="kb-coupon-links">
<h2>Lieber persönlich?</h2>
<p>Sonderanfertigung, große Menge oder ein Fuß ohne Online-Preis: TS Systemtechnik in Pfungstadt antwortet persönlich. Das Formular öffnet Ihr E-Mail-Programm.</p>
</div>
<div class="kb-coupon-rechts">
<label><span class="bf-unsichtbar">Name</span><input name="Name" placeholder="Name" autocomplete="name" required></label>
<label><span class="bf-unsichtbar">E-Mail</span><input name="E-Mail" type="email" placeholder="E-Mail" autocomplete="email" required></label>
<label><span class="bf-unsichtbar">Telefon</span><input name="Telefon" type="tel" placeholder="Telefon (freiwillig)" autocomplete="tel"></label>
<label><span class="bf-unsichtbar">Nachricht</span><textarea name="Nachricht" rows="3" placeholder="Was brauchen Sie?" required></textarea></label>
<button class="bf-knopf kb-coupon-senden" type="submit">Anfrage senden</button>
</div>
</form>
</section>
<dialog id="ki-bestellen" class="ki-dialog"></dialog>
<script>window.bfKi = {{ api: "{e(api)}", basis: "", email: "{mail}" }};</script>
<script src="/assets/ki.js" defer></script>""", kopf=kopf,
        beschreibung=f"{anzahl} Stellfüße, Einschlagfüße, Stellbeine und Gelenkfüße mit festem Nettopreis, Gewinde {z['gew_min']} bis {z['gew_max']}. "
                     "Anwendung beschreiben, passenden Fuß finden und direkt bestellen.")


def preis_ab_text(p):
    """„ab 7,20 €“, wenn es mehrere Preise gibt oder der Preis für die günstigste Ausführung gilt."""
    ab = (p["varianten"] and len(p["varianten"]) > 1) or p["preis_ab"]
    return ("ab " if ab else "") + euro(min_preis(p))


def seo_name(p):
    """Name mit Bauform vorne, damit „Stellfuß“ & Co. in Titel und Überschrift stehen (Herstellernamen allein sucht kaum jemand)."""
    bauform = p["merkmale"]["Bauform"]
    stamm = bauform.lower()[:-1] if bauform.lower().endswith(("ß", "n", "r", "z", "t")) else bauform.lower()
    erstes = p["name"].split()[0].lower()
    # Eigene Namen beginnen schon mit dem Produktwort (Rohrstellfuß, Gummipuffer, ...): nicht doppeln
    if any(w in erstes for w in ("fuß", "bein", "stopfen", "dämpfer", "lager", "element", "set", "puffer", "isolator", "sockel", "rolle", "heber", "feststeller")):
        return p["name"]
    if bauform == "Spezialausführung" or stamm[:6] in p["name"].lower():
        return p["name"]
    return f"{bauform} {p['name']}"


# Einleitung je Bauform für die Kategorieseiten: (Überschrift, Text)
KATEGORIEN = {
    "Stellfuß": ("Stellfüße kaufen", "Stellfüße, auch Maschinenfüße oder Nivellierfüße genannt, werden mit dem Gewinde in Maschine, Gestell oder Gerät gedreht. "
                 "Über die Spindel gleichen Sie Bodenunebenheiten aus und richten das Gerät waagerecht aus. Wichtig für die Auswahl sind Gewinde, Traglast und der Teller: "
                 "mit Gummi gegen Rutschen und Schwingungen, aus Kunststoff oder Stahl für hohe Lasten, mit Bohrung zum Verschrauben am Boden."),
    "Stellbein": ("Stellbeine kaufen", "Stellbeine sind höhenverstellbare Beine für Tische, Arbeitsplatten, Gastronomie- und Hygienebereiche. "
                  "Sie werden angeschraubt oder ins Rohr gesteckt und lassen sich in der Höhe fein einstellen. Edelstahl-Ausführungen sind leicht zu reinigen und rostfrei."),
    "Gelenkfuß": ("Gelenkfüße kaufen", "Gelenkfüße haben ein Kugelgelenk zwischen Gewinde und Teller. Der Teller legt sich auch auf schrägen oder unebenen Böden flach auf, "
                  "dadurch steht die Maschine sicher und die Last verteilt sich gleichmäßig."),
    "Einschlagfuß": ("Einschlagfüße kaufen", "Einschlagfüße werden ins offene Ende eines Vierkant- oder Rundrohrs gesteckt oder eingeschlagen und sitzen danach fest, ohne Schweißen und Bohren. "
                     "Mit Stellteil gleichen sie zusätzlich Unebenheiten aus. Entscheidend ist das passende Rohrmaß."),
    "Schwingungsdämpfer": ("Schwingungsdämpfer kaufen", "Schwingungsdämpfer und Maschinenlager trennen Maschine und Boden. Sie mindern Vibrationen und Körperschall und schützen Maschine und Umgebung."),
    "Nivellierelement": ("Nivellierelemente kaufen", "Nivellierelemente richten schwere Maschinen genau aus, oft mit Keil oder Spindel und ohne Bodenbefestigung. Sie tragen hohe Lasten und dämpfen meist zugleich."),
    "Gewindestopfen": ("Gewindestopfen kaufen", "Gewindestopfen werden in Rohre gesteckt oder eingeschlagen und bieten ein Innengewinde, in das Sie anschließend einen Stellfuß drehen."),
    "Spezialausführung": ("Spezialausführungen", "Füße und Zubehör für besondere Einsätze."),
}


def kat_url(bauform, absolut=False):
    return (SITE_URL if absolut else "") + f"/produkte/{b.slug(dict(BAUFORMEN)[bauform])}/"


def produkt_url(p, absolut=False):
    return (SITE_URL if absolut else "") + f"/produkte/{p['slug']}/"


def bild_absolut(p):
    return p["bild"] if p["bild"].startswith("http") else SITE_URL + p["bild"]


def produktdaten(p, bauform):
    """schema.org Product mit Angebot und Brotkrumen, damit Google Preis und Einordnung versteht."""
    preise = [v["preis"] for v in p["varianten"]] or [p["preis"]]
    netto = {"@type": "UnitPriceSpecification", "priceCurrency": "EUR", "valueAddedTaxIncluded": False}
    if len(preise) > 1:
        angebot = {"@type": "AggregateOffer", "priceCurrency": "EUR", "lowPrice": f"{min(preise):.2f}",
                   "highPrice": f"{max(preise):.2f}", "offerCount": len(preise)}
    else:
        angebot = {"@type": "Offer", "priceCurrency": "EUR", "price": f"{preise[0]:.2f}",
                   "priceSpecification": {**netto, "price": f"{preise[0]:.2f}"}}
    angebot.update({"url": produkt_url(p, True), "seller": {"@id": f"{SITE_URL}/#shop"},
                    "eligibleCustomerType": "https://schema.org/Business"})
    produkt = {"@type": "Product", "name": seo_name(p), "sku": p["sku"], "description": p["kurz"],
               "image": bild_absolut(p), "url": produkt_url(p, True), "category": bauform, "offers": angebot}
    if p["marke"]:
        produkt["brand"] = {"@type": "Brand", "name": p["marke"]}
    kette = [("Startseite", f"{SITE_URL}/"), ("Produkte", f"{SITE_URL}/produkte/"),
             (dict(BAUFORMEN)[bauform], kat_url(bauform, True)), (seo_name(p), produkt_url(p, True))]
    krumen = {"@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i + 1, "name": n, "item": u} for i, (n, u) in enumerate(kette)]}
    daten = {"@context": "https://schema.org", "@graph": [produkt, krumen]}
    return f'<script type="application/ld+json">{json.dumps(daten, ensure_ascii=False)}</script>'


def produktseite(p, verwandte, mehrzahl):
    """Eigene Seite je Produkt: Daten, Ausführungen mit Preis, Bestellen und Berater fragen."""
    bauform = p["merkmale"]["Bauform"]
    frage = f"Ich interessiere mich für „{p['name']}“ ({p['sku']}). Welche Ausführung passt für meine Anwendung?"
    bestellen = f"/?bestellen={quote(p['sku'])}#berater"
    fragen = f"/?frage={quote(frage)}#berater"
    daten = "".join(f"<tr><th scope=\"row\">{e(k)}</th><td>{e(v)}</td></tr>" for k, v in p["merkmale"].items() if v)
    if p["marke"]:
        daten = f'<tr><th scope="row">Hersteller</th><td>{e(p["marke"])}</td></tr>' + daten
    ausf = ""
    if p["varianten"]:
        zeilen = "".join(f'<tr><td>{e(v["ausfuehrung"])}</td><td class="pr-nr">{e(v["sku"])}</td><td class="pr-zahl">{euro(v["preis"])}</td>'
                         f'<td class="pr-zahl"><a class="pr-pille" href="/?bestellen={quote(p["sku"])}&amp;variante={quote(v["sku"])}#berater">Bestellen</a></td></tr>'
                         for v in p["varianten"])
        ausf = (f'<h2>Ausführungen und Preise</h2><div class="pr-tabelle"><table><thead><tr><th>Ausführung</th><th class="pr-nr">Artikelnr.</th>'
                f'<th class="pr-zahl">Preis netto/Stück</th><th class="pr-zahl"><span class="bf-unsichtbar">Bestellen</span></th></tr></thead><tbody>{zeilen}</tbody></table></div>')
    if p["preis_ab"]:
        ausf += "<p class=\"pr-notiz\">Der Preis gilt für die günstigste Ausführung der Serie. Den Preis für Ihre Größe bestätigen wir mit der Auftragsbestätigung.</p>"
    optionen = p.get("optionen") or {}
    if optionen:
        ausf += "".join(f'<h2>{e(m)} wählen</h2><p class="pr-wahl">' + "".join(
            f'<a class="pr-pille" href="/?bestellen={quote(p["sku"])}&amp;{quote("opt-" + m)}={quote(x)}#berater">{e(x)}</a>' for x in w)
            + '</p><p class="pr-notiz">Ein Klick öffnet das Bestellformular mit dieser Auswahl.</p>' for m, w in optionen.items())
    mehr = "".join(f'<li><a href="{produkt_url(q)}"><span>{e(seo_name(q))}</span><span class="pr-zahl">{preis_ab_text(q)}</span></a></li>'
                   for q in verwandte)
    inhalt = f"""<article class="pr-seite" data-feld="weiss">
<nav class="pr-krumen" aria-label="Brotkrumen"><a href="/">Startseite</a> / <a href="/produkte/">Produkte</a> / <a href="{kat_url(bauform)}">{e(mehrzahl)}</a></nav>
<div class="pr-kopf">
<figure class="pr-bild"><img src="{e(p['bild'])}" alt="{e(seo_name(p))}" width="480" height="480" loading="eager"></figure>
<div class="pr-info">
<h1>{e(seo_name(p))}</h1>
<p class="pr-kurz">{e(p['kurz'])}</p>
<p class="pr-preis">{preis_ab_text(p)} <span>netto pro Stück, zzgl. MwSt. und <a href="/versandkosten/">Versand</a></span></p>
<p class="pr-aktionen"><a class="bf-knopf bf-knopf-gelb bf-knopf-gross" href="{bestellen}">Bestellen</a><a class="bf-knopf bf-knopf-rand bf-knopf-gross" href="{fragen}">Berater fragen</a></p>
<p class="pr-notiz">Artikelnummer {e(p['sku'])}. Verkauf an Gewerbetreibende. Verbindlich wird die Bestellung mit unserer Auftragsbestätigung.</p>
</div>
</div>
<div class="pr-details">
<div>{ausf}<h2>Technische Daten</h2><div class="pr-tabelle"><table class="pr-daten"><tbody>{daten}</tbody></table></div></div>
{f'<aside><h2>Weitere {e(mehrzahl)}</h2><ul class="pr-liste">{mehr}</ul></aside>' if mehr else ''}
</div>
</article>"""
    besch = f"{seo_name(p)}: {p['kurz']} {preis_ab_text(p)} netto. Direkt bestellen bei beinundfuß.de."
    pfad = f"produkte/{p['slug']}/"
    SEITEN.append((pfad, "0.8"))
    return seitenrahmen(f"{seo_name(p)} kaufen | beinundfuß.de", inhalt, beschreibung=besch[:300], kopf=PRODUKT_CSS + produktdaten(p, bauform), pfad=pfad,
                        seite="produkt")


def produktuebersicht(liste):
    gruppen = {}
    for p in liste:
        gruppen.setdefault(p["merkmale"]["Bauform"], []).append(p)
    teile = []
    for bauform, mehrzahl in BAUFORMEN:
        l = sorted(gruppen.get(bauform, []), key=lambda q: (min_preis(q), q["name"]))
        if not l:
            continue
        zeilen = "".join(f'<li><a href="{produkt_url(q)}"><span>{e(q["name"])}</span><span class="pr-zahl">{preis_ab_text(q)}</span></a></li>' for q in l[:10])
        teile.append(f'<section id="{b.slug(bauform)}"><h2><a href="{kat_url(bauform)}">{e(mehrzahl)}</a> <span>{len(l)} Modelle ab {euro(min_preis(l[0]))}</span></h2>'
                     f'<ul class="pr-liste pr-spalten">{zeilen}</ul>'
                     + (f'<p><a class="pr-mehr" href="{kat_url(bauform)}">Alle {len(l)} {e(mehrzahl)} ansehen</a></p>' if len(l) > 10 else "") + '</section>')
    inhalt = (f'<article class="pr-seite" data-feld="weiss"><nav class="pr-krumen" aria-label="Brotkrumen"><a href="/">Startseite</a> / Produkte</nav>'
              f'<h1>Alle Produkte mit Preis</h1><p class="pr-kurz">{len(liste)} Stellfüße, Stellbeine, Gelenkfüße, Einschlagfüße und mehr. '
              f'Alle Preise netto pro Stück. Unsicher, welcher passt? <a href="/#berater">Fragen Sie den Berater.</a></p>'
              f'<nav class="pr-sprung" aria-label="Bauformen">{"".join(f"<a href=\"{kat_url(bf)}\">{e(mz)}</a>" for bf, mz in BAUFORMEN if bf in gruppen)}</nav>'
              f'{"".join(teile)}</article>')
    SEITEN.append(("produkte/", "0.9"))
    return seitenrahmen("Stellfüße, Einschlagfüße und Maschinenfüße: alle Produkte mit Preis | beinundfuß.de", inhalt,
                        beschreibung=f"Alle {len(liste)} Stellfüße, Stellbeine, Gelenkfüße, Einschlagfüße, Schwingungsdämpfer und Nivellierelemente mit festem Nettopreis.",
                        kopf=PRODUKT_CSS, pfad="produkte/")


def werte(q, merkmal):
    """Einzelwerte eines Merkmals für die Filter, vereinheitlicht („Edelstahl 1.4301“ zählt als Edelstahl)."""
    roh = [w.strip() for w in str(q["merkmale"].get(merkmal) or "").split(",") if w.strip()]
    if merkmal == "Material":
        roh = ["Edelstahl" if w.startswith("Edelstahl") else "Gummi" if w.startswith("Gummi") else w for w in roh]
    if merkmal == "Gewinde":
        roh = [w for w in roh if re.fullmatch(r"M\d+", w)]
    return list(dict.fromkeys(roh))


def zahl(text):
    m = re.search(r"\d+(?:[.,]\d+)?", text or "")
    return float(m.group().replace(",", ".")) if m else 0


# Filter auf den Kategorieseiten: (Merkmal, Überschrift)
FILTER = [("Material", "Material"), ("Gewinde", "Gewinde"), ("Rohrmaß", "Rohrmaß")]


def sortierdaten(q):
    """Daten am Listeneintrag für Sortieren und Filtern im Browser (kategorie.js); ohne JavaScript bleibt die Liste nach Preis."""
    gew = [int(w[1:]) for w in werte(q, "Gewinde")]
    groesse = zahl(q["merkmale"].get("Rohrmaß")) or zahl(q["merkmale"].get("Durchmesser"))
    attr = {"preis": f"{min_preis(q):.2f}", "nach-gewinde": min(gew) if gew else 999, "nach-groesse": groesse or 9999}
    for m, _ in FILTER:
        attr[b.slug(m)] = "|".join(werte(q, m))
    return "".join(f' data-{k}="{e(str(v))}"' for k, v in attr.items())


def sortierleiste(l):
    """Sortieren und Filter über der Modellliste. Erscheint erst mit JavaScript (hidden), sonst stört sie nicht."""
    gruppen = ""
    for m, titel in FILTER:
        alle = sorted({w for q in l for w in werte(q, m)}, key=lambda w: (zahl(w), w) if m != "Material" else (w,))
        if len(alle) < 2:
            continue
        knoepfe = "".join(f'<button type="button" class="pr-pille" aria-pressed="false" data-wert="{e(w)}">{e(w)}</button>' for w in alle)
        gruppen += f'<div class="pr-filter-gruppe" data-merkmal="{b.slug(m)}"><span class="pr-filter-titel">{e(titel)}</span><div class="pr-wahl">{knoepfe}</div></div>'
    return (f'<div class="pr-werkzeug" hidden><label class="pr-sortieren">Sortieren nach <select id="pr-sortierung">'
            '<option value="preis">Preis aufsteigend</option><option value="preis-ab">Preis absteigend</option>'
            '<option value="gewinde">Gewinde, klein nach groß</option><option value="groesse">Größe (Teller oder Rohr), klein nach groß</option>'
            f'</select></label>{gruppen}'
            f'<p class="pr-treffer" aria-live="polite"><span><span id="pr-anzahl">{len(l)}</span> von {len(l)} Modellen</span>'
            '<button type="button" class="pr-zuruecksetzen" id="pr-zuruecksetzen" hidden>Filter zurücksetzen</button></p>'
            '<p class="pr-leer" id="pr-leer" hidden>Kein Modell passt zu dieser Auswahl. Nehmen Sie einen Filter heraus oder fragen Sie den Berater.</p></div>')


def kategorieseite(bauform, l):
    """Seite je Bauform („Stellfüße kaufen“): Einleitung und alle Modelle, für Suchen wie „Stellfuß“ oder „Stellbein“."""
    mehrzahl = dict(BAUFORMEN)[bauform]
    titel, text = KATEGORIEN[bauform]
    l = sorted(l, key=lambda q: (min_preis(q), q["name"]))
    zeilen = "".join(f'<li{sortierdaten(q)}><a href="{produkt_url(q)}"><span>{e(q["name"])}</span><span class="pr-zahl">{preis_ab_text(q)}</span></a></li>' for q in l)
    frage = f"Ich suche {mehrzahl}. Welche passen für meine Anwendung?"
    inhalt = (f'<article class="pr-seite" data-feld="weiss"><nav class="pr-krumen" aria-label="Brotkrumen"><a href="/">Startseite</a> / '
              f'<a href="/produkte/">Produkte</a> / {e(mehrzahl)}</nav><h1>{e(titel)}</h1><p class="pr-kurz">{e(text)}</p>'
              f'<p class="pr-kurz">{len(l)} Modelle ab {euro(min_preis(l[0]))} netto pro Stück. Unsicher, welcher passt? '
              f'<a href="/?frage={quote(frage)}#berater">Fragen Sie den Berater.</a></p>'
              f'<section>{sortierleiste(l)}<ul class="pr-liste pr-spalten" id="pr-modelle">{zeilen}</ul></section></article>')
    pfad = kat_url(bauform)[1:]
    SEITEN.append((pfad, "0.9"))
    krumen = {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": "Startseite", "item": f"{SITE_URL}/"},
        {"@type": "ListItem", "position": 2, "name": "Produkte", "item": f"{SITE_URL}/produkte/"},
        {"@type": "ListItem", "position": 3, "name": mehrzahl, "item": kat_url(bauform, True)}]}
    return seitenrahmen(f"{titel}: {len(l)} Modelle mit Preis | beinundfuß.de", inhalt,
                        beschreibung=f"{len(l)} {mehrzahl} ab {euro(min_preis(l[0]))} netto. {text}"[:300],
                        kopf=PRODUKT_CSS + '<script src="/assets/kategorie.js" defer></script>'
                        + f'<script type="application/ld+json">{json.dumps(krumen, ensure_ascii=False)}</script>', pfad=pfad, seite="kategorie")


PRODUKT_CSS = '<link rel="stylesheet" href="/assets/produkte.css">'
FAVICON = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="7" fill="#111827"/>'
           '<rect x="14" y="4" width="4" height="15" rx="1" fill="#fece14"/><path d="M14 7h4M14 10h4M14 13h4M14 16h4" stroke="#111827" stroke-width="1"/>'
           '<path d="M8 26l3-6h10l3 6z" fill="#fece14"/></svg>')
VERSAND = json.loads((ROOT / "daten/versandkosten.json").read_text(encoding="utf-8"))


def kg_text(x):
    return f"{x:g}".replace(".", ",") + " kg"


def versandseite():
    """Versandkosten pro Paket (GLS ab Pfungstadt), Deutschland und Europa. Länder mit gleichen Preisen stehen in einer Zeile."""
    de = VERSAND["deutschland"]
    zeilen_de = "".join(f'<tr><td>bis {kg_text(g)}</td><td class="pr-zahl">{euro(x)}</td></tr>' for g, x in zip(de["bis_kg"], de["preise"]))
    eu = VERSAND["europa"]
    gruppen = {}
    for l in eu["laender"]:
        gruppen.setdefault((tuple(l["preise"]), bool(l.get("luftfracht"))), []).append(l["land"])
    reihen = sorted(gruppen.items(), key=lambda kv: kv[1][0].replace("Ö", "Oe"))  # alphabetisch, damit man sein Land findet
    kopf = "".join(f'<th class="pr-zahl">{kg_text(g)}</th>' for g in eu["bis_kg"])
    zeilen_eu = "".join(f'<tr><th scope="row">{e(", ".join(laender))}{" ¹" if luft else ""}</th>'
                        + "".join(f'<td class="pr-zahl">{euro(x)}</td>' for x in preise) + "</tr>"
                        for (preise, luft), laender in reihen)
    inhalt = (f'<article class="pr-seite" data-feld="weiss"><nav class="pr-krumen" aria-label="Brotkrumen"><a href="/">Startseite</a> / Versandkosten</nav>'
              '<h1>Versandkosten</h1><p class="pr-kurz">Wir versenden mit GLS ab Pfungstadt. Die Versandkosten gelten pro Paket, netto zzgl. MwSt., '
              'und richten sich nach Land und Paketgewicht. Mehrere Artikel einer Bestellung packen wir zusammen.</p>'
              f'<section><h2>Deutschland</h2><div class="pr-tabelle pr-versand-de"><table><thead><tr><th>Paketgewicht</th><th class="pr-zahl">Preis netto</th></tr></thead>'
              f'<tbody>{zeilen_de}</tbody></table></div></section>'
              f'<section><h2>Europa</h2><p class="pr-notiz">Preis pro Paket nach Gewicht bis …</p><div class="pr-tabelle pr-versand-eu"><table><thead><tr><th>Land</th>{kopf}</tr></thead>'
              f'<tbody>{zeilen_eu}</tbody></table></div>'
              '<p class="pr-notiz">¹ Versand per Luftfracht. Berechnet wird nach Volumengewicht, wenn es höher ist als das tatsächliche Gewicht.</p></section>'
              '<section><h2>Gut zu wissen</h2><ul class="pr-punkte">'
              '<li>Ist ein Paket groß und leicht, zählt das Volumengewicht: Länge × Breite × Höhe in cm geteilt durch 6.000, höchstens 30 kg.</li>'
              '<li>Für Pakete über 40 kg, Paletten oder Expressversand machen wir Ihnen gern ein Angebot: '
              f'<a href="mailto:{e(CFG["anfrage_email"])}">{e(CFG["anfrage_email"])}</a>.</li>'
              '<li>Die Versandkosten stellen wir mit der Auftragsbestätigung in Rechnung.</li></ul></section></article>')
    return seitenrahmen("Versandkosten | beinundfuß.de", inhalt, pfad="versandkosten/", kopf=PRODUKT_CSS,
                        beschreibung="Versandkosten von beinundfuß.de: Versand mit GLS ab Pfungstadt nach Deutschland und Europa, Preise pro Paket nach Gewicht.")


def main():
    produkte = b.produkte_laden()
    neutral(produkte)
    liste = katalog(produkte)
    KATALOG.parent.mkdir(parents=True, exist_ok=True)
    KATALOG.write_text(json.dumps(liste, ensure_ascii=False, indent=0), encoding="utf-8")
    if INTERN.exists():
        daten = bezugsquellen(produkte)
        ziel = INTERN / "ki-bezugsquellen.json"
        ziel.write_text(json.dumps(daten, ensure_ascii=False, indent=1), encoding="utf-8")
        # Für das GitHub-Secret BEZUGSQUELLEN: gzip + base64, damit es unter die 48-KB-Grenze passt
        packung = base64.b64encode(gzip.compress(json.dumps(daten, ensure_ascii=False, separators=(",", ":")).encode(), 9, mtime=0)).decode()
        (INTERN / "ki-bezugsquellen-fuer-github.txt").write_text(packung, encoding="ascii")
        # Lokale Kopie für Tests; steht in .gitignore
        (ROOT / "ki/worker/src/bezugsquellen.json").write_text(json.dumps(daten, ensure_ascii=False), encoding="utf-8")
        print(f"intern: {ziel} (GitHub-Secret: {len(packung) // 1024} KB)")

    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "assets/skizzen").mkdir(parents=True)
    shutil.copytree(b.THEME / "assets/anwendungen", OUT / "assets/anwendungen")
    shutil.copytree(ROOT / "ki/seite/fonts", OUT / "assets/fonts")
    for datei in ("ki.js", "ki.css", "produkte.css", "seite.js", "kategorie.js", "zaehlen.js", "statistik.js", "fuesse-freigestellt.webp", "vorschau.jpg"):
        shutil.copy(ROOT / "ki/seite" / datei, OUT / "assets" / datei)
    # Logo im Browser-Tab: gelber Stellfuß (Gewindespindel und Teller) auf Dunkel (Lenn, 22.10.2026); PNGs für Apple und Google
    (OUT / "assets/favicon.svg").write_text(FAVICON, encoding="utf-8")
    for datei in ("favicon-48.png", "favicon-180.png"):
        shutil.copy(ROOT / "ki/seite" / datei, OUT / "assets" / datei)
    for p in produkte:
        if b.preise(p) and not p["bild"]:
            (OUT / "assets/skizzen" / f"{p['slug']}.svg").write_text(zeichnung(p, klein=True), encoding="utf-8")

    def schreibe(pfad, text):
        ziel = OUT / pfad / "index.html" if pfad else OUT / "index.html"
        ziel.parent.mkdir(parents=True, exist_ok=True)
        ziel.write_text(text, encoding="utf-8")

    slugs = {p["sku"]: p["slug"] for p in produkte}
    liste = [{**k, "slug": slugs[k["sku"]]} for k in liste]
    schreibe("", beraterseite(liste))
    # Produktseiten für Google; Katalog (nur Verkaufspreise) als Datei, damit „Bestellen“ auf der Startseite das Formular öffnet
    mehrzahl = dict(BAUFORMEN)
    schreibe("produkte", produktuebersicht(liste))
    for bauform, _ in BAUFORMEN:
        l = [q for q in liste if q["merkmale"]["Bauform"] == bauform]
        if l:
            schreibe(kat_url(bauform)[1:-1], kategorieseite(bauform, l))
    for p in liste:
        gleich = sorted((q for q in liste if q["merkmale"]["Bauform"] == p["merkmale"]["Bauform"] and q["sku"] != p["sku"]),
                        key=lambda q: abs(min_preis(q) - min_preis(p)))[:6]
        schreibe(f"produkte/{p['slug']}", produktseite(p, gleich, mehrzahl.get(p["merkmale"]["Bauform"], p["merkmale"]["Bauform"])))
    shutil.copy(KATALOG, OUT / "assets/katalog.json")
    # Alte Adresse der Kategorie (bis 20.10.2026 „Gewindeeinsätze“) leitet weiter
    schreibe("produkte/gewindeeinsaetze", '<!doctype html><meta charset="utf-8"><title>Gewindestopfen</title>'
             f'<link rel="canonical" href="{kat_url("Gewindestopfen", absolut=True)}">'
             f'<meta http-equiv="refresh" content="0; url={b.BASIS}{kat_url("Gewindestopfen")}"><a href="{kat_url("Gewindestopfen")}">Gewindestopfen</a>')
    # Alte Produktadressen (mit Herstellernamen, bis 22.10.2026) leiten auf die neuen weiter
    for p in produkte:
        if p.get("slug_alt") and p["slug_alt"] != p["slug"] and b.preise(p):
            schreibe(f"produkte/{p['slug_alt']}", f'<!doctype html><meta charset="utf-8"><title>{e(p["name"])}</title>'
                     f'<meta name="robots" content="noindex"><link rel="canonical" href="{produkt_url(p, absolut=True)}">'
                     f'<meta http-equiv="refresh" content="0; url={b.BASIS}{produkt_url(p)}"><a href="{produkt_url(p)}">{e(p["name"])}</a>')
    schreibe("versandkosten", versandseite())
    SEITEN.append(("versandkosten/", "0.4"))
    shutil.copy(ROOT / "daten/versandkosten.json", OUT / "assets/versandkosten.json")
    shutil.copy(ROOT / "daten/versandkosten.json", ROOT / "ki/worker/src/versandkosten.json")  # Lieferländer und EU-Kennung für /bestellen
    mail = e(CFG["anfrage_email"])
    schreibe("kontakt", textseite("Kontakt", f"<p>Fragen zu Produkten, Sonderanfertigungen oder Mengenpreisen? Schreiben Sie uns.</p>"
                                               f'<p><a class="btn" href="mailto:{mail}">{mail}</a></p>'
                                               f"<p>{e(CFG['betreiber_zeile'])}</p>", "kontakt/",
                                    "Kontakt zu beinundfuß.de: Fragen zu Stellfüßen, Einschlagfüßen, Sonderanfertigungen und Mengenpreisen.", "0.5"))
    for pfad, titel in (("impressum", "Impressum"), ("datenschutz", "Datenschutzerklärung"), ("agb", "Allgemeine Geschäftsbedingungen")):
        datei = b.RECHT / f"{pfad}.html"
        if not datei.exists():
            if pfad == "agb":
                continue
            raise SystemExit(f"Rechtstext fehlt: {datei}")
        schreibe(pfad, textseite(titel, datei.read_text(encoding="utf-8"), f"{pfad}/", prio="0.1"))
    # Statistik für Lenn (anonyme Zählung, Bericht nur mit Schlüssel); nicht in der Sitemap, noindex
    schreibe("statistik", seitenrahmen("Statistik | beinundfuß.de", '<article class="pr-seite" data-feld="weiss"><h1>Statistik</h1>'
        '<p class="pr-kurz">Besucher, Berater und Bestellungen als Tagessummen. Gezählt wird ohne Cookies und ohne Personenbezug.</p>'
        '<form id="st-form" class="st-form"><label>Schlüssel<input id="st-schluessel" type="password" autocomplete="current-password" required></label>'
        '<label>Zeitraum<select id="st-tage"><option value="7">7 Tage</option><option value="30" selected>30 Tage</option>'
        '<option value="90">90 Tage</option><option value="365">1 Jahr</option></select></label>'
        '<button class="bf-knopf bf-knopf-gelb" type="submit">Anzeigen</button></form><p id="st-meldung" class="pr-notiz" aria-live="polite"></p>'
        '<div id="st-ergebnis"></div></article>',
        kopf=PRODUKT_CSS + '<script src="/assets/statistik.js" defer></script>', index=False, seite="statistik"))
    (OUT / "404.html").write_text(seitenrahmen("Seite nicht gefunden | beinundfuß.de", '<section class="bf-text" data-feld="weiss">'
                                               '<h1>Seite nicht gefunden</h1><p>Diese Seite gibt es nicht. <a href="/">Zum Berater</a></p></section>',
                                               index=False), encoding="utf-8")
    (OUT / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {SITE_URL}/sitemap.xml\n", encoding="utf-8")
    (OUT / "sitemap.xml").write_text(sitemap(), encoding="utf-8")

    if b.BASIS:
        for f in OUT.rglob("*.html"):
            t = f.read_text(encoding="utf-8")
            t = re.sub(r'((?:href|src)=")/(?!/)', rf"\1{b.BASIS}/", t)
            f.write_text(t.replace('basis: ""', f'basis: "{b.BASIS}"'), encoding="utf-8")
    if (ROOT / "CNAME").exists():
        shutil.copy(ROOT / "CNAME", OUT / "CNAME")
    print(f"site/: KI-Berater, {len(liste)} Produkte mit Preis im Katalog ({KATALOG.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
