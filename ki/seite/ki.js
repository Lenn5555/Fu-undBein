/* KI-Berater von beinundfuß.de: Chat, Produktkarten mit Preis, Bestellformular. */
(function () {
  "use strict";
  var cfg = window.bfKi || {};
  var box = document.getElementById("ki");
  var form = document.getElementById("ki-eingabe");
  var feld = document.getElementById("ki-text");
  var dialog = document.getElementById("ki-bestellen");
  // Klick oder Tippen auf den abgedunkelten Bereich neben dem Bestellfeld schließt es.
  // Nur wenn der Klick dort auch begonnen hat, damit Markieren im Formular es nicht zufällig schließt.
  var startDraussen = false;
  function draussen(ev) {
    var r = dialog.getBoundingClientRect();
    return ev.clientX < r.left || ev.clientX > r.right || ev.clientY < r.top || ev.clientY > r.bottom;
  }
  if (dialog) {
    dialog.addEventListener("pointerdown", function (ev) { startDraussen = ev.target === dialog && draussen(ev); });
    dialog.addEventListener("click", function (ev) {
      if (startDraussen && ev.target === dialog && draussen(ev)) dialog.close();
      startDraussen = false;
    });
  }
  var chips = document.getElementById("ki-chips");
  var verlauf = [];
  var karten = {};

  function el(tag, klasse, text) {
    var n = document.createElement(tag);
    if (klasse) n.className = klasse;
    if (text != null) n.textContent = text;
    return n;
  }
  function euro(x) {
    return x.toFixed(2).replace(".", ",").replace(/\B(?=(\d{3})+,)/g, ".") + " €";
  }
  function bildUrl(b) {
    return b && b.charAt(0) === "/" && b.charAt(1) !== "/" ? (cfg.basis || "") + b : b;
  }
  function preisText(p) {
    var w = p.varianten.length ? p.varianten.map(function (v) { return v.preis; }) : [p.preis];
    var min = Math.min.apply(null, w);
    var ab = p.preis_ab || w.some(function (x) { return x !== min; });
    return (ab ? "ab " : "") + euro(min) + " zzgl. MwSt.";
  }
  function speichern() {
    try { sessionStorage.setItem("bf-ki", JSON.stringify({ verlauf: verlauf, karten: karten })); } catch (e) { /* egal */ }
  }
  function nachUnten() { box.scrollTop = box.scrollHeight; }

  function blase(rolle, text) {
    var b = el("div", "ki-blase ki-" + rolle);
    text.split(/\n{2,}/).forEach(function (abs) { b.appendChild(el("p", null, abs)); });
    box.appendChild(b);
    nachUnten();
    return b;
  }

  function karte(p) {
    var k = el("article", "ki-karte");
    var img = el("img");
    img.src = bildUrl(p.bild); img.alt = ""; img.loading = "lazy";
    k.appendChild(img);
    var t = el("div", "ki-karte-text");
    t.appendChild(el("h3", null, p.name));
    if (p.kurz) t.appendChild(el("p", "ki-kurz", p.kurz));
    var m = el("ul", "ki-merkmale");
    ["Gewinde", "Rohrmaß", "Durchmesser", "Traglast", "Material", "Verstellbereich"].forEach(function (n) {
      if (p.merkmale[n]) m.appendChild(el("li", null, n + ": " + p.merkmale[n]));
    });
    t.appendChild(m);
    var preis = el("p", "ki-preis", preisText(p));
    var wahl = auswahlFelder(p, function () {
      var v = wahl.variante();
      preis.textContent = v ? euro(v.preis) + " netto pro Stück" : preisText(p);
    });
    if (wahl.feld) t.appendChild(wahl.feld);
    t.appendChild(preis);
    var knopf = el("button", "btn", "Bestellen");
    knopf.type = "button";
    knopf.addEventListener("click", function () { bestellen(p, wahl.werte()); });
    t.appendChild(knopf);
    k.appendChild(t);
    return k;
  }

  // Auswahl zum Anklicken: Ausführungen mit eigenem Preis (Varianten) und wählbare Merkmale wie das Gewinde
  var gruppenNr = 0;
  function auswahlFelder(p, beiAenderung, vorher) {
    vorher = vorher || {};
    var feld = null, gruppen = {}, nr = ++gruppenNr;
    function gruppe(titel, schluessel, eintraege, gewaehlt) {
      if (!feld) feld = el("div", "ki-wahl");
      var fs = el("fieldset", "ki-wahl-gruppe");
      fs.appendChild(el("legend", null, titel + " wählen"));
      var reihe = el("div", "ki-pillen");
      eintraege.forEach(function (x, i) {
        var l = el("label", "ki-pille");
        var r = el("input"); r.type = "radio"; r.name = "w" + nr + "-" + schluessel; r.value = x.wert;
        if (i === 0) r.required = true;
        if (x.wert === gewaehlt) r.checked = true;
        r.addEventListener("change", beiAenderung);
        l.appendChild(r);
        l.appendChild(el("span", null, x.text));
        reihe.appendChild(l);
      });
      fs.appendChild(reihe); feld.appendChild(fs);
      gruppen[schluessel] = fs;
    }
    function wert(schluessel) {
      var fs = gruppen[schluessel], r = fs && fs.querySelector("input:checked");
      return r ? r.value : null;
    }
    if (p.varianten.length > 1 || (p.varianten.length === 1 && p.preis_ab)) {
      gruppe("Ausführung", "variante", p.varianten.map(function (v) { return { wert: v.sku, text: v.ausfuehrung + " · " + euro(v.preis) }; }), vorher.variante);
    }
    Object.keys(p.optionen || {}).forEach(function (m) {
      gruppe(m, "opt-" + m, p.optionen[m].map(function (w) { return { wert: w, text: w }; }), vorher.optionen && vorher.optionen[m]);
    });
    return {
      feld: feld,
      variante: function () {
        var sku = gruppen.variante ? wert("variante") : (p.varianten.length === 1 ? p.varianten[0].sku : null);
        return p.varianten.filter(function (v) { return v.sku === sku; })[0] || null;
      },
      werte: function () {
        var o = {};
        Object.keys(p.optionen || {}).forEach(function (m) { var w = wert("opt-" + m); if (w) o[m] = w; });
        var v = this.variante();
        return { variante: v ? v.sku : null, optionen: o };
      }
    };
  }

  function kartenZeigen(liste) {
    if (!liste.length) return;
    var reihe = el("div", "ki-karten");
    liste.forEach(function (p) { karten[p.sku] = p; reihe.appendChild(karte(p)); });
    box.appendChild(reihe);
    nachUnten();
  }

  function begruessen() {
    blase("berater", "Guten Tag! Wofür brauchen Sie Füße? Nennen Sie mir zum Beispiel Anwendung, Gewinde oder Rohrmaß und ungefähre Last. Wenn Sie unsicher sind, frage ich nach.");
  }

  // Anonyme Zählung (zaehlen.js); fehlt sie, passiert nichts
  function zaehle(ereignis) {
    if (window.bfZaehle) window.bfZaehle(ereignis);
  }

  function senden(text) {
    zaehle("chat_start");
    verlauf.push({ rolle: "kunde", text: text });
    blase("kunde", text);
    if (chips) chips.hidden = true;
    var warte = el("div", "ki-blase ki-berater ki-warte");
    warte.setAttribute("aria-label", "Berater schreibt");
    warte.innerHTML = "<span></span><span></span><span></span>";
    box.appendChild(warte); nachUnten();
    form.querySelector("button").disabled = true;
    if (!cfg.api) {
      warte.remove();
      blase("berater", "Der Berater ist noch nicht verbunden. Schreiben Sie uns gern an " + cfg.email + ".");
      form.querySelector("button").disabled = false;
      return;
    }
    fetch(cfg.api.replace(/\/$/, "") + "/beraten", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ verlauf: verlauf })
    }).then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
      .then(function (x) {
        warte.remove();
        if (!x.ok) throw new Error(x.d.fehler || "Fehler");
        var notiz = x.d.produkte.length ? "\n\n(Angezeigt: " + x.d.produkte.map(function (p) { return p.sku; }).join(", ") + ")" : "";
        verlauf.push({ rolle: "berater", text: x.d.antwort + notiz, produkte: x.d.produkte.map(function (p) { return p.sku; }) });
        var antwortBlase = blase("berater", x.d.antwort);
        kartenZeigen(x.d.produkte);
        if (x.d.produkte.length) zaehle("produktkarten");
        // Antworttext oben im Fenster lassen, damit er nicht hinter den Karten verschwindet
        if (x.d.produkte.length) box.scrollTop = antwortBlase.offsetTop - box.offsetTop - 12;
        speichern();
      })
      .catch(function (err) {
        warte.remove();
        verlauf.pop();
        blase("berater ki-fehler", (err && err.message && err.message !== "Failed to fetch" ? err.message : "Keine Verbindung zum Berater.") +
          " Sie erreichen uns auch per E-Mail an " + cfg.email + ".");
      })
      .then(function () { form.querySelector("button").disabled = false; feld.focus(); });
  }

  // Versandkosten im Bestellformular: Lieferland wählen, „ab …“ unter der Summe, Tabelle nach Gewicht zum Aufklappen.
  // Produktgewichte gibt es noch nicht, deshalb kein genauer Betrag (Lenn, 22.10.2026).
  var versandDaten = null;
  function versandLaden() {
    if (versandDaten) return Promise.resolve(versandDaten);
    return fetch((cfg.basis || "") + "/assets/versandkosten.json")
      .then(function (r) { return r.json(); })
      .then(function (v) { versandDaten = v; return v; });
  }
  function versandFelder() {
    var l = el("label", null, "Lieferland *");
    var wahl = el("select"); wahl.name = "land"; wahl.required = true;
    var de = el("option", null, "Deutschland"); de.value = "Deutschland"; wahl.appendChild(de);
    l.appendChild(wahl);
    var ab = el("p", "ki-versand-ab");
    var d = el("details", "ki-versand");
    d.appendChild(el("summary", null, "Versandkosten nach Gewicht anzeigen"));
    var inhalt = el("div", "ki-versand-inhalt");
    d.appendChild(inhalt);
    function kg(x) { return String(x).replace(".", ",") + " kg"; }
    function tarif(v) {
      var t = v.europa.laender.filter(function (x) { return x.land === wahl.value; })[0];
      return { bis: v.europa.bis_kg, preise: t.preise, luft: t.luftfracht };
    }
    function zeigen() {
      if (!versandDaten) { ab.textContent = "Versand: zzgl., den Betrag nennen wir in der Auftragsbestätigung."; return; }
      // Deutschland: feste Pauschale pro Bestellung, keine Gewichtstabelle (Lenn, 09.11.2026)
      d.hidden = wahl.value === "Deutschland";
      if (wahl.value === "Deutschland") {
        ab.textContent = "Versand innerhalb Deutschlands: pauschal " + euro(versandDaten.deutschland.pauschal) + " netto pro Bestellung.";
        return;
      }
      var t = tarif(versandDaten);
      ab.textContent = "Versand nach " + wahl.value + ": ab " + euro(t.preise[0]) + " netto pro Paket (bis " + kg(t.bis[0]) +
        "), je nach Gewicht. Den genauen Betrag nennen wir in der Auftragsbestätigung.";
      inhalt.textContent = "";
      var tab = el("table");
      t.bis.forEach(function (g, i) {
        var tr = el("tr");
        tr.appendChild(el("td", null, "bis " + kg(g)));
        tr.appendChild(el("td", "ki-zahl", euro(t.preise[i])));
        tab.appendChild(tr);
      });
      inhalt.appendChild(tab);
      if (t.luft) inhalt.appendChild(el("p", null, "Versand per Luftfracht, berechnet nach Volumengewicht."));
      var a = el("a", null, "Alle Versandkosten und Hinweise");
      a.href = (cfg.basis || "") + "/versandkosten/"; a.target = "_blank";
      var p = el("p"); p.appendChild(a); inhalt.appendChild(p);
    }
    wahl.addEventListener("change", zeigen);
    versandLaden().then(function (v) {
      v.europa.laender.forEach(function (x) { var o = el("option", null, x.land); o.value = x.land; wahl.appendChild(o); });
      zeigen();
    }).catch(zeigen);
    zeigen();
    // USt-IdNr.: Pflicht im EU-Ausland, freiwillig außerhalb der EU, in Deutschland ausgeblendet
    var ust = el("label", null, "USt-IdNr. *");
    var ustFeld = el("input"); ustFeld.type = "text"; ustFeld.name = "ust_id"; ustFeld.maxLength = 20;
    ustFeld.placeholder = "z. B. IT12345678901"; ustFeld.autocomplete = "off";
    ust.appendChild(ustFeld);
    var ausland = el("p", "ki-versand-ab");
    function ustZeigen() {
      var info = versandDaten && versandDaten.europa.laender.filter(function (x) { return x.land === wahl.value; })[0];
      var eu = !info || info.eu;
      var inland = wahl.value === "Deutschland";
      ust.hidden = inland; ausland.hidden = inland;
      ustFeld.required = !inland && eu;
      ust.firstChild.textContent = eu ? "USt-IdNr. *" : "USt-IdNr. oder Steuernummer (falls vorhanden)";
      ausland.textContent = eu
        ? "Lieferung ins EU-Ausland ohne deutsche MwSt. mit Ihrer gültigen USt-IdNr."
        : "Lieferung außerhalb der EU: Zoll und Versand stimmen wir vor der Auftragsbestätigung mit Ihnen ab.";
    }
    wahl.addEventListener("change", ustZeigen);
    ustZeigen();
    versandLaden().then(ustZeigen, function () {});
    return { land: l, ab: ab, tabelle: d, ust: ust, ausland: ausland };
  }

  var ZAHLARTEN = ["Überweisung (Vorkasse)", "Kreditkarte", "PayPal"];

  // Sofortbezahlen mit PayPal oder Karte (über PayPal): nur wenn der Server Zugangsdaten hat und der Preis fest ist.
  // Der Betrag wird auf dem Server berechnet; hier nur zur Anzeige mit derselben Versandpauschale (bis 5 kg).
  var MWST = 0.19;
  var bezahlInfo = null, paypalSkript = null;
  function bezahlenLaden() {
    if (!cfg.api) return Promise.resolve({ aktiv: false });
    if (!bezahlInfo) bezahlInfo = fetch(cfg.api.replace(/\/$/, "") + "/bezahlen")
      .then(function (r) { return r.json(); }).catch(function () { return { aktiv: false }; });
    return bezahlInfo;
  }
  function paypalLaden(info) {
    if (!paypalSkript) paypalSkript = new Promise(function (ok, nein) {
      var s = document.createElement("script");
      s.src = "https://www.paypal.com/sdk/js?client-id=" + encodeURIComponent(info.client_id) +
        "&currency=EUR&intent=capture&components=buttons&locale=de_DE&enable-funding=card&disable-funding=paylater,sepa";
      s.onload = function () { ok(window.paypal); };
      s.onerror = function () { paypalSkript = null; nein(new Error("PayPal konnte nicht geladen werden.")); };
      document.head.appendChild(s);
    });
    return paypalSkript;
  }
  function pauschale(land) {
    if (!versandDaten) return null;
    return land === "Deutschland" ? versandDaten.deutschland.pauschal : null; // Sofortbezahlen nur in Deutschland
  }

  function bestellen(p, vorher) {
    dialog.innerHTML = "";
    var f = el("form", "ki-formular");
    f.appendChild(el("h2", null, "Bestellen"));
    f.appendChild(el("p", "ki-kurz", p.name));
    function zeile(label, name, typ, pflicht, extra) {
      var l = el("label", null, label + (pflicht ? " *" : ""));
      var i = el(typ === "textarea" ? "textarea" : "input");
      if (typ !== "textarea") i.type = typ;
      i.name = name; i.required = !!pflicht;
      if (extra) Object.keys(extra).forEach(function (k) { i[k] = extra[k]; });
      l.appendChild(i); f.appendChild(l);
      return i;
    }
    var wahl = auswahlFelder(p, function () { rechnen(); }, vorher);
    if (wahl.feld) f.appendChild(wahl.feld);
    var menge = zeile("Menge (Stück)", "menge", "number", true, { min: 1, max: 100000, value: 4 });
    var summe = el("p", "ki-preis");
    function rechnen() {
      var v = wahl.variante();
      var st = v ? v.preis : p.preis;
      var n = parseInt(menge.value, 10) || 0;
      summe.textContent = "Summe: " + euro(st * n) + " netto zzgl. MwSt. und Versand" + (p.preis_ab && !v ? " (ab-Preis, den Preis für Ihre Ausführung bestätigen wir)" : "");
    }
    menge.addEventListener("input", rechnen);
    f.appendChild(summe); rechnen();
    var versand = versandFelder();
    zeile("Firma", "firma", "text", false, { autocomplete: "organization" });
    zeile("Name", "name", "text", true, { autocomplete: "name" });
    zeile("E-Mail", "email", "email", true, { autocomplete: "email" });
    zeile("Telefon", "telefon", "tel", false, { autocomplete: "tel" });
    // Lieferadresse in einzelnen Feldern
    f.appendChild(el("h3", "ki-abschnitt", "Lieferadresse"));
    zeile("Straße und Hausnummer", "strasse", "text", true, { autocomplete: "shipping street-address", maxLength: 120 });
    zeile("Adresszusatz", "zusatz", "text", false, { maxLength: 120, placeholder: "z. B. Halle 3, Wareneingang" });
    var plzOrt = el("div", "ki-plz-ort");
    var plzEnde = f.lastChild;
    zeile("PLZ", "plz", "text", true, { autocomplete: "shipping postal-code", maxLength: 10, inputMode: "numeric" });
    zeile("Ort", "ort", "text", true, { autocomplete: "shipping address-level2", maxLength: 80 });
    plzOrt.appendChild(plzEnde.nextSibling); plzOrt.appendChild(plzEnde.nextSibling);
    f.appendChild(plzOrt);
    f.appendChild(versand.land); f.appendChild(versand.ab); f.appendChild(versand.tabelle);
    f.appendChild(versand.ausland);
    f.appendChild(versand.ust);
    // Rechnungsadresse: standardmäßig gleich der Lieferadresse; abgewählt erscheinen eigene Felder, vorbelegt mit der Lieferadresse
    f.appendChild(el("h3", "ki-abschnitt", "Rechnungsadresse"));
    var gl = el("label", "ki-check");
    var gleich = el("input"); gleich.type = "checkbox"; gleich.checked = true;
    gl.appendChild(gleich); gl.appendChild(el("span", null, "Rechnungsadresse ist gleich der Lieferadresse"));
    f.appendChild(gl);
    var rBox = el("div", "ki-rechnung"); rBox.hidden = true;
    var rFelder = {};
    [["Firma", "firma", false, "billing organization"], ["Name", "name", false, "billing name"],
     ["Straße und Hausnummer", "strasse", true, "billing street-address"], ["Adresszusatz", "zusatz", false, "off"],
     ["PLZ", "plz", true, "billing postal-code"], ["Ort", "ort", true, "billing address-level2"], ["Land", "land", true, "billing country-name"]]
      .forEach(function (x) {
        var l = el("label", null, x[0] + (x[2] ? " *" : ""));
        var i = el("input"); i.type = "text"; i.autocomplete = x[3]; i.maxLength = x[1] === "plz" ? 10 : 120;
        i.dataset.pflicht = x[2] ? "1" : "";
        l.appendChild(i); rBox.appendChild(l); rFelder[x[1]] = i;
      });
    f.appendChild(rBox);
    function rechnungZeigen() {
      rBox.hidden = gleich.checked;
      Object.keys(rFelder).forEach(function (k) { rFelder[k].required = !gleich.checked && !!rFelder[k].dataset.pflicht; });
      if (!gleich.checked) {
        var e = f.elements;
        var von = { firma: e.firma.value, name: e.name.value, strasse: e.strasse.value, zusatz: e.zusatz.value,
          plz: e.plz.value, ort: e.ort.value, land: e.land.value };
        var leer = Object.keys(rFelder).every(function (k) { return !rFelder[k].value; });
        if (leer) Object.keys(rFelder).forEach(function (k) { rFelder[k].value = von[k] || ""; });
        rFelder.firma.focus();
      }
    }
    gleich.addEventListener("change", rechnungZeigen);
    // Zahlung nur im Voraus; die Zahlungsdaten kommen mit der Auftragsbestätigung
    var zahl = el("label", null, "Zahlungsart *");
    var zs = el("select"); zs.name = "zahlart"; zs.required = true;
    ZAHLARTEN.forEach(function (x) { var o = el("option", null, x); o.value = x; zs.appendChild(o); });
    zahl.appendChild(zs); f.appendChild(zahl);
    var zahlHinweis = el("p", "ki-kurz");
    f.appendChild(zahlHinweis);
    zeile("Hinweis", "hinweis", "textarea", false, { rows: 2 });
    var falle = zeile("Website", "website", "text", false, { tabIndex: -1, autocomplete: "off" });
    falle.parentNode.className = "ki-falle";
    var zl = el("label", "ki-check");
    var z = el("input"); z.type = "checkbox"; z.name = "zustimmung"; z.required = true;
    zl.appendChild(z);
    // Text in einem Element, sonst verteilt das Flex-Layout jedes Textstück auf eine eigene Spalte
    var zt = el("span");
    zt.appendChild(document.createTextNode("Ich bestelle als Unternehmer, nicht als Verbraucher. Es gelten die "));
    var agb = el("a", "", "AGB"); agb.href = (cfg.basis || "") + "/agb/"; agb.target = "_blank";
    zt.appendChild(agb);
    zt.appendChild(document.createTextNode(". Meine Angaben werden zur Bearbeitung der Bestellung verwendet (siehe Datenschutz)."));
    zl.appendChild(zt);
    f.appendChild(zl);
    var meldung = el("p", "ki-meldung");
    f.appendChild(meldung);
    var knoepfe = el("div", "ki-knoepfe");
    var ab = el("button", "btn btn-hell", "Abbrechen"); ab.type = "button";
    ab.addEventListener("click", function () { dialog.close(); });
    var ok = el("button", "btn", "Verbindlich bestellen"); ok.type = "submit";
    knoepfe.appendChild(ab); knoepfe.appendChild(ok); f.appendChild(knoepfe);
    var sofortBox = el("div", "ki-sofort"); sofortBox.hidden = true;
    var sofortSumme = el("p", "ki-preis");
    var paypalFeld = el("div", "ki-paypal");
    sofortBox.appendChild(sofortSumme); sofortBox.appendChild(paypalFeld);
    f.insertBefore(sofortBox, knoepfe);
    f.appendChild(el("p", "ki-kurz", "Sie erhalten von uns eine Auftragsbestätigung per E-Mail. Erst damit kommt der Vertrag zustande."));

    function daten() {
      var d = {};
      new FormData(f).forEach(function (v, k) { if (!/^w\d+-/.test(k)) d[k] = v; });
      var w = wahl.werte();
      if (w.variante) d.variante = w.variante;
      d.optionen = w.optionen;
      d.sku = p.sku; d.menge = parseInt(d.menge, 10); d.zustimmung = z.checked;
      d.rechnung_gleich = gleich.checked;
      if (!gleich.checked) {
        d.rechnung = {};
        Object.keys(rFelder).forEach(function (k) { d.rechnung[k] = rFelder[k].value; });
      }
      if (window.bfHerkunft) d.herkunft = window.bfHerkunft; // nur „werbung“, für die Erfolgsmessung der Anzeigen
      return d;
    }
    function api(pfad, d) {
      return fetch(cfg.api.replace(/\/$/, "") + pfad, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(d)
      }).then(function (r) { return r.json().then(function (x) { if (!r.ok) throw new Error(x.fehler || "Fehler"); return x; }); });
    }

    // Zahlungsart: bei PayPal/Karte mit festem Preis erscheinen die PayPal-Knöpfe statt „Verbindlich bestellen“
    var info = { aktiv: false }, quelle = null;
    function sofortMoeglich() {
      var v = wahl.variante();
      return info.aktiv && (zs.value === "PayPal" || zs.value === "Kreditkarte") && !(p.preis_ab && !v) &&
        !(p.varianten.length && !v) && pauschale(f.elements.land.value) != null;
    }
    function zahlungZeigen() {
      var sofort = sofortMoeglich();
      ok.hidden = sofort; sofortBox.hidden = !sofort;
      if (!sofort) {
        var karte = info.aktiv && zs.value !== ZAHLARTEN[0];
        zahlHinweis.textContent = (karte && p.varianten.length && !wahl.variante() ? "Bitte zuerst eine Ausführung wählen, dann können Sie sofort bezahlen. "
          : karte && p.preis_ab && !wahl.variante() ? "Für diese Serie bestätigen wir zuerst den Preis Ihrer Ausführung. "
          : karte && f.elements.land.value !== "Deutschland" ? "Sofortbezahlen ist nur bei Lieferung nach Deutschland möglich. " : "") +
          "Wir liefern gegen Vorkasse. Die Zahlungsdaten oder den Zahlungslink erhalten Sie mit der Auftragsbestätigung, der Versand erfolgt nach Zahlungseingang.";
        return;
      }
      var v = wahl.variante(), n = parseInt(menge.value, 10) || 0, land = f.elements.land.value;
      var ware = Math.round((v ? v.preis : p.preis) * n * 100), vs = Math.round(pauschale(land) * 100);
      var mw = land === "Deutschland" ? Math.round((ware + vs) * MWST) : 0;
      sofortSumme.textContent = "Jetzt zu zahlen: " + euro((ware + vs + mw) / 100) + " (Ware " + euro(ware / 100) +
        " + Versandpauschale " + euro(vs / 100) + (mw ? " + 19 % MwSt. " + euro(mw / 100) : ", ohne deutsche MwSt.") + ")";
      zahlHinweis.textContent = "Sie bezahlen sofort über PayPal" + (zs.value === "Kreditkarte" ? " mit Ihrer Karte" : "") +
        ". Mit der Zahlung ist Ihre Bestellung verbindlich; wir versenden nach Zahlungseingang. Der Versand ist mit der Pauschale abgegolten.";
      var neu = zs.value === "Kreditkarte" ? "card" : "paypal";
      if (quelle === neu) return;
      quelle = neu; paypalFeld.textContent = "PayPal wird geladen …";
      paypalLaden(info).then(function (pp) {
        if (quelle !== neu) return;
        paypalFeld.textContent = "";
        pp.Buttons({
          fundingSource: neu === "card" ? pp.FUNDING.CARD : pp.FUNDING.PAYPAL,
          style: { layout: "vertical", label: "pay" },
          onClick: function (_, actions) {
            if (!f.reportValidity()) return actions.reject();
            meldung.textContent = "";
            return actions.resolve();
          },
          createOrder: function () { return api("/bezahlen/start", daten()).then(function (x) { return x.id; }); },
          onApprove: function (d) {
            meldung.textContent = "Zahlung wird abgeschlossen …";
            var x = daten(); x.paypal_id = d.orderID;
            return api("/bezahlen/abschluss", x).then(function (r) {
              dialog.close();
              blase("berater", "Danke! Ihre Bestellung " + r.bestellnummer + " ist bezahlt (" + euro(r.gesamt / 100) +
                "). Sie erhalten von PayPal eine Zahlungsbestätigung, wir melden uns mit der Auftragsbestätigung.");
            });
          },
          onCancel: function () { meldung.textContent = "Zahlung abgebrochen. Es wurde nichts abgebucht."; },
          onError: function (err) {
            meldung.textContent = (err && err.message && !/^Fehler$/.test(err.message) ? err.message : "Die Zahlung hat nicht geklappt.") +
              " Sie können auch „Überweisung (Vorkasse)“ wählen.";
          },
        }).render(paypalFeld);
      }).catch(function (err) { paypalFeld.textContent = err.message + " Bitte „Überweisung (Vorkasse)“ wählen."; });
    }
    zs.addEventListener("change", zahlungZeigen);
    f.addEventListener("change", function (ev) { if (ev.target !== zs) zahlungZeigen(); });
    menge.addEventListener("input", zahlungZeigen);
    zahlungZeigen();
    Promise.all([bezahlenLaden(), versandLaden().catch(function () {})]).then(function (x) { info = x[0] || { aktiv: false }; zahlungZeigen(); });

    f.addEventListener("submit", function (ev) {
      ev.preventDefault();
      if (sofortMoeglich()) return; // bezahlt wird über die PayPal-Knöpfe
      var d = daten();
      ok.disabled = true; meldung.textContent = "Wird gesendet …";
      if (!cfg.api) { meldung.textContent = "Online-Bestellung ist noch nicht verbunden."; ok.disabled = false; return; }
      fetch(cfg.api.replace(/\/$/, "") + "/bestellen", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(d)
      }).then(function (r) { return r.json().then(function (x) { return { ok: r.ok, x: x }; }); })
        .then(function (r) {
          if (!r.ok) throw new Error(r.x.fehler || "Fehler");
          dialog.close();
          blase("berater", "Danke! Ihre Bestellung " + r.x.bestellnummer + " ist bei uns eingegangen. Wir melden uns mit der Auftragsbestätigung und den Zahlungsdaten.");
        })
        .catch(function (err) {
          meldung.textContent = (err.message !== "Failed to fetch" ? err.message : "Keine Verbindung.") + " Alternativ per E-Mail an " + cfg.email + ".";
          ok.disabled = false;
        });
    });
    dialog.appendChild(f);
    dialog.showModal();
    zaehle("bestellformular");
  }

  form.addEventListener("submit", function (ev) {
    ev.preventDefault();
    var t = feld.value.trim();
    if (!t) return;
    feld.value = "";
    feld.style.height = "";
    senden(t);
  });
  feld.addEventListener("input", function () {
    feld.style.height = "";
    feld.style.height = Math.min(feld.scrollHeight, 160) + "px";
  });
  // Beispielfragen, Einsätze, Preisliste und Lastrechner schicken ihre Frage direkt an den Berater
  document.querySelectorAll("[data-frage]").forEach(function (k) {
    k.addEventListener("click", function () {
      if (form.querySelector("button").disabled) return;
      // Fragen von außerhalb des Gesprächs (Einsätze, Preisliste, Lastrechner): zum Gespräch scrollen
      if (!k.closest(".kb-chat")) document.querySelector(".kb-chat").scrollIntoView({ behavior: "smooth", block: "start" });
      senden(k.getAttribute("data-frage"));
    });
  });
  var neu = document.getElementById("ki-neu");
  if (neu) neu.addEventListener("click", function () {
    verlauf = []; karten = {};
    try { sessionStorage.removeItem("bf-ki"); } catch (e) { /* egal */ }
    box.innerHTML = "";
    if (chips) chips.hidden = false;
    begruessen();
    feld.focus();
  });
  feld.addEventListener("keydown", function (ev) {
    if (ev.key === "Enter" && !ev.shiftKey) { ev.preventDefault(); form.requestSubmit(); }
  });

  // Gespräch nach Neuladen der Seite wiederherstellen
  try {
    var alt = JSON.parse(sessionStorage.getItem("bf-ki") || "null");
    if (alt && alt.verlauf && alt.verlauf.length) { verlauf = alt.verlauf; karten = alt.karten || {}; }
  } catch (e) { /* egal */ }
  begruessen();
  if (verlauf.length && chips) chips.hidden = true;
  verlauf.forEach(function (m) {
    blase(m.rolle, m.text.replace(/\n\n\(Angezeigt: [^)]*\)$/, ""));
    if (m.produkte) kartenZeigen(m.produkte.map(function (s) { return karten[s]; }).filter(Boolean));
  });

  // Links von den Produktseiten: ?frage=… startet das Gespräch, ?bestellen=Artikelnummer öffnet das Bestellformular
  var q = new URLSearchParams(location.search);
  if (q.get("frage") || q.get("bestellen")) {
    // Nur die eigenen Zusätze entfernen; „herkunft“ braucht noch die Zählung
    var rest = new URLSearchParams(location.search);
    rest.delete("frage"); rest.delete("bestellen");
    history.replaceState(null, "", location.pathname + (rest.toString() ? "?" + rest : "") + location.hash);
  }
  if (q.get("frage")) senden(q.get("frage").slice(0, 1500));
  if (q.get("bestellen")) {
    fetch((cfg.basis || "") + "/assets/katalog.json")
      .then(function (r) { return r.json(); })
      .then(function (liste) {
        var p = liste.filter(function (x) { return x.sku === q.get("bestellen"); })[0];
        if (!p) return;
        // Auswahl von der Produktseite übernehmen: ?variante=… oder ?opt-Gewinde=…
        var optionen = {};
        Object.keys(p.optionen || {}).forEach(function (m) { if (q.get("opt-" + m)) optionen[m] = q.get("opt-" + m); });
        bestellen(p, { variante: q.get("variante"), optionen: optionen });
      })
      .catch(function () { /* Formular bleibt zu, der Berater ist trotzdem da */ });
  }
})();
