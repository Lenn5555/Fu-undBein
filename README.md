# beinundfuß.de

Shop für Einschlagfüße, Stellbeine und Maschinenfüße auf WordPress + WooCommerce.

| Ordner | Inhalt |
| --- | --- |
| `wp-content/themes/beinundfuss` | Block-Theme: Farben, Kopf/Fuß, Startseite (Einstieg, Produktwelten, Produktfinder-Teaser, 15 Anwendungen, Vorteile-Band) |
| `wp-content/plugins/beinundfuss-shop` | Produktwelten und Finder-Merkmale anlegen, Produktfinder `[bf_produktfinder]`, „Preis auf Anfrage“, KI-Produktberater, schlanker Admin für Shop-Manager |
| `daten/ts-produkte.json` | Startsortiment aus ts-systemtechnik.de mit eigenen Texten (Quelle der Importdatei) |
| `import/produkte-woocommerce.csv` | Importdatei für den WooCommerce-Produktimporter (erzeugt) |
| `werkzeuge/` | `build_import.py` (JSON → CSV), `build_preview.py` (statische Vorschau) |
| `vorschau/index.html` | Vorschau der Startseite mit funktionierendem Produktfinder (erzeugt) |

## Einrichtung auf Strato

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
- Produktwelten Schwingungsdämpfer, Hygienefüße, Schwerlastfüße sind noch leer; Kandidaten in der Herstellerrecherche.
