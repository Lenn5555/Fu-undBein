/* Anonyme Besucherzählung von beinundfuß.de: keine Cookies, kein Speicher im Browser, keine Kennung.
   Gemeldet wird nur, welche Art Ereignis passiert ist und woher der Besuch kam (Werbung, Google, …).
   Der Server zählt daraus Tagessummen (ki/worker/src/statistik.js). */
(function () {
  "use strict";
  var cfg = window.bfZaehlen || {};
  if (!cfg.api || cfg.seite === "statistik" || navigator.webdriver || /bot|crawl|spider|slurp|preview/i.test(navigator.userAgent)) {
    window.bfZaehle = function () {};
    return;
  }
  var q = new URLSearchParams(location.search);
  var ref = "";
  try { ref = document.referrer ? new URL(document.referrer).hostname : ""; } catch (e) { ref = ""; }
  var intern = ref === location.hostname;
  var werbung = q.get("herkunft") === "werbung" || q.has("gclid") || q.has("gbraid") || q.has("wbraid") ||
    /^(cpc|ppc|paid|ads?)$/i.test(q.get("utm_medium") || "");
  var quelle = werbung ? "werbung"
    : intern ? "intern"
    : !ref ? "direkt"
    : /(^|\.)google\./.test(ref) ? "google"
    : /(^|\.)(bing|duckduckgo|ecosia|yahoo|qwant|startpage)\./.test(ref) ? "suchmaschine"
    : "andere_seite";
  window.bfHerkunft = werbung ? "werbung" : "";

  function melden(ereignisse) {
    var daten = JSON.stringify({ ereignisse: ereignisse, quelle: quelle, seite: cfg.seite });
    try {
      // text/plain: einfache Anfrage ohne Vorabfrage; keepalive, damit sie auch beim Seitenwechsel ankommt
      fetch(cfg.api.replace(/\/$/, "") + "/zaehlen", { method: "POST", body: daten, keepalive: true, headers: { "Content-Type": "text/plain" } })
        .catch(function () { /* Zählen ist nie wichtiger als die Seite */ });
    } catch (e) { /* egal */ }
  }
  var gemeldet = {};
  // Jedes Ereignis höchstens einmal pro Seitenaufruf
  window.bfZaehle = function (ereignis) {
    if (gemeldet[ereignis]) return;
    gemeldet[ereignis] = true;
    melden([ereignis]);
  };
  melden(intern ? ["seitenaufruf"] : ["seitenaufruf", "besuch"]);
  if (cfg.seite === "produkt") window.bfZaehle("produktseite");

  // Besuch aus der Werbung: Herkunft über interne Links weitergeben (nur als Adresszusatz, nichts wird gespeichert)
  if (werbung) {
    document.addEventListener("click", function (ev) {
      var a = ev.target.closest && ev.target.closest("a[href]");
      if (!a || a.hostname !== location.hostname || a.protocol.indexOf("http") !== 0) return;
      var u = new URL(a.href);
      if (u.searchParams.get("herkunft") === "werbung") return;
      u.searchParams.set("herkunft", "werbung");
      a.href = u.toString();
    }, true);
    if (q.has("herkunft")) {
      q.delete("herkunft");
      var rest = q.toString();
      history.replaceState(history.state, "", location.pathname + (rest ? "?" + rest : "") + location.hash);
    }
  }
})();
