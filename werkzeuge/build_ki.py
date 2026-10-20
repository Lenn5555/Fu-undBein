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
from html import escape as e
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_site as b  # noqa: E402
from zeichnung import zeichnung  # noqa: E402

ROOT, OUT, CFG = b.ROOT, b.OUT, b.CFG
b.NAV = [("Berater", "/"), ("Kontakt", "/kontakt/")]
INTERN = Path("/mnt/project-files/katalog/intern")
KATALOG = ROOT / "ki/worker/src/katalog.json"


def ohne_html(text):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text or "")).strip()


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
            "optionen": {"Gewinde": p["merkmale"]["Gewinde"]}
                        if not p["varianten"] and isinstance(p["merkmale"].get("Gewinde"), list) and len(p["merkmale"]["Gewinde"]) > 1 else {},
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
    (10, "Gestelle", "Einschlagfüße für Vierkant- und Rundrohr: ins offene Rohrende schlagen, ohne Schweißen und Bohren. {Einschlagfuß} Einschlagfüße und {Gewindeeinsatz} Gewindeeinsätze.",
     "Ich brauche Einschlagfüße für eine Werkbank aus Vierkantrohr."),
]

# Reihenfolge der Preisliste nach Bauform, mit Mehrzahl für die Überschrift
BAUFORMEN = [("Stellfuß", "Stellfüße"), ("Stellbein", "Stellbeine"), ("Gelenkfuß", "Gelenkfüße"), ("Einschlagfuß", "Einschlagfüße"),
             ("Schwingungsdämpfer", "Schwingungsdämpfer"), ("Nivellierelement", "Nivellierelemente"),
             ("Gewindeeinsatz", "Gewindeeinsätze"), ("Spezialausführung", "Spezialausführungen")]


# Zwei kleine Szenen für den Vergleich: Stellfuß wird herausgedreht, Rohrrahmen wird auf Einschlagfüße gesetzt
SZENE_DREHEN = """<svg class="kb-szene" viewBox="0 0 420 260" role="img" aria-label="Ein schiefer Tisch wird mit einem Stellfuß ausgerichtet, die Libelle wandert in die Mitte">
<rect x="0" y="236" width="420" height="24" fill="#d1d5db"/>
<g class="an-tisch">
<rect x="30" y="70" width="360" height="22" rx="2" fill="#111827"/>
<rect x="170" y="50" width="80" height="20" rx="10" fill="#e5e7eb"/><circle class="an-blase" cx="210" cy="60" r="7" fill="#16a34a"/>
<rect x="52" y="92" width="16" height="132" fill="#374151"/><rect x="40" y="224" width="40" height="12" rx="2" fill="#111827"/>
<g class="an-spindel"><rect x="356" y="186" width="8" height="42" fill="#9ca3af"/><rect class="an-mutter" x="348" y="204" width="24" height="9" fill="#fece14"/><rect x="340" y="222" width="40" height="14" rx="2" fill="#111827"/></g>
<rect x="351" y="92" width="18" height="106" fill="#374151"/>
</g>
</svg>"""

SZENE_SCHLAGEN = """<svg class="kb-szene" viewBox="0 0 420 260" role="img" aria-label="Ein Rohrrahmen wird auf zwei Einschlagfüße gesetzt, die Zapfen verschwinden im Rohr, bis der Rahmen bündig auf den Füßen steht">
<rect x="0" y="236" width="420" height="24" fill="#d1d5db"/>
<g fill="#6b7280"><rect x="55" y="196" width="14" height="30"/><rect x="351" y="196" width="14" height="30"/></g>
<g fill="#4b5563"><rect x="53" y="202" width="18" height="3"/><rect x="53" y="210" width="18" height="3"/><rect x="53" y="218" width="18" height="3"/>
<rect x="349" y="202" width="18" height="3"/><rect x="349" y="210" width="18" height="3"/><rect x="349" y="218" width="18" height="3"/></g>
<g fill="#111827"><rect x="42" y="226" width="40" height="10" rx="2"/><rect x="338" y="226" width="40" height="10" rx="2"/></g>
<g class="an-rahmen">
<rect x="30" y="70" width="360" height="22" rx="2" fill="#111827"/>
<rect x="52" y="92" width="20" height="134" fill="#374151"/><rect x="348" y="92" width="20" height="134" fill="#374151"/>
</g>
<g class="an-text"><text x="210" y="252" text-anchor="middle" font-size="13" font-family="Poppins, Arial, sans-serif" fill="#111827">einstecken, fertig: ohne Schweißen und Bohren</text></g>
</svg>"""

