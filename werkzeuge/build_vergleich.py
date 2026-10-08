#!/usr/bin/env python3
"""Erzeugt aus der Herstellerrecherche (katalog/recherche/teil-*.csv) eine zweite WooCommerce-Importdatei
mit den Vergleichsprodukten anderer Hersteller.

Alle Artikel sind „Preis auf Anfrage“ und ohne Bilder (Herstellerfotos nur mit Freigabe). Texte und
Merkmale werden aus den recherchierten Daten erzeugt, nicht von Herstellerseiten übernommen.
Standard ist veröffentlicht (Entscheidung Lenn, 08.10.2026); mit --entwurf kommen sie als Entwurf an.

Aufruf: python3 werkzeuge/build_vergleich.py <recherche-ordner> [--entwurf]
        ->  import/vergleichsprodukte-woocommerce.csv
"""
import csv
import hashlib
import html
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_auswahlliste import hersteller  # noqa: E402
from build_import import FINDER_MERKMALE, wert  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "import" / "vergleichsprodukte-woocommerce.csv"

# Produktwelt der Recherche → Kategorie(n), Bauform, Anwendung, Grundfunktion.
WELTEN = {
    "Einschlagfüße Vierkantrohr": ("Einschlagfüße > Vierkantrohr", "Einschlagfuß",
                                   ["Arbeitstisch / Möbel", "Regal / Gestell", "Gastronomiegerät"], ["Höhenverstellung"]),
    "Einschlagfüße Rundrohr": ("Einschlagfüße > Rundrohr", "Einschlagfuß",
                               ["Arbeitstisch / Möbel", "Regal / Gestell", "Gastronomiegerät"], ["Höhenverstellung"]),
    "Edelstahl-Stellbeine": ("Edelstahl-Stellbeine", "Stellbein",
                             ["Gastronomiegerät", "Arbeitstisch / Möbel"], ["Höhenverstellung"]),
    "Gerätebeine/Möbelfüße": ("Edelstahl-Stellbeine > Gerätebeine", "Stellbein",
                              ["Gastronomiegerät", "Arbeitstisch / Möbel"], ["Höhenverstellung"]),
    "Maschinenfüße": ("Maschinenfüße", "Stellfuß", ["Maschine / Anlage", "Fördertechnik"], ["Höhenverstellung"]),
    "Nivellierelemente": ("Maschinenfüße", "Nivellierelement", ["Maschine / Anlage"], ["Höhenverstellung"]),
    "Gelenkfüße": ("Gelenkfüße", "Gelenkfuß",
                   ["Maschine / Anlage", "Fördertechnik", "Schaltschrank / Gehäuse"], ["Höhenverstellung"]),
    "Füße mit Bodenbefestigung": ("Füße mit Bodenbefestigung", "Stellfuß", ["Maschine / Anlage"],
                                  ["Höhenverstellung", "Bodenbefestigung"]),
    "Hygienefüße": ("Hygienefüße", "Stellfuß", ["Maschine / Anlage"], ["Höhenverstellung", "Hygiene-Anforderungen"]),
    "Schwerlastfüße": ("Schwerlastfüße", "Stellfuß", ["Maschine / Anlage"], ["Höhenverstellung", "Hohe Traglast"]),
    "Schwingungsdämpfer": ("Schwingungsdämpfer", "Schwingungsdämpfer",
                           ["Maschine / Anlage", "Klima- / Lüftungsgerät"], ["Schwingungsdämpfung"]),
    "Nivellierrollen/Sonderlösungen": ("Rollen & Sonderlösungen", "Spezialausführung",
                                       ["Maschine / Anlage", "Gastronomiegerät"], ["Mobil (Rolle + Fuß)"]),
}

MASS_FELDER = ["rohrmass_oder_durchmesser_mm", "teller_durchmesser_mm", "durchmesser_mm"]
DATEN = [  # (Beschriftung in der Tabelle, Feld)
    ("Material", "material"), ("Gewinde / Anschluss", "anschluss_gewinde"), ("Traglast (N)", "traglast_n"),
    ("Verstellbereich (mm)", "verstellbereich_mm"), ("Gelenkwinkel (°)", "gelenkwinkel_grad"),
    ("Dämpfung / Härte", "daempfung_haerte"), ("Bodenbefestigung", "bodenbefestigung"),
    ("Zertifizierung", "zertifizierung"), ("Varianten laut Hersteller", "anzahl_varianten"),
]


