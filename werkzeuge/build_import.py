#!/usr/bin/env python3
"""Erzeugt die WooCommerce-Importdatei (CSV, Format des eingebauten Produkt-Importers)
aus daten/ts-produkte.json.

Aufruf: python3 werkzeuge/build_import.py  ->  import/produkte-woocommerce.csv
"""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = json.loads((ROOT / "daten" / "ts-produkte.json").read_text(encoding="utf-8"))
OUT = ROOT / "import" / "produkte-woocommerce.csv"

# Globale Merkmale = Filter im Produktfinder (WooCommerce "pa_..."-Attribute).
FINDER_MERKMALE = ["Anwendung", "Funktion", "Bauform", "Material", "Rohrmaß", "Gewinde",
                   "Fußform", "Anschluss", "Bodenbefestigung"]
# Reine Datenblatt-Werte, sichtbar auf der Produktseite, aber nicht als Filter.
DATEN_MERKMALE = ["Traglast", "Verstellbereich", "Durchmesser", "Tellerdurchmesser", "Spindellänge"]
ALLE = FINDER_MERKMALE + DATEN_MERKMALE
VAR_ATTR = "Ausführung"

ROLLEN = [
    (17328, "Geräterolle 50 mm", "Rollen_50mm_Foto.png"),
    (17335, "Geräterolle 75 mm", "Rollen_75mm_Foto-1.png"),
    (17342, "Geräterolle 100 mm", "Rollen_100mm_Foto-1.png"),
    (17354, "Geräterolle 125 mm", "Rollen_125mm_Foto-1.png"),
    (17361, "Edelstahl-Geräterolle 100 mm", "Rollen_100mm_Edelstahl_Foto.png"),
    (17358, "Edelstahl-Geräterolle 125 mm", "Rollen_125mm_Edelstahl_Foto.png"),
]


def gelenkfuesse():
    g = DATA["gelenkfuesse"]
    teller = sorted({t for v in g["gewinde"].values() for t in v["teller"]}, key=int)
    tabelle = "\n".join(
        f"<tr><td>{gw}</td><td>{' / '.join(v['teller'])} mm</td><td>50 / 100 mm</td>"
        f"<td>{'8.000 N (Teller 40/50), 12.000 N (Teller 60)' if '40' in v['teller'] and '60' in v['teller'] else ('8.000 N' if '40' in v['teller'] else '12.000 N')}</td></tr>"
        for gw, v in g["gewinde"].items())
    tabelle = ("<table><thead><tr><th>Gewinde</th><th>Teller-Ø</th><th>Spindellänge</th><th>Traglast</th></tr></thead>"
               f"<tbody>{tabelle}</tbody></table>")
    out = []
    for key, mit in (("ohne", False), ("mit", True)):
        out.append({
            "sku": f"BF-GELENK-{key.upper()}",
            "name": f"Gelenkfuß M8–M24 {'mit' if mit else 'ohne'} Bodenbefestigung",
            "kategorie": "Gelenkfüße" + (", Füße mit Bodenbefestigung" if mit else ""),
            "kurz": ("Gelenkfuß mit Kunststoffteller und rutschfester NBR-Sohle, Gewinde M8 bis M24, bis 12.000 N"
                     + (", Teller mit Löchern zum Verschrauben am Boden." if mit else ".")),
            "text": ("<p>Der Teller neigt sich gegenüber der Spindel und gleicht so unebene oder leicht schräge Böden aus. "
                     "Teller aus glasfaserverstärktem PA6, Sohle aus NBR gegen Rutschen und Körperschall. "
                     + ("Über die Befestigungslöcher wird der Fuß am Boden verschraubt, damit die Maschine nicht wandert. " if mit else "")
                     + "Bitte Gewinde, Tellerdurchmesser und Spindellänge in der Anfrage angeben.</p>" + tabelle),
            "bild": g["bild_mit"] if mit else g["bild_ohne"],
            "merkmale": {"Bauform": ["Gelenkfuß"], "Anwendung": ["Maschine / Anlage", "Fördertechnik", "Schaltschrank / Gehäuse"],
                         "Funktion": ["Höhenverstellung"] + (["Bodenbefestigung"] if mit else []),
                         "Material": ["Kunststoff"], "Gewinde": list(g["gewinde"].keys()),
                         "Bodenbefestigung": ["ja" if mit else "nein"], "Traglast": "8000–12000 N",
                         "Tellerdurchmesser": " / ".join(teller) + " mm", "Spindellänge": "50 / 100 mm"},
            "varianten": [],
        })
    return out