BEISPIELE = [
    "Stellfuß M12 für eine Maschine, ca. 400 kg",
    "Einschlagfuß für 40er Vierkantrohr",
    "Edelstahl für die Lebensmittelindustrie",
    "Ich weiß nicht, was ich brauche",
]


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


def seitenrahmen(titel, inhalt, beschreibung="", kopf="", feld="bone"):
    """Eigener Rahmen der KI-Seite: feste helle Kopfleiste, dunkler Fuß mit Wortmarke."""
    nav = "".join(f'<a href="{h}">{t}</a>' for t, h in (("Berater", "/#berater"), ("Einsätze", "/#einsaetze"), ("Preise", "/#preise"), ("Kontakt", "/#kontakt")))
    mail = e(CFG["anfrage_email"])
    return f"""<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(titel)}</title>
<meta name="description" content="{e(beschreibung or 'Stellfüße, Einschlagfüße und Maschinenfüße mit festem Nettopreis. Beschreiben Sie Ihre Anwendung und bestellen Sie den passenden Fuß.')}">
<meta name="theme-color" content="#111827">
<link rel="icon" href="/assets/favicon.svg" type="image/svg+xml">
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
<nav class="bf-fuss-links" aria-label="Seite"><a href="/#berater">Berater</a><a href="/#einsaetze">Einsätze</a><a href="/#preise">Preise</a><a href="/#kontakt">Kontakt</a></nav>
<nav class="bf-fuss-links" aria-label="Rechtliches"><a href="/kontakt/">Kontaktseite</a><a href="/impressum/">Impressum</a><a href="/datenschutz/">Datenschutz</a>{b.AGB_LINK}</nav>
<div class="bf-fuss-adresse"><p>{e(CFG['betreiber_zeile'])}<br>TS Systemtechnik, Pfungstadt</p><p><a href="mailto:{mail}">{mail}</a></p></div>
</div>
<div class="bf-fuss-ende"><p>Alle Preise netto zzgl. MwSt. und Versand. Verkauf an Gewerbetreibende.</p><a class="bf-knopf bf-knopf-klein" href="#inhalt">Nach oben</a></div>
</footer>
<script src="/assets/seite.js" defer></script>
</body>
</html>
"""


def textseite(titel, absaetze):
    return seitenrahmen(f"{titel} | beinundfuß.de", f'<section class="bf-text" data-feld="weiss"><h1>{e(titel)}</h1>{absaetze}</section>')


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
        auswahl = [l[round(k * (len(l) - 1) / 5)] for k in range(6)] if len(l) > 6 else l
        auswahl = list(dict.fromkeys(p["sku"] for p in auswahl))
        zeilen = "".join(
            f'<li><button type="button" data-frage="{e("Ich interessiere mich für „" + p["name"] + "“ (" + p["sku"] + "). Welche Ausführungen gibt es?")}">'
            f'<span>{e(p["name"])}</span><span class="kb-preis">{"ab " if (p["varianten"] and len(p["varianten"]) > 1) or p["preis_ab"] else ""}{euro(min_preis(p))}</span></button></li>'
            for p in (next(q for q in l if q["sku"] == s) for s in auswahl))
        bars.append(f'<details class="kb-bar"{" open" if i == 0 else ""}><summary><span>{e(mehrzahl)}</span>'
                    f'<span class="kb-bar-info">{len(l)} Modelle ab {euro(min_preis(l[0]))}</span></summary><ul>{zeilen}</ul></details>')

    band = "".join(f"<span>{e(x)}</span>" for x in (
        f"{anzahl} Modelle mit Preis", f"Gewinde {z['gew_min']} bis {z['gew_max']}", "Edelstahl", "Zinkdruckguss", "Gelenkfüße",
        "Einschlagfüße für Vierkantrohr", "Schwingungsdämpfer", "Nivellierelemente", f"ab {euro(min(map(min_preis, liste)))} netto"))
    stell = sorted(gruppen["Stellfuß"], key=min_preis)
    schlag = sorted(gruppen["Einschlagfuß"], key=min_preis)
    kopf = ('<meta property="og:title" content="beinundfuß.de: Stellfüße und Einschlagfüße mit Preis">'
            '<meta property="og:description" content="Beschreiben Sie Ihre Anwendung und bekommen Sie passende Füße mit festem Nettopreis.">')
    mail = e(CFG["anfrage_email"])
    return seitenrahmen("beinundfuß.de: Stellfüße und Einschlagfüße mit Preis", f"""
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
<p class="kb-rechner-wert"><output id="kb-last" for="kb-kg kb-anzahl">1.310 N</output></p>
<p class="kb-rechner-notiz" id="kb-last-notiz">pro Fuß, gerechnet mit 3 tragenden Füßen, weil auf unebenem Boden oft einer kaum Last trägt.</p>
<div class="kb-rechner-felder">
<label>Gewicht in kg<input type="number" id="kb-kg" min="1" max="100000" value="400" inputmode="numeric"></label>
<label>Anzahl Füße<input type="number" id="kb-anzahl" min="1" max="64" value="4" inputmode="numeric"></label>
</div>
<button type="button" class="bf-knopf bf-knopf-gelb" id="kb-last-frage" data-frage="Mein Gerät wiegt 400 kg und steht auf 4 Füßen, also etwa 1.310 N pro Fuß. Welche Füße passen?">Damit Füße suchen</button>
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

<section class="kb-vergleich" data-feld="hell">
<div class="kb-intro">
<h2 data-rein>Zwei Arten zu stehen</h2>
<p data-rein>Ein Stellfuß wird ins Gewinde gedreht, {z['gew_min']} bis {z['gew_max']}, und gleicht über die Spindel Unebenheiten aus.
Ein Einschlagfuß wird ins offene Rohrende eingesetzt und hält ohne Schweißen und Bohren.</p>
</div>
<div class="kb-specimen">
<figure data-rein>{SZENE_DREHEN}<h3>Drehen</h3><figcaption>Stellfuß: {len(stell)} Modelle ab {euro(min_preis(stell[0]))}</figcaption></figure>
<figure data-rein>{SZENE_SCHLAGEN}<h3>Einstecken</h3><figcaption>Einschlagfuß: {len(schlag)} Modelle ab {euro(min_preis(schlag[0]))}</figcaption></figure>
</div>
</section>

<section class="kb-preise" id="preise" data-feld="weiss">
<div class="kb-preise-text">
<h2 data-rein>Preise</h2>
<p data-rein>Jeder Preis gilt netto pro Stück, zzgl. MwSt. und Versand. Verkauf an Gewerbetreibende.</p>
<p data-rein>Tippen Sie auf ein Modell, und der Berater nennt Ausführungen, Maße und Traglast. Insgesamt {anzahl} Modelle.</p>
</div>
<div class="kb-preise-liste">
{"".join(bars)}
</div>
</section>

<section class="kb-kontakt" id="kontakt" data-feld="hell">
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
<script src="/assets/ki.js" defer></script>""", kopf=kopf)


