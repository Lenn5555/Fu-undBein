/* beinundfuß Produktfinder – lädt alle Produkte über die WooCommerce Store API und filtert im Browser. */
(function () {
	'use strict';

	const cfg = window.bfFinder || {};
	const root = document.getElementById('bf-finder');
	if (!root || !cfg.api) return;

	// Schritte nach dem Konzept „Der Produktfinder“. Werte kommen aus den Produktdaten.
	const SCHRITTE = [
		{ merkmal: 'Anwendung', frage: 'Was möchten Sie aufstellen?' },
		{ merkmal: 'Funktion', frage: 'Welche Funktion ist wichtig?' },
		{ merkmal: 'Bauform', frage: 'Welche Bauform bevorzugen Sie?' },
		{ merkmal: 'Rohrmaß', frage: 'Welches Rohrmaß?', technik: true },
		{ merkmal: 'Gewinde', frage: 'Welches Gewinde?', technik: true },
		{ merkmal: 'Material', frage: 'Welches Material?', technik: true },
	];

	const SEITE = 24; // Karten pro „Weitere anzeigen“
	const auswahl = {};
	let produkte = [];
	let anzahl = SEITE;

	const el = (tag, attrs, ...kinder) => {
		const e = document.createElement(tag);
		Object.entries(attrs || {}).forEach(([k, v]) => {
			if (k === 'class') e.className = v;
			else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
			else e.setAttribute(k, v);
		});
		kinder.flat().forEach((k) => k != null && e.append(k));
		return e;
	};

	const merkmale = (p) => {
		const m = {};
		(p.attributes || []).forEach((a) => {
			m[a.name] = (a.terms || []).map((t) => t.name);
		});
		return m;
	};

	const passt = (p, ohne) =>
		Object.entries(auswahl).every(([merkmal, werte]) => {
			if (merkmal === ohne || !werte.length) return true;
			const vorhanden = p._m[merkmal] || [];
			return werte.some((w) => vorhanden.includes(w));
		});

	const preis = (p) => {
		const pr = p.prices || {};
		const teiler = Math.pow(10, pr.currency_minor_unit ?? 2);
		const min = pr.price_range ? pr.price_range.min_amount : pr.price;
		if (!min || Number(min) === 0) return 'Preis auf Anfrage';
		const betrag = (Number(min) / teiler).toLocaleString('de-DE', { style: 'currency', currency: pr.currency_code || 'EUR' });
		return (pr.price_range ? 'ab ' : '') + betrag + ' zzgl. MwSt.';
	};

	function render() {
		const treffer = produkte.filter((p) => passt(p));
		const schritte = SCHRITTE.map((s, i) => {
			// Nur Werte anbieten, die mit der übrigen Auswahl noch Treffer ergeben.
			const zaehler = {};
			produkte.filter((p) => passt(p, s.merkmal)).forEach((p) =>
				(p._m[s.merkmal] || []).forEach((w) => (zaehler[w] = (zaehler[w] || 0) + 1))
			);
			const werte = Object.keys(zaehler).sort((a, b) => a.localeCompare(b, 'de', { numeric: true }));
			if (!werte.length && !(auswahl[s.merkmal] || []).length) return null;
			const gewaehlt = auswahl[s.merkmal] || [];
			return el('fieldset', { class: 'bf-schritt' + (s.technik ? ' bf-technik' : '') },
				el('legend', {}, el('span', { class: 'bf-nr' }, String(i + 1)), s.frage),
				el('div', { class: 'bf-optionen' }, werte.map((w) =>
					el('button', {
						type: 'button',
						class: 'bf-option' + (gewaehlt.includes(w) ? ' ist-aktiv' : ''),
						'aria-pressed': gewaehlt.includes(w) ? 'true' : 'false',
						onclick: () => {
							const liste = auswahl[s.merkmal] || [];
							auswahl[s.merkmal] = liste.includes(w) ? liste.filter((x) => x !== w) : [...liste, w];
							anzahl = SEITE;
							render();
						},
					}, w, el('span', { class: 'bf-zahl' }, String(zaehler[w])))
				))
			);
		});

		const ergebnis = el('section', { class: 'bf-ergebnis' },
			el('div', { class: 'bf-ergebnis-kopf' },
				el('h2', {}, treffer.length === 1 ? '1 passendes Produkt' : `${treffer.length} passende Produkte`),
				Object.values(auswahl).some((w) => w.length)
					? el('button', { type: 'button', class: 'bf-zuruecksetzen', onclick: () => { Object.keys(auswahl).forEach((k) => delete auswahl[k]); anzahl = SEITE; render(); } }, 'Auswahl zurücksetzen')
					: null
			),
			treffer.length
				? el('div', { class: 'bf-karten' }, treffer.slice(0, anzahl).map((p) =>
					el('a', { class: 'bf-karte', href: p.permalink },
						p.images && p.images[0]
							? el('img', { src: p.images[0].thumbnail || p.images[0].src, alt: '', loading: 'lazy' })
							: el('div', { class: 'bf-ohne-bild' }),
						el('h3', {}, p.name),
						el('p', { class: 'bf-preis' }, preis(p)),
						el('span', { class: 'bf-mehr' }, 'Ansehen')
					)))
				: el('p', {}, 'Mit dieser Kombination haben wir noch nichts im Sortiment. ',
					el('a', { href: '/kontakt/' }, 'Fragen Sie uns nach einer Lösung.')),
			treffer.length > anzahl
				? el('button', { type: 'button', class: 'bf-weitere', onclick: () => { anzahl += SEITE; render(); } },
					`Weitere anzeigen (${treffer.length - anzahl} übrig)`)
				: null
		);

		root.replaceChildren(el('div', { class: 'bf-finder-raster' }, el('div', { class: 'bf-schritte-spalte' }, schritte), ergebnis));
	}

	async function laden() {
		if (cfg.einmal) { // statische Website: eine JSON-Datei mit allen Produkten
			const r = await fetch(cfg.api);
			if (!r.ok) throw new Error('HTTP ' + r.status);
			return r.json();
		}
		const alle = [];
		for (let seite = 1; seite < 50; seite++) {
			const url = cfg.api + (cfg.api.includes('?') ? '&' : '?') + 'per_page=100&page=' + seite;
			const r = await fetch(url, { credentials: 'same-origin' });
			if (!r.ok) throw new Error('HTTP ' + r.status);
			const teil = await r.json();
			alle.push(...teil);
			if (teil.length < 100) break;
		}
		return alle;
	}

	laden()
		.then((liste) => {
			produkte = liste.map((p) => Object.assign(p, { _m: merkmale(p) }));
			Object.entries(cfg.preset || {}).forEach(([k, v]) => { if (v) auswahl[k] = [v]; });
			render();
		})
		.catch(() => {
			root.replaceChildren(el('p', {}, 'Der Produktfinder konnte nicht geladen werden. ', el('a', { href: '/shop/' }, 'Zu allen Produkten')));
		});
})();