def rollen():
    return [{
        "sku": f"BF-{tid}", "name": name, "kategorie": "Rollen & Sonderlösungen",
        "kurz": "Lenkrolle für Apparate und Geräte. Ausführung, Bremse und Traglast auf Anfrage.",
        "text": "<p>Für Geräte, die bewegt und anschließend sicher abgestellt werden. Technische Daten senden wir Ihnen auf Anfrage.</p>",
        "bild": f"https://ts-systemtechnik.de/wp-content/uploads/2019/05/{bild}",
        "merkmale": {"Bauform": ["Spezialausführung"], "Anwendung": ["Gastronomiegerät", "Maschine / Anlage"],
                     "Funktion": ["Mobil (Rolle + Fuß)"]},
        "varianten": [],
    } for tid, name, bild in ROLLEN]


def wert(text):
    """WooCommerce trennt Mehrfachwerte mit Komma, deshalb keine Kommas in Einzelwerten."""
    return text.replace(", ", " · ")


def merkmal_wert(v):
    return ", ".join(v) if isinstance(v, list) else str(v)


def main():
    produkte = DATA["produkte"] + gelenkfuesse() + rollen()
    max_attr = len(ALLE) + 1
    head = ["Type", "SKU", "Name", "Published", "Is featured?", "Visibility in catalog", "Short description",
            "Description", "Tax status", "In stock?", "Regular price", "Categories", "Images", "Parent", "Brands"]
    for i in range(1, max_attr + 1):
        head += [f"Attribute {i} name", f"Attribute {i} value(s)", f"Attribute {i} visible", f"Attribute {i} global"]
    head += ["Meta: _bf_preis_auf_anfrage", "Meta: _bf_ts_id"]

    rows = []
    for p in produkte:
        var = p.get("varianten", [])
        row = dict.fromkeys(head, "")
        text = p["text"] if p["text"].startswith("<") else f"<p>{p['text']}</p>"
        row.update({
            "Type": "variable" if var else "simple", "SKU": p["sku"], "Name": p["name"], "Published": 1,
            "Is featured?": 0, "Visibility in catalog": "visible", "Short description": p["kurz"],
            "Description": text, "Tax status": "taxable", "In stock?": 1, "Categories": p["kategorie"],
            "Images": p.get("bild", ""), "Brands": p.get("hersteller", ""),
            "Meta: _bf_preis_auf_anfrage": "" if var else "1", "Meta: _bf_ts_id": p.get("ts_id", ""),
        })
        n = 0
        for name in ALLE:
            if name in p["merkmale"]:
                n += 1
                row[f"Attribute {n} name"] = name
                row[f"Attribute {n} value(s)"] = merkmal_wert(p["merkmale"][name])
                row[f"Attribute {n} visible"] = 1
                row[f"Attribute {n} global"] = 1 if name in FINDER_MERKMALE else 0
        if var:
            n += 1
            row[f"Attribute {n} name"] = VAR_ATTR
            row[f"Attribute {n} value(s)"] = ", ".join(wert(v["ausfuehrung"]) for v in var)
            row[f"Attribute {n} visible"] = 1
            row[f"Attribute {n} global"] = 0
            var_slot = n
        rows.append(row)
        for v in var:
            vr = dict.fromkeys(head, "")
            vr.update({
                "Type": "variation", "SKU": v["sku"], "Name": f"{p['name']} – {v['ausfuehrung']}", "Published": 1,
                "Tax status": "taxable", "In stock?": 1, "Regular price": v["preis"], "Parent": p["sku"],
                f"Attribute {var_slot} name": VAR_ATTR, f"Attribute {var_slot} value(s)": wert(v["ausfuehrung"]),
                f"Attribute {var_slot} global": 0,
            })
            rows.append(vr)

    OUT.parent.mkdir(exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=head)
        w.writeheader()
        w.writerows(rows)
    eltern = sum(1 for r in rows if r["Type"] != "variation")
    varianten = len(rows) - eltern
    print(f"{OUT.relative_to(ROOT)}: {eltern} Produkte, {varianten} Varianten")


if __name__ == "__main__":
    main()
