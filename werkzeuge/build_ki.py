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


# Anwendungskacheln: Bild aus dem Theme, Titel, Frage, die beim Anklicken an den Berater geht
ANWENDUNGEN = [
    (1, "Gastronomie-Arbeitstische", "Ich brauche höhenverstellbare Füße für einen Edelstahl-Arbeitstisch in der Gastronomie."),
    (3, "Produktionsmaschinen", "Ich suche Maschinenfüße für eine Produktionsmaschine. Was brauchen Sie von mir?"),
    (4, "CNC- und Werkzeugmaschinen", "Welche Füße eignen sich für eine schwere CNC-Maschine mit Vibrationen?"),
    (5, "Fördertechnik", "Ich brauche Gelenkfüße für ein Förderband, der Boden ist uneben."),
    (9, "Schaltschränke", "Welche Stellfüße passen unter einen Schaltschrank?"),
    (10, "Werkbänke und Gestelle", "Ich brauche Einschlagfüße für eine Werkbank aus Vierkantrohr."),
    (11, "Regale", "Welche Füße nehme ich für ein Schwerlastregal?"),
    (13, "Klima- und Lüftungsgeräte", "Ich suche Schwingungsdämpfer für ein Klimagerät."),
]

BEISPIELE = [
    "Stellfuß M12 für eine Maschine, ca. 400 kg",
    "Einschlagfuß für 40er Vierkantrohr",
    "Edelstahl für die Lebensmittelindustrie",
    "Ich weiß nicht, was ich brauche",
]

ICON = {
    "senden": '<path d="M4 12 20 4l-6 16-2.5-6.5z" fill="currentColor"/>',
    "fuss": '<path d="M12 3v11M9 6h6" stroke="currentColor" stroke-width="2.2" fill="none" stroke-linecap="round"/><ellipse cx="12" cy="18" rx="7" ry="2.6" fill="currentColor"/>',
    "check": '<path d="m5 12.5 4.5 4.5L19 7.5" stroke="currentColor" stroke-width="2.4" fill="none" stroke-linecap="round" stroke-linejoin="round"/>',
}


def icon(name, klasse=""):
    return f'<svg class="{klasse}" viewBox="0 0 24 24" aria-hidden="true">{ICON[name]}</svg>'


