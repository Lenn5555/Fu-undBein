# beinundfuß.de

Shop für Einschlagfüße, Stellbeine und Maschinenfüße auf WordPress + WooCommerce.

| Ordner | Inhalt |
| --- | --- |
| `wp-content/themes/beinundfuss` | Block-Theme: Farben, Kopf/Fuß, Startseite (Einstieg, Produktwelten, Produktfinder-Teaser, 15 Anwendungen, Vorteile-Band) |
| `wp-content/plugins/beinundfuss-shop` | Produktwelten und Finder-Merkmale anlegen, Produktfinder `[bf_produktfinder]`, „Preis auf Anfrage“, KI-Produktberater, schlanker Admin für Shop-Manager |
| `daten/ts-produkte.json` | Startsortiment aus ts-systemtechnik.de mit eigenen Texten (Quelle der Importdatei) |
| `import/produkte-woocommerce.csv` | Importdatei für den WooCommerce-Produktimporter (erzeugt) |
| `import/vergleichsprodukte-woocommerce.csv` | 667 Vergleichsprodukte anderer Hersteller aus der Recherche (erzeugt) |
| `werkzeuge/` | `build_import.py` (JSON → CSV), `build_vergleich.py` (Recherche → CSV), `build_auswahlliste.py` (Recherche → Excel), `build_preview.py` (statische Vorschau) |
| `vorschau/index.html` | Vorschau der Startseite mit funktionierendem Produktfinder (erzeugt) |

## Statische Website (ohne WordPress)

`python3 werkzeuge/build_site.py` erzeugt aus denselben Importdateien die komplette Website im Ordner `site/` (Startseite, Produktfinder, Kategorie- und Produktseiten, Kontakt, Rechtstexte). Der Ordner läuft auf jedem Webspace ohne PHP und ohne Datenbank.

- Einstellungen in `daten/site.json`: Anfrage-Adresse, Betreiberzeile, Bezahllinks (Artikelnummer → Stripe-Zahlungslink; ohne Link öffnet „Bestellen“ eine vorbereitete E-Mail).
- Rechtstexte als HTML in `daten/rechtstexte/impressum.html`, `datenschutz.html`, `agb.html`. Fehlen sie, steht dort ein Platzhalter; so nicht veröffentlichen.
- Produktbilder des TS-Sortiments werden von ts-systemtechnik.de geladen.

## Einrichtung auf Strato (WordPress-Variante)

1. **WordPress** für beinundfuß.de im bestehenden Strato-Paket installieren (Strato-Kundenbereich → WordPress → neue Installation, Domain beinundfuß.de zuweisen). Sprache Deutsch.
2. **Plugins** aus dem WordPress-Verzeichnis installieren: WooCommerce, Germanized for WooCommerce (Rechtstexte, Rechnungen, Preisangaben).
3. **Theme und Plugin hochladen**: Die Ordner `wp-content/themes/beinundfuss` und `wp-content/plugins/beinundfuss-shop` per SFTP an dieselbe Stelle kopieren. Im Plugin-Ordner vorher `composer install --no-dev` ausführen (lädt das Anthropic-SDK für den KI-Berater).
4. **Aktivieren**: Theme „beinundfuß“, dann Plugin „beinundfuß Shop“. Beim Aktivieren legt das Plugin die Produktwelten, die Finder-Merkmale und die Seite „Produktfinder“ an.
5. **WooCommerce-Einstellungen**:
   - Allgemein: Land Deutschland, Währung Euro.
   - MwSt.: „Preise werden ohne Steuer eingegeben“, Anzeige im Shop „ohne Steuer“ (B2B). Standardsteuersatz 19 %.
   - Germanized: Shop als B2B kennzeichnen, Rechnungen aktivieren, Rechtstexte (AGB, Widerruf, Datenschutz, Impressum) einbinden.
   - Zahlungsarten: z. B. Vorkasse, PayPal, Kauf auf Rechnung für Bestandskunden.
6. **Produkte importieren**: Produkte → Importieren → `import/produkte-woocommerce.csv`. Bilder werden dabei von ts-systemtechnik.de geladen.
   Danach `import/vergleichsprodukte-woocommerce.csv` (667 Artikel anderer Hersteller, „Preis auf Anfrage“, ohne Bilder, direkt veröffentlicht). Als Entwurf erzeugen: `python3 werkzeuge/build_vergleich.py <recherche-ordner> --entwurf`.