def main():
    produkte = b.produkte_laden()
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
    for datei in ("ki.js", "ki.css", "seite.js", "fuesse-freigestellt.webp"):
        shutil.copy(ROOT / "ki/seite" / datei, OUT / "assets" / datei)
    (OUT / "assets/favicon.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="6" fill="#fece14"/>'
        '<path d="M16 5v15M11 9h10" stroke="#111827" stroke-width="3" fill="none"/><rect x="7" y="21" width="18" height="5" fill="#111827"/></svg>',
        encoding="utf-8")
    for p in produkte:
        if b.preise(p) and not p["bild"]:
            (OUT / "assets/skizzen" / f"{p['slug']}.svg").write_text(zeichnung(p, klein=True), encoding="utf-8")

    def schreibe(pfad, text):
        ziel = OUT / pfad / "index.html" if pfad else OUT / "index.html"
        ziel.parent.mkdir(parents=True, exist_ok=True)
        ziel.write_text(text, encoding="utf-8")

    schreibe("", beraterseite(liste))
    mail = e(CFG["anfrage_email"])
    schreibe("kontakt", textseite("Kontakt", f"<p>Fragen zu Produkten, Sonderanfertigungen oder Mengenpreisen? Schreiben Sie uns.</p>"
                                               f'<p><a class="btn" href="mailto:{mail}">{mail}</a></p>'
                                               f"<p>{e(CFG['betreiber_zeile'])}</p>"))
    for pfad, titel in (("impressum", "Impressum"), ("datenschutz", "Datenschutzerklärung"), ("agb", "Allgemeine Geschäftsbedingungen")):
        datei = b.RECHT / f"{pfad}.html"
        if not datei.exists():
            if pfad == "agb":
                continue
            raise SystemExit(f"Rechtstext fehlt: {datei}")
        schreibe(pfad, textseite(titel, datei.read_text(encoding="utf-8")))
    (OUT / "404.html").write_text(textseite("Seite nicht gefunden", '<p>Diese Seite gibt es nicht. <a href="/">Zum Berater</a></p>'), encoding="utf-8")
    (OUT / "robots.txt").write_text("User-agent: *\nAllow: /\n", encoding="utf-8")

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