def materialien(text, welt):
    t = text.lower()
    out = []
    if "edelstahl" in t or "aisi" in t or "1.43" in t or "1.44" in t:
        out.append("Edelstahl")
    if re.search(r"(?<!edel)stahl", t):
        out.append("Stahl")
    if "zinkdruckguss" in t or "zamak" in t:
        out.append("Zinkdruckguss")
    if "alu" in t:
        out.append("Aluminium")
    if re.search(r"\b(pa|pa6|pp|pom|pvc|polyamid|kunststoff|technopolymer|nylon)\b", t):
        out.append("Kunststoff")
    if welt == "Schwingungsdämpfer" and re.search(r"gummi|nbr|\bnr\b|elastomer|kautschuk|polyurethan|\bpu\b", t):
        out.append("Gummi / Elastomer")
    return out


REIHE = [3, 4, 5, 6, 8, 10, 12, 14, 16, 20, 24, 30, 36, 42, 48]


def gewinde(text):
    """M-Gewinde einzeln oder als Bereich („M8-M16“, „M8 bis M16“ → Regelreihe dazwischen) und Zoll-Gewinde."""
    werte = {int(n) for n in re.findall(r"\bM(\d{1,2})(?!\d)", text)}
    for a, b in re.findall(r"\bM(\d{1,2})\s*(?:-|–|bis)\s*M(\d{1,2})(?!\d)", text):
        werte |= {n for n in REIHE if int(a) <= n <= int(b)}
    m = [f"M{n}" for n in sorted(werte)]
    zoll = re.findall(r'\b(\d/\d+)"?\s*-?\s*\d*\s*UNC', text)
    return m + sorted({f'{z}" UNC' for z in zoll})


def zahl(text):
    m = re.search(r"\d+(?:[.,]\d+)?", text or "")
    return float(m.group().replace(",", ".")) if m else None


def rohrmass(r, welt):
    roh = r.get("rohrmass_oder_durchmesser_mm", "")
    if not roh:
        return []
    if welt == "Einschlagfüße Vierkantrohr":
        out = []
        for a, b in re.findall(r"(\d+(?:,\d+)?)\s*[x×]\s*(\d+(?:,\d+)?)", roh):
            out.append(f"Vierkant {a} mm" if a == b else f"Rechteck {a}x{b} mm")
        return sorted(set(out))
    if welt == "Einschlagfüße Rundrohr":
        d = zahl(roh)
        if d is None:
            return []
        if abs(d - 41.3) < 0.2:
            return ["Rund 1 5/8 Zoll (41.3 mm)"]
        return [f"Rund {d:g} mm".replace(".", ",") if d % 1 else f"Rund {d:g} mm"]
    return []


def bodenbefestigung(r, welt):
    b = (r.get("bodenbefestigung") or "").strip().lower()
    if welt == "Füße mit Bodenbefestigung" or b.startswith("ja") or "bohrung" in b or "bolt" in b:
        return "ja"
    if b.startswith("nein"):
        return "nein"
    return ""


def sku(r):
    schluessel = f"{r['hersteller']}|{r['serie_artikel']}|{r['produktwelt']}"
    return "BF-V-" + hashlib.sha1(schluessel.encode()).hexdigest()[:8].upper()