7. **Anfrage-Adresse** für „Preis auf Anfrage“ setzen: `wp option update bf_anfrage_email vertrieb@…` (oder Admin-E-Mail bleibt Standard).
8. **KI-Berater einschalten**: in `wp-config.php`
   `define( 'BF_ANTHROPIC_API_KEY', 'sk-ant-…' );`
   Ohne Schlüssel bleibt das Chatfenster einfach aus.
9. **Shop-Manager anlegen** (Benutzer → Neu, Rolle „Shop-Manager“): sieht im Admin nur Produkte, Bestellungen und Kunden.
10. **Zugang für Claude**: WooCommerce → Einstellungen → Erweitert → REST-API → Schlüssel mit Lese-/Schreibrecht anlegen und als geschützte Umgebungsvariable hinterlegen (nicht im Chat posten). Damit legt Claude Produkte als Entwurf an und ändert sie nach Freigabe.

## Produkte pflegen

Neue oder geänderte Produkte entstehen als Entwurf über die WooCommerce-REST-API und gehen erst nach Freigabe live. Für größere Umbauten am Startsortiment `daten/ts-produkte.json` ändern und `python3 werkzeuge/build_import.py` laufen lassen.

Finder-Merkmale (Filter): Anwendung, Funktion, Bauform, Material, Rohrmaß, Gewinde, Fußform, Anschluss, Bodenbefestigung. Werte dürfen kein Komma enthalten, weil WooCommerce Mehrfachwerte mit Komma trennt.

## Offen

- Preise für 16 Artikel ohne Preis bei TS (Gelenkfüße, Gerätebeine, Rollen u. a.) – bis dahin „Preis auf Anfrage“.
- Artikelnummern der Varianten sind die TS-Nummern; vor einer späteren SAP-Anbindung gegen SAP prüfen.
- SAP Business One: vorerst nicht angebunden (Entscheidung 08.10.2026), später nachrüstbar.
- Vergleichsprodukte sind sichtbar (Entscheidung 08.10.2026); Bezug (Händler/Hersteller), Einkaufspreise und Lieferzeiten für Anfragen noch klären. Technische Daten stammen aus Hersteller- und Händlerseiten und sind teils lückenhaft; Herstellerfotos nur mit Freigabe verwenden.

## KI-Berater (Zweig `ki-shop`)

Statt Katalog gibt es eine Seite mit KI-Berater. Er kennt nur Produkte **mit Preis** (`ki/worker/src/katalog.json`)
und zeigt passende Produkte mit Bestellknopf. Eine Bestellung geht als Mail an `sales@ts-systec.de`,
mit interner Bezugsquelle, Bestell-Link und EK. Der alte Katalog-Stand liegt im Zweig `stand-katalog-2026-10-08`.

Aufbau:
- `werkzeuge/build_ki.py` baut `site/` (Beraterseite, Rechtstexte) und `ki/worker/src/katalog.json`.
  Lokal schreibt es außerdem `/mnt/project-files/katalog/intern/ki-bezugsquellen.json` (vertraulich, nie ins Repo).
- `ki/seite/ki.js|css`: Chat und Bestellformular im Browser.
- `ki/worker/`: Cloudflare Worker mit `POST /beraten` (Claude, Werkzeug `produkte_zeigen`) und `POST /bestellen` (Mail über Resend).
  Händler und EK kommen beim Veröffentlichen aus dem GitHub-Secret `BEZUGSQUELLEN` in den Worker, nie ins Repo.

Einrichten (einmalig, ohne Terminal):
1. Konten: Anthropic (API-Schlüssel), Cloudflare (Worker, API-Token mit Vorlage „Edit Cloudflare Workers“), Resend (Domain bestätigen, API-Schlüssel).
2. Im GitHub-Repo unter Settings > Secrets and variables > Actions diese Secrets anlegen:
   `ANTHROPIC_API_KEY`, `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `RESEND_API_KEY` und
   `BEZUGSQUELLEN` (Inhalt von `/mnt/project-files/katalog/intern/ki-bezugsquellen-fuer-github.txt`).
3. Unter Actions den Workflow „KI-Server veröffentlichen“ starten. Die Worker-Adresse (…workers.dev) in `daten/site.json` als `ki_api` eintragen.

Tests: `cd ki/worker && npm test`. Nach neuen Preisen: `preise_uebernehmen.py`, dann `build_ki.py`, das Secret `BEZUGSQUELLEN` erneuern und den Workflow neu starten.
