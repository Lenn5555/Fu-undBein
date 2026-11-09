"""Tests für den Preiswächter mit erfundenen Händlerseiten. Aufruf: python3 -m unittest werkzeuge/test_preiswaechter.py"""
import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import preiswaechter as pw  # noqa: E402

TABELLE = """<html><body><nav>Warenkorb 0,00 €</nav><h1>Gelenkfüße Stahl</h1><table>
<tr><td>X0375.005010X25</td><td>Ø50</td><td>{a} €</td></tr>
<tr><td>X0375.005010X50</td><td>Ø50</td><td>9,49 €</td></tr></table></body></html>"""
EINZEL = """<html><head><script type="application/ld+json">{{"@type":"Product","offers":{{"price":"{p}"}}}}</script></head>
<body><h1>Stellfuß Type 45815037</h1><p>{text}</p><table><tr><td>From 1</td><td>€{p}*</td></tr><tr><td>From 50</td><td>€24.26*</td></tr></table></body></html>"""
BRUTTO = "<html><body><h1>Isolator SD1 Art. 77001234</h1><p>36,45 € inkl. MwSt.</p></body></html>"


def eintrag(url, ek, bezug):
    return {"bestell_url": url, "ek_netto": ek, "preis_bezug": bezug, "artikel": "", "bezugsquelle": "Händler X", "hersteller": "H"}


class Lesen(unittest.TestCase):
    def test_zahlen(self):
        self.assertEqual(pw.zahl("1.234,56"), 1234.56)
        self.assertEqual(pw.zahl("1,234.56"), 1234.56)
        self.assertEqual(pw.zahl("29.01"), 29.01)
        self.assertEqual(pw.zahl("3,71"), 3.71)

    def test_preise_im_text(self):
        self.assertEqual(pw.preise_im_text("ab € 3,71* netto, 4,41 € brutto, M16 100 12,00 EUR"), [3.71, 4.41, 12.0])

    def test_auszug(self):
        text = "Kopf " + "a" * 3000 + " Typ 45815037 Preis 29,01 € " + "b" * 5000
        a = pw.auszug(text, ["45815037"])
        self.assertIn("Typ 45815037 Preis 29,01 €", a)
        self.assertEqual(pw.auszug("kurz", ["123456"]), "kurz")

    def test_variante_in_tabelle(self):
        e = eintrag("https://h.test/p", 8.83, "ab, X0375.005010X25, Ø50 L25, 1 Stk")
        r = pw.pruefe(e, 200, e["bestell_url"], TABELLE.format(a="8,83"), {})
        self.assertEqual((r["art"], r["ek"], r["brutto"]), ("eingemessen", 8.83, False))
        self.assertTrue(r["weg"].startswith("nach:"))
        # nächster Lauf: neuer Preis an derselben Stelle
        basis = {"weg": r["weg"], "brutto": False, "token": r["token"], "auslauf_text": False}
        r2 = pw.pruefe(e, 200, e["bestell_url"], TABELLE.format(a="9,10"), basis)
        self.assertEqual((r2["art"], r2["ek"]), ("ok", 9.10))

    def test_brutto(self):
        e = eintrag("https://h.test/b", 30.63, "SD1 Art. 77001234, 1 Stk")
        r = pw.pruefe(e, 200, e["bestell_url"], BRUTTO, {})
        self.assertEqual((r["art"], r["brutto"], r["ek"]), ("eingemessen", True, 30.63))

    def test_falscher_preis_wird_nicht_eingemessen(self):
        e = eintrag("https://h.test/p", 15.00, "X0375.005010X25")
        self.assertEqual(pw.pruefe(e, 200, e["bestell_url"], TABELLE.format(a="8,83"), {})["art"], "nicht_pruefbar")

    def test_artikelnummer_verschwunden(self):
        e = eintrag("https://h.test/e", 29.01, "Typ 45815037")
        r = pw.pruefe(e, 200, e["bestell_url"], EINZEL.format(p="29.01", text=""), {})
        basis = {"weg": r["weg"], "brutto": False, "token": r["token"], "auslauf_text": False}
        seite = EINZEL.format(p="29.01", text="").replace("Type 45815037", "Stellfuß")
        self.assertEqual(pw.pruefe(e, 200, e["bestell_url"], seite, basis)["art"], "auslauf")

    def test_auslauftext_nur_wenn_neu(self):
        e = eintrag("https://h.test/e", 29.01, "Typ 45815037")
        alt = EINZEL.format(p="29.01", text="Filter: Auslaufartikel")
        r = pw.pruefe(e, 200, e["bestell_url"], alt, {})
        self.assertEqual(r["art"], "eingemessen")  # stand schon beim ersten Mal da: kein Alarm
        basis = {"weg": r["weg"], "brutto": False, "token": r["token"], "auslauf_text": True}
        self.assertEqual(pw.pruefe(e, 200, e["bestell_url"], alt, basis)["art"], "ok")
        basis["auslauf_text"] = False
        neu = EINZEL.format(p="29.01", text="Dieser Artikel ist nicht mehr lieferbar.")
        self.assertEqual(pw.pruefe(e, 200, e["bestell_url"], neu, basis)["art"], "auslauf")

    def test_seite_weg_und_fehler(self):
        e = eintrag("https://h.test/x/y", 1.0, "")
        self.assertEqual(pw.pruefe(e, 404, e["bestell_url"], "", {})["art"], "weg")
        self.assertEqual(pw.pruefe(e, 403, e["bestell_url"], "", {})["art"], "fehler")
        self.assertEqual(pw.pruefe(e, 0, e["bestell_url"], "", {})["art"], "fehler")
        self.assertEqual(pw.pruefe(e, 200, "https://h.test/", "<p>Start</p>", {})["art"], "weg")

    def test_sperrseite_ist_kein_auslauf(self):
        e = eintrag("https://h.test/e", 29.01, "Typ 45815037")
        basis = {"weg": "nach:0", "brutto": False, "token": 0, "auslauf_text": False}
        for seite in ("<h1>Just a moment...</h1><p>Checking your browser</p>", "<p>Bitte warten</p>"):
            self.assertEqual(pw.pruefe(e, 200, e["bestell_url"], seite, basis)["art"], "fehler")


