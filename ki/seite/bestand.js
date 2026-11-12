/* Lagerbestand der T&S-Artikel auf den Produktseiten: füllt Zellen mit data-lager="Artikelnummer". */
(function () {
  "use strict";
  var api = (window.bfZaehlen && window.bfZaehlen.api) || "";
  var zellen = document.querySelectorAll("[data-lager]");
  if (!api || !zellen.length) return;
  fetch(api.replace(/\/$/, "") + "/bestand").then(function (r) { return r.json(); }).then(function (d) {
    var a = d.artikel || {}, irgendwas = false;
    zellen.forEach(function (z) {
      var s = z.getAttribute("data-lager");
      if (!Object.prototype.hasOwnProperty.call(a, s)) return;
      irgendwas = true;
      var n = a[s];
      z.textContent = n > 0 ? n + " Stück" : "nicht verfügbar";
      z.classList.add(n > 0 ? "pr-lager-ja" : "pr-lager-nein");
      if (n <= 0) {
        // Statt Bestellen: Anfrage per E-Mail, wann der Artikel wieder da ist
        var knopf = z.parentNode.querySelector(".pr-pille");
        var mail = z.getAttribute("data-mail");
        if (knopf && mail) {
          knopf.textContent = "Anfragen";
          knopf.href = "mailto:" + mail + "?subject=" + encodeURIComponent("Verfügbarkeit " + z.getAttribute("data-name"));
        }
      }
    });
    if (irgendwas) document.querySelectorAll(".pr-lager-spalte").forEach(function (x) { x.hidden = false; });
  }).catch(function () {});
})();