def produkt(r):
    welt = r["produktwelt"]
    kategorie, bauform, anwendung, funktion = WELTEN[welt]
    marke = hersteller(r["hersteller"])
    bf = bodenbefestigung(r, welt)
    if bf == "ja":
        funktion = list(dict.fromkeys(funktion + ["Bodenbefestigung"]))
        if "Füße mit Bodenbefestigung" not in kategorie:
            kategorie += ", Füße mit Bodenbefestigung"
    last = zahl(r.get("traglast_n"))
    if last and last >= 20000:
        funktion = list(dict.fromkeys(funktion + ["Hohe Traglast"]))
    if bauform == "Einschlagfuß" and re.search(r"stopfen|buchse|einsatz", r["serie_artikel"] + r["kurzbeschreibung"], re.I):
        bauform = "Gewindeeinsatz"

    merkmale = {
        "Anwendung": anwendung, "Funktion": funktion, "Bauform": [bauform],
        "Material": materialien(r["material"], welt), "Rohrmaß": rohrmass(r, welt),
        "Gewinde": gewinde(r.get("anschluss_gewinde", "")), "Bodenbefestigung": [bf] if bf else [],
        "Traglast": f"{r['traglast_n']} N" if r.get("traglast_n") else "",
        "Durchmesser": next((f"{r[k]} mm" for k in MASS_FELDER if r.get(k)), ""),
    }

    zeilen = [("Hersteller", marke), ("Serie / Artikel", r["serie_artikel"])]
    mass = next((r[k] for k in MASS_FELDER if r.get(k)), "")
    if mass:
        zeilen.append(("Maß / Ø (mm)", mass))
    zeilen += [(label, r[k]) for label, k in DATEN if r.get(k)]
    tabelle = "".join(f"<tr><th>{html.escape(a)}</th><td>{html.escape(b)}</td></tr>" for a, b in zeilen)
    kurz = r["kurzbeschreibung"].rstrip(". ")
    text = (f"<p>{html.escape(kurz)}.</p><table><tbody>{tabelle}</tbody></table>"
            "<p>Technische Angaben nach Herstellerunterlagen, ohne Gewähr. Passende Ausführung, Preis und "
            "Lieferzeit nennen wir Ihnen auf Anfrage.</p>")
    return {
        "sku": sku(r), "name": f"{marke} {r['serie_artikel']}", "kategorie": kategorie, "marke": marke,
        "kurz": kurz + ". Preis und Lieferzeit auf Anfrage.", "text": text,
        "merkmale": merkmale,
    }


def main(ordner: Path, sichtbar: bool):
    daten = []
    for f in sorted(ordner.glob("teil-*.csv")):
        daten += list(csv.DictReader(f.open(encoding="utf-8")))
    produkte = [produkt(r) for r in daten]
    skus = [p["sku"] for p in produkte]
    assert len(skus) == len(set(skus)), "doppelte Artikelnummern"

    namen = ["Anwendung", "Funktion", "Bauform", "Material", "Rohrmaß", "Gewinde", "Bodenbefestigung", "Traglast", "Durchmesser"]
    head = ["Type", "SKU", "Name", "Published", "Is featured?", "Visibility in catalog", "Short description",
            "Description", "Tax status", "In stock?", "Regular price", "Categories", "Images", "Brands"]
    for i in range(1, len(namen) + 1):
        head += [f"Attribute {i} name", f"Attribute {i} value(s)", f"Attribute {i} visible", f"Attribute {i} global"]
    # Bezugsquellen und Einkaufsdaten gehören nicht in diese Datei (Repo ist öffentlich), sondern nach
    # /mnt/project-files/katalog/intern/.
    head += ["Meta: _bf_preis_auf_anfrage", "Meta: _bf_herkunft"]

    rows = []
    for p in sorted(produkte, key=lambda p: (p["kategorie"], p["name"].lower())):
        row = dict.fromkeys(head, "")
        row.update({
            "Type": "simple", "SKU": p["sku"], "Name": p["name"], "Published": 1 if sichtbar else 0,
            "Is featured?": 0, "Visibility in catalog": "visible", "Short description": p["kurz"],
            "Description": p["text"], "Tax status": "taxable", "In stock?": 1, "Categories": p["kategorie"],
            "Brands": p["marke"], "Meta: _bf_preis_auf_anfrage": 1, "Meta: _bf_herkunft": "vergleich",
        })
        n = 0
        for name in namen:
            v = p["merkmale"][name]
            if not v:
                continue
            n += 1
            row[f"Attribute {n} name"] = name
            row[f"Attribute {n} value(s)"] = ", ".join(wert(x) for x in v) if isinstance(v, list) else wert(v)
            row[f"Attribute {n} visible"] = 1
            row[f"Attribute {n} global"] = 1 if name in FINDER_MERKMALE else 0
        rows.append(row)

    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=head)
        w.writeheader()
        w.writerows(rows)
    print(f"{OUT.relative_to(ROOT)}: {len(rows)} Produkte ({'veröffentlicht' if sichtbar else 'Entwurf'})")


if __name__ == "__main__":
    main(Path(sys.argv[1]), "--entwurf" not in sys.argv)