class Lauf(unittest.TestCase):
    """Ganzer Lauf mit erfundenen Seiten in einem Temp-Ordner (Grundlage, ohne eigene Tests)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "daten").mkdir()
        self.patches = [mock.patch.object(pw, n, self.tmp / f"daten/{d}") for n, d in
                        (("PREISE", "preise-vergleich.csv"), ("AUSGEBLENDET", "ausgeblendet.csv"), ("STAND", "preiswaechter.json"),
                         ("FESTE", "feste-preise.json"))]
        self.ki = None  # Antwort des zweiten Lesers (Claude); None = nicht verfügbar
        self.ki_aufrufe = 0
        # Rechenbeispiele unten mit 10 % Aufschlag; der echte Aufschlag steht in preiswaechter.AUFSCHLAG
        self.patches += [mock.patch.object(pw, "AUFSCHLAG", 1.10),
                         mock.patch.object(pw, "ROOT", self.tmp), mock.patch.object(pw, "PAUSE", 0),
                         mock.patch.object(pw.hilfe, "browser_lesen", lambda url: None),
                         mock.patch.object(pw.hilfe, "ki_lesen", self.ki_lesen)]
        for p in self.patches:
            p.start()
        self.bezug = {f"BF-V-{i}": eintrag(f"https://h.test/p{i}", 10.0, f"Typ 4581{i:04d}") for i in range(10)}
        (self.tmp / "bq.json").write_text(json.dumps(self.bezug))
        with (self.tmp / "daten/preise-vergleich.csv").open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["sku", "preis_netto"])
            w.writerows([s, "11.00"] for s in self.bezug)
        self.seiten = {f"https://h.test/p{i}": (200, f"<h1>Typ 4581{i:04d}</h1><p>10,00 €</p>") for i in range(10)}

    def ki_lesen(self, eintrag, auszug):
        self.ki_aufrufe += 1
        return self.ki(eintrag, auszug) if callable(self.ki) else self.ki

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def lauf(self, *args):
        with mock.patch.object(pw, "lesen", lambda u: (self.seiten[u][0], u, self.seiten[u][1])):
            pw.main([str(self.tmp / "bq.json"), *args])
        with (self.tmp / "daten/preise-vergleich.csv").open() as f:
            return {r["sku"]: r["preis_netto"] for r in csv.DictReader(f)}


class Ablauf(Lauf):
    def test_erster_lauf_aendert_nichts_dann_preis_und_ausblenden(self):
        self.seiten["https://h.test/p1"] = (200, "<h1>Typ 45810001</h1><p>10,20 €</p>")
        vk = self.lauf()
        self.assertEqual(vk["BF-V-1"], "11.00")  # erster Lauf: nur melden
        self.assertIn("ERSTER LAUF", (self.tmp / "bericht.txt").read_text())
        self.seiten["https://h.test/p1"] = (200, "<h1>Typ 45810001</h1><p>10,50 €</p>")
        vk = self.lauf()
        self.assertEqual(vk["BF-V-1"], "11.00")  # ohne zweiten Leser: erst beim zweiten Mal übernommen
        vk = self.lauf()
        self.assertEqual(vk["BF-V-1"], "11.55")  # 10,50 + 10 %
        self.seiten["https://h.test/p2"] = (404, "")
        vk = self.lauf()
        self.assertIn("BF-V-2", vk)  # erst Verdacht
        vk = self.lauf()
        self.assertNotIn("BF-V-2", vk)  # zweiter Tag: ausgeblendet
        aus = pw.lade_csv(self.tmp / "daten/ausgeblendet.csv")
        self.assertEqual(aus[0]["sku"], "BF-V-2")
        self.assertNotIn("Händler", json.dumps(json.loads((self.tmp / "daten/preiswaechter.json").read_text())))
        self.seiten["https://h.test/p2"] = (200, "<h1>Typ 45810002</h1><p>10,00 €</p>")
        vk = self.lauf()
        self.assertNotIn("BF-V-2", vk)  # ohne zweiten Leser erst beim zweiten Mal
        vk = self.lauf()
        self.assertEqual(vk["BF-V-2"], "11.00")  # wieder da

    def test_bremse_bei_vielen_ausfaellen(self):
        self.lauf()
        for i in range(8):
            self.seiten[f"https://h.test/p{i}"] = (403, "")
        self.seiten["https://h.test/p9"] = (200, "<h1>Typ 45810009</h1><p>12,00 €</p>")
        vk = self.lauf()
        self.assertEqual(vk["BF-V-9"], "11.00")
        self.assertIn("SICHERHEITSBREMSE", (self.tmp / "bericht.txt").read_text())

    def test_bremse_bei_massenausblenden(self):
        self.lauf()
        for i in range(7):
            self.seiten[f"https://h.test/p{i}"] = (404, "")
        self.lauf()
        vk = self.lauf()
        self.assertEqual(len(vk), 10)

    def test_grosser_sprung_nur_gemeldet(self):
        self.lauf()
        self.seiten["https://h.test/p3"] = (200, "<h1>Typ 45810003</h1><p>20,00 €</p>")
        self.ki = {"gefunden": True, "preis": 20.0, "brutto": False, "nicht_mehr_lieferbar": False}
        vk = self.lauf()
        self.assertEqual(vk["BF-V-3"], "11.00")
        self.assertIn("GROSSER PREISSPRUNG", (self.tmp / "bericht.txt").read_text())

    def test_zweiter_leser_bestaetigt_sofort(self):
        self.lauf()
        self.seiten["https://h.test/p4"] = (200, "<h1>Typ 45810004</h1><p>10,80 €</p>")
        self.ki = {"gefunden": True, "preis": 12.85, "brutto": True, "nicht_mehr_lieferbar": False}  # 12,85 / 1,19 = 10,80
        vk = self.lauf()
        self.assertEqual(vk["BF-V-4"], "11.88")
        self.assertEqual(self.ki_aufrufe, 1)  # nur bei der Änderung gefragt

    def test_zweiter_leser_widerspricht(self):
        self.lauf()
        self.seiten["https://h.test/p5"] = (200, "<h1>Typ 45810005</h1><p>10,80 €</p>")
        self.ki = {"gefunden": True, "preis": 10.00, "brutto": False, "nicht_mehr_lieferbar": False}
        for _ in range(3):
            vk = self.lauf()
        self.assertEqual(vk["BF-V-5"], "11.00")
        self.assertIn("zweite Lesung ergab", (self.tmp / "bericht.txt").read_text())

    def test_nur_ki_lesbar(self):
        """Preis ohne Artikelnummer in der Nähe: Claude misst ein, danach nur bei geänderter Seite fragen."""
        self.seiten["https://h.test/p6"] = (200, "<h1>Typ 45810006</h1>" + "x" * 900 + "<p>Preis 10,00 €</p>")
        self.ki = {"gefunden": True, "preis": 10.0, "brutto": False, "nicht_mehr_lieferbar": False}
        self.lauf()
        stand = json.loads((self.tmp / "daten/preiswaechter.json").read_text())["artikel"]["BF-V-6"]
        self.assertEqual(stand["weg"], "ki")
        n = self.ki_aufrufe
        self.lauf()
        self.assertEqual(self.ki_aufrufe, n)  # Seite unverändert: keine Abfrage
        self.seiten["https://h.test/p6"] = (200, "<h1>Typ 45810006</h1>" + "x" * 900 + "<p>Preis 11,00 €</p>")
        self.ki = {"gefunden": True, "preis": 11.0, "brutto": False, "nicht_mehr_lieferbar": False}
        vk = self.lauf()
        self.assertEqual(vk["BF-V-6"], "11.00")  # nur Claude: erst nach zweiter gleicher Lesung
        self.seiten["https://h.test/p6"] = (200, "<h1>Typ 45810006</h1>" + "x" * 901 + "<p>Preis 11,00 €</p>")
        vk = self.lauf()
        self.assertEqual(vk["BF-V-6"], "12.10")

    def test_nachpruefung_nur_offene(self):
        self.lauf()
        self.seiten["https://h.test/p7"] = (200, "<h1>Typ 45810007</h1><p>10,40 €</p>")
        self.lauf()
        abrufe = []
        alt = self.seiten
        self.seiten = type("Zaehler", (dict,), {"__getitem__": lambda d, u: abrufe.append(u) or alt[u]})(alt)
        vk = self.lauf("--nur-offene")
        self.assertEqual(set(abrufe), {"https://h.test/p7"})
        self.assertEqual(vk["BF-V-7"], "11.44")

    def test_keine_mail_wenn_alles_ruhig(self):
        self.lauf()
        with mock.patch.dict("os.environ", {"GITHUB_OUTPUT": str(self.tmp / "out.txt")}):
            self.lauf()
        self.assertIn("wichtig=nein", (self.tmp / "out.txt").read_text())


class FestePreise(Lauf):
    """Feste Preise (09.11.2026): Einzelpreis je Produkt und Preise je Ausführung in daten/feste-preise.json."""

    def setUp(self):
        super().setUp()
        self.bezug["BF-V-1"] = {**eintrag("https://h.test/p1", 10.91, ""), "artikel": "Typ 45810001"}
        self.bezug["BF-V-2"] = {**eintrag("https://h.test/s", 10.0, "ab"), "varianten": {
            "BF-V-2-01": {"artikel": "Typ 77770001", "ek_netto": 10.0, "bestell_url": "https://h.test/v"},
            "BF-V-2-02": {"artikel": "Typ 77770002", "ek_netto": 12.0}}}
        self.bezug["BF-V-2"]["varianten"]["BF-V-2-02"]["bestell_url"] = "https://h.test/v"
        (self.tmp / "bq.json").write_text(json.dumps(self.bezug))
        self.fest = {"BF-V-1": {"preis": 12.0}, "BF-V-2": {"varianten": [
            {"sku": "BF-V-2-01", "ausfuehrung": "Teller 40 mm", "wahl": {"Teller": "40 mm"}, "preis": 11.0},
            {"sku": "BF-V-2-02", "ausfuehrung": "Teller 60 mm", "wahl": {"Teller": "60 mm"}, "preis": 13.2}]}}
        (self.tmp / "daten/feste-preise.json").write_text(json.dumps(self.fest, ensure_ascii=False, indent=1))
        self.seiten["https://h.test/p1"] = (200, "<h1>Typ 45810001</h1><p>10,91 €</p>")
        self.variantenseite(10.0, 12.0)

    def variantenseite(self, a, b, zweite="Typ 77770002"):
        self.seiten["https://h.test/v"] = (200, f"<table><tr><td>Typ 77770001</td><td>{a:.2f} €</td></tr>"
                                                f"<tr><td>{zweite}</td><td>{b:.2f} €</td></tr></table>".replace(".", ","))

    def feste(self):
        return json.loads((self.tmp / "daten/feste-preise.json").read_text())

    def test_preis_je_ausfuehrung(self):
        self.lauf()
        self.variantenseite(10.0, 12.5)
        self.lauf()
        vk = self.lauf()
        v = {x["sku"]: x["preis"] for x in self.feste()["BF-V-2"]["varianten"]}
        self.assertEqual(v, {"BF-V-2-01": 11.0, "BF-V-2-02": 13.75})
        self.assertNotIn("BF-V-2-02", vk)  # Ausführungen stehen nur in feste-preise.json
        self.assertNotIn("BF-V-2", json.loads((self.tmp / "daten/preiswaechter.json").read_text())["artikel"])

    def test_fester_einzelpreis(self):
        self.lauf()
        self.seiten["https://h.test/p1"] = (200, "<h1>Typ 45810001</h1><p>11,00 €</p>")
        self.lauf()
        self.lauf()
        self.assertEqual(self.feste()["BF-V-1"]["preis"], 12.1)

    def test_ausfuehrung_weg_nur_gemeldet(self):
        self.lauf()
        self.variantenseite(10.0, 12.0, zweite="Typ 99990002")
        self.lauf()
        with mock.patch.dict("os.environ", {"GITHUB_OUTPUT": str(self.tmp / "out.txt")}):
            self.lauf()
        self.assertIn("AUSFÜHRUNG NICHT MEHR DA", (self.tmp / "bericht.txt").read_text())
        self.assertIn("wichtig=ja", (self.tmp / "out.txt").read_text())
        self.assertEqual(len(self.feste()["BF-V-2"]["varianten"]), 2)  # bleibt im Shop
        self.lauf()
        self.assertNotIn("AUSFÜHRUNG NICHT MEHR DA", (self.tmp / "bericht.txt").read_text())  # nur einmal gemeldet

    def test_fester_preis_ausblenden_und_zurueck(self):
        self.lauf()
        self.seiten["https://h.test/p1"] = (404, "")
        self.lauf()
        self.lauf()
        self.assertNotIn("BF-V-1", self.feste())
        self.assertEqual(pw.lade_csv(self.tmp / "daten/ausgeblendet.csv")[0]["sku"], "BF-V-1")
        self.seiten["https://h.test/p1"] = (200, "<h1>Typ 45810001</h1><p>10,91 €</p>")
        self.lauf()
        self.lauf()
        self.assertEqual(self.feste()["BF-V-1"], {"preis": 12.0})

    def test_altes_secret_ueberspringt_feste_preise(self):
        del self.bezug["BF-V-2"]["varianten"]
        (self.tmp / "bq.json").write_text(json.dumps(self.bezug))
        self.lauf()
        self.seiten["https://h.test/p1"] = (200, "<h1>Typ 45810001</h1><p>3,00 €</p>")
        with mock.patch.dict("os.environ", {"GITHUB_OUTPUT": str(self.tmp / "out.txt")}):
            self.lauf()
        self.assertIn("SECRET BEZUGSQUELLEN VERALTET: 2", (self.tmp / "bericht.txt").read_text())
        self.assertIn("wichtig=ja", (self.tmp / "out.txt").read_text())
        self.assertEqual(self.feste(), self.fest)

    def test_neue_zuordnung_misst_neu_ein(self):
        self.lauf()
        stand = json.loads((self.tmp / "daten/preiswaechter.json").read_text())
        stand["artikel"]["BF-V-1"]["ref"] = "alt"
        stand["artikel"]["BF-V-1"]["vorschlag_vk"] = 99.0
        (self.tmp / "daten/preiswaechter.json").write_text(json.dumps(stand))
        self.lauf()
        a = json.loads((self.tmp / "daten/preiswaechter.json").read_text())["artikel"]["BF-V-1"]
        self.assertNotIn("vorschlag_vk", a)
        self.assertEqual(a["weg"], "nach:0")


if __name__ == "__main__":
    unittest.main()