def beraterseite(anzahl):
    api = CFG.get("ki_api", "")
    chips = "".join(f'<button type="button" class="kb-chip" data-frage="{e(x)}">{e(x)}</button>' for x in BEISPIELE)
    kacheln = "".join(
        f'<button type="button" class="kb-anw" data-frage="{e(frage)}">'
        f'<img src="/assets/anwendungen/anwendung-{nr:02d}.jpg" alt=""><span>{e(titel)}</span></button>'
        for nr, titel, frage in ANWENDUNGEN)
    schritte = "".join(
        f'<li><span class="kb-nr">{i}</span><h3>{e(h)}</h3><p>{e(p)}</p></li>' for i, (h, p) in enumerate((
            ("Beschreiben", "Sagen Sie, wofür der Fuß gedacht ist: Gerät, Gewinde oder Rohr, Last, Boden. Was fehlt, fragt der Berater nach."),
            ("Vorschlag mit Preis", "Sie bekommen passende Produkte mit Bild, technischen Daten und Nettopreis."),
            ("Bestellen", "Ausführung und Menge wählen, Lieferadresse eintragen. Wir bestätigen die Bestellung per E-Mail."),
        ), 1))
    haken = "".join(f'<li>{icon("check")}{e(x)}</li>' for x in (
        f"{anzahl} Produkte mit festem Preis", "Beratung auch ohne Fachbegriffe", "Persönlicher Ansprechpartner bei TS Systemtechnik"))
    return b.seite("beinundfuß.de – Ihr Berater für Stellfüße und Einschlagfüße", f"""
<section class="kb-hero">
<div class="wrap kb-hero-inhalt">
<p class="kb-claim">Stellfüße · Einschlagfüße · Maschinenfüße</p>
<h1>Sagen Sie uns, was Ihr Fuß können muss.</h1>
<p class="kb-lead">Unser Berater findet den passenden Fuß für Maschine, Tisch, Regal oder Gerät und nennt Ihnen gleich den Preis.</p>
<ul class="kb-haken">{haken}</ul>
</div>
</section>

<section class="wrap kb-buehne">
<div class="kb-chat">
<div class="kb-chat-kopf">
<span class="kb-avatar">{icon("fuss")}</span>
<div><strong>Fußberater</strong><span class="kb-status">KI-Assistent</span></div>
<button type="button" class="kb-neu" id="ki-neu" title="Neues Gespräch">Neu starten</button>
</div>
<div id="ki" class="kb-verlauf" aria-live="polite"></div>
<div class="kb-chips" id="ki-chips">{chips}</div>
<form id="ki-eingabe" class="kb-eingabe">
<textarea id="ki-text" rows="1" maxlength="1500" placeholder="Was brauchen Sie?" aria-label="Ihre Frage" required></textarea>
<button class="kb-senden" type="submit" aria-label="Senden">{icon("senden")}</button>
</form>
</div>
<p class="kb-hinweis">Sie sprechen mit einer KI. Angaben bitte vor der Bestellung prüfen; verbindlich sind Auftragsbestätigung und Datenblatt.
Ihre Eingaben werden zur Beantwortung an Anthropic übermittelt, siehe <a href="/datenschutz/">Datenschutz</a>.</p>
</section>

<section class="kb-bild"><img src="/assets/hero-fuesse.jpg" alt="Auswahl an Maschinenfüßen, Edelstahl-Stellbeinen und Einschlagfüßen"></section>

<section class="kb-block"><div class="wrap">
<h2>So einfach geht's</h2>
<ol class="kb-schritte">{schritte}</ol>
</div></section>

<section class="kb-block kb-hell"><div class="wrap">
<h2>Wofür brauchen Sie Füße?</h2>
<p class="kb-unter">Tippen Sie auf eine Anwendung, und der Berater legt direkt los.</p>
<div class="kb-anwendungen">{kacheln}</div>
</div></section>

<section class="kb-block"><div class="wrap kb-kontakt">
<div><h2>Lieber mit einem Menschen sprechen?</h2>
<p>Sonderanfertigungen, große Mengen oder Produkte ohne Online-Preis: Schreiben Sie uns, wir melden uns persönlich.</p></div>
<a class="btn" href="mailto:{e(CFG['anfrage_email'])}">{e(CFG['anfrage_email'])}</a>
</div></section>
<dialog id="ki-bestellen" class="ki-dialog"></dialog>
<script>window.bfKi = {{ api: "{e(api)}", basis: "", email: "{e(CFG['anfrage_email'])}" }};</script>
<script src="/assets/ki.js" defer></script>""", extra_kopf='<link rel="stylesheet" href="/assets/ki.css">')


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
    theme_css = re.sub(r"/\*.*?\*/", "", (b.THEME / "style.css").read_text(encoding="utf-8"), count=1, flags=re.S)
    (OUT / "assets/site.css").write_text(b.CSS + theme_css, encoding="utf-8")
    shutil.copy(b.THEME / "assets/hero-fuesse.jpg", OUT / "assets/hero-fuesse.jpg")
    shutil.copytree(b.THEME / "assets/anwendungen", OUT / "assets/anwendungen")
    for datei in ("ki.js", "ki.css"):
        shutil.copy(ROOT / "ki/seite" / datei, OUT / "assets" / datei)
    (OUT / "assets/favicon.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="6" fill="#1b2836"/>'
        '<path d="M16 6v14M12 10h8" stroke="#fff" stroke-width="2.5" fill="none"/><ellipse cx="16" cy="23" rx="8" ry="3" fill="#4fa82e"/></svg>',
        encoding="utf-8")
    for p in produkte:
        if b.preise(p) and not p["bild"]:
            (OUT / "assets/skizzen" / f"{p['slug']}.svg").write_text(zeichnung(p, klein=True), encoding="utf-8")

    def schreibe(pfad, text):
        ziel = OUT / pfad / "index.html" if pfad else OUT / "index.html"
        ziel.parent.mkdir(parents=True, exist_ok=True)
        ziel.write_text(text, encoding="utf-8")

    schreibe("", beraterseite(len(liste)))
    mail = e(CFG["anfrage_email"])
    schreibe("kontakt", b.textseite("Kontakt", f"<p>Fragen zu Produkten, Sonderanfertigungen oder Mengenpreisen? Schreiben Sie uns.</p>"
                                               f'<p><a class="btn" href="mailto:{mail}">{mail}</a></p>'
                                               f"<p>{e(CFG['betreiber_zeile'])}</p>"))
    for pfad, titel in (("impressum", "Impressum"), ("datenschutz", "Datenschutzerklärung"), ("agb", "Allgemeine Geschäftsbedingungen")):
        datei = b.RECHT / f"{pfad}.html"
        if not datei.exists():
            if pfad == "agb":
                continue
            raise SystemExit(f"Rechtstext fehlt: {datei}")
        schreibe(pfad, b.textseite(titel, datei.read_text(encoding="utf-8")))
    (OUT / "404.html").write_text(b.textseite("Seite nicht gefunden", '<p>Diese Seite gibt es nicht. <a href="/">Zum Berater</a></p>'), encoding="utf-8")
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
