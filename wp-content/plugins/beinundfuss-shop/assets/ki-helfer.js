/* beinundfuß KI-Berater – Chatfenster unten rechts. Verlauf nur im Browser (sessionStorage). */
(function () {
	'use strict';

	const cfg = window.bfKi || {};
	if (!cfg.api) return;

	const SPEICHER = 'bf-ki-verlauf';
	let verlauf = [];
	try { verlauf = JSON.parse(sessionStorage.getItem(SPEICHER) || '[]'); } catch (e) { verlauf = []; }
	const speichern = () => { try { sessionStorage.setItem(SPEICHER, JSON.stringify(verlauf.slice(-20))); } catch (e) {} };

	const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text) e.textContent = text; return e; };

	const knopf = el('button', 'bf-ki-knopf', 'Produktberater');
	knopf.type = 'button';
	knopf.setAttribute('aria-expanded', 'false');

	const fenster = el('section', 'bf-ki-fenster');
	fenster.hidden = true;
	fenster.setAttribute('aria-label', 'KI-Produktberater');
	const kopf = el('header', 'bf-ki-kopf');
	kopf.append(el('strong', '', 'Produktberater'), el('span', '', 'KI-gestützt, Angaben bitte prüfen'));
	const zu = el('button', 'bf-ki-zu', '×'); zu.type = 'button'; zu.setAttribute('aria-label', 'Schließen');
	kopf.append(zu);
	const liste = el('div', 'bf-ki-liste'); liste.setAttribute('aria-live', 'polite');
	const form = el('form', 'bf-ki-form');
	const feld = el('textarea'); feld.rows = 2; feld.placeholder = 'z. B. Fuß für 40er Vierkantrohr, Tisch mit 300 kg'; feld.setAttribute('aria-label', 'Ihre Frage');
	const senden = el('button', '', 'Senden'); senden.type = 'submit';
	form.append(feld, senden);
	fenster.append(kopf, liste, form);
	document.body.append(knopf, fenster);

	function blase(rolle, text, produkte) {
		const b = el('div', 'bf-ki-msg bf-ki-' + rolle, text);
		(produkte || []).forEach((p) => {
			const a = el('a', 'bf-ki-produkt'); a.href = p.url;
			if (p.bild) { const i = el('img'); i.src = p.bild; i.alt = ''; a.append(i); }
			const t = el('span'); t.append(el('strong', '', p.name), el('small', '', p.preis)); a.append(t);
			b.append(a);
		});
		liste.append(b);
		liste.scrollTop = liste.scrollHeight;
		return b;
	}

	if (!verlauf.length) {
		blase('assistant', 'Hallo! Was möchten Sie aufstellen oder ausrichten? Beschreiben Sie Gerät, Gewicht und Rohr oder Gewinde, dann suche ich passende Füße.');
	} else {
		verlauf.forEach((n) => blase(n.rolle, n.text, n.produkte));
	}

	const umschalten = (auf) => { fenster.hidden = !auf; knopf.setAttribute('aria-expanded', String(auf)); if (auf) feld.focus(); };
	knopf.addEventListener('click', () => umschalten(fenster.hidden));
	zu.addEventListener('click', () => umschalten(false));
	feld.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); } });

	form.addEventListener('submit', async (e) => {
		e.preventDefault();
		const text = feld.value.trim();
		if (!text) return;
		feld.value = '';
		verlauf.push({ rolle: 'user', text });
		blase('user', text);
		const warte = blase('assistant', 'Einen Moment, ich suche passende Artikel…');
		warte.classList.add('bf-ki-warte');
		senden.disabled = true;
		try {
			const r = await fetch(cfg.api, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json', 'X-WP-Nonce': cfg.nonce },
				body: JSON.stringify({ verlauf: verlauf.map(({ rolle, text }) => ({ rolle, text })) }),
			});
			const d = await r.json();
			warte.remove();
			const antwort = r.ok ? d.antwort : (d.message || 'Das hat leider nicht geklappt.');
			verlauf.push({ rolle: 'assistant', text: antwort, produkte: r.ok ? d.produkte : [] });
			blase('assistant', antwort, r.ok ? d.produkte : []);
		} catch (err) {
			warte.remove();
			blase('assistant', 'Die Verbindung ist fehlgeschlagen. Bitte versuchen Sie es erneut.');
			verlauf.pop();
		}
		speichern();
		senden.disabled = false;
	});
})();
