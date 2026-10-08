<?php
/**
 * KI-Berater: Chatfenster auf allen Seiten, Antworten von Claude über die Anthropic API.
 *
 * Aktivierung: in wp-config.php  define( 'BF_ANTHROPIC_API_KEY', 'sk-ant-…' );
 * Ohne Schlüssel oder ohne installiertes SDK (composer install) bleibt das Chatfenster aus.
 *
 * @package beinundfuss
 */

defined( 'ABSPATH' ) || exit;

const BF_KI_MODELL       = 'claude-opus-5-5';
const BF_KI_MAX_RUNDEN   = 4;
const BF_KI_LIMIT_STUNDE = 30;

function bf_ki_aktiv(): bool {
	return defined( 'BF_ANTHROPIC_API_KEY' ) && BF_ANTHROPIC_API_KEY && class_exists( '\Anthropic\Client' );
}

add_action(
	'wp_enqueue_scripts',
	static function () {
		if ( ! bf_ki_aktiv() ) {
			return;
		}
		wp_enqueue_style( 'bf-ki', BF_SHOP_URL . 'assets/ki-helfer.css', array(), BF_SHOP_VERSION );
		wp_enqueue_script( 'bf-ki', BF_SHOP_URL . 'assets/ki-helfer.js', array(), BF_SHOP_VERSION, true );
		wp_localize_script(
			'bf-ki',
			'bfKi',
			array(
				'api'   => esc_url_raw( rest_url( 'beinundfuss/v1/ki-helfer' ) ),
				'nonce' => wp_create_nonce( 'wp_rest' ),
			)
		);
	}
);

add_action(
	'rest_api_init',
	static function () {
		register_rest_route(
			'beinundfuss/v1',
			'/ki-helfer',
			array(
				'methods'             => 'POST',
				'callback'            => 'bf_ki_antworten',
				'permission_callback' => '__return_true',
				'args'                => array(
					'verlauf' => array( 'type' => 'array', 'required' => true ),
				),
			)
		);
	}
);

function bf_ki_system(): string {
	return <<<TXT
Du bist der Produktberater von beinundfuß.de, einem Shop für Einschlagfüße, Edelstahl-Stellbeine, Maschinenfüße, Gelenkfüße und Rollen für gewerbliche Kunden. Antworte auf Deutsch, freundlich und knapp, in ganzen Sätzen.

So arbeitest du:
- Finde heraus, was der Kunde aufstellen will (Maschine, Tisch, Gastronomiegerät, Regal …), wie schwer es ist, und wie es befestigt wird (Rohrmaß und Wandstärke oder Gewinde). Frage nach, wenn etwas Entscheidendes fehlt, höchstens zwei Fragen auf einmal.
- Suche passende Artikel immer mit dem Werkzeug katalog_suchen. Empfiehl nur Artikel, die das Werkzeug geliefert hat, und nenne sie mit ihrem genauen Namen.
- Nenne Traglasten, Maße und Preise nur so, wie sie im Katalog stehen. Rechne bei Traglasten mit der Last pro Fuß (Gesamtgewicht geteilt durch Anzahl der Füße) und weise auf Sicherheitsreserve hin. Erfinde keine Werte.
- Wenn nichts Passendes im Katalog ist oder es um Sonderanfertigungen, Mengenpreise oder Hygienezulassungen geht, verweise auf eine Anfrage über die Kontaktseite.
- Sprich nur über Themen rund um Füße, Beine, Rollen und den Shop.
TXT;
}

function bf_ki_werkzeuge(): array {
	return array(
		array(
			'name'        => 'katalog_suchen',
			'description' => 'Sucht Produkte im Shop-Katalog von beinundfuß.de. Liefert bis zu 8 Artikel mit Name, Link, Preis und technischen Merkmalen. Filterwerte müssen exakt den Katalogwerten entsprechen, im Zweifel weglassen und stattdessen Suchwörter verwenden.',
			'inputSchema' => array(
				'type'                 => 'object',
				'properties'           => array(
					'suchtext'  => array( 'type' => 'string', 'description' => 'Suchwörter, z. B. "Vierkant 40 Edelstahl" oder "Gelenkfuß M12".' ),
					'anwendung' => array( 'type' => 'string', 'description' => 'Optional: Maschine / Anlage, Arbeitstisch / Möbel, Gastronomiegerät, Fördertechnik, Schaltschrank / Gehäuse, Klima- / Lüftungsgerät, Regal / Gestell.' ),
					'bauform'   => array( 'type' => 'string', 'description' => 'Optional: Einschlagfuß, Stellfuß, Stellbein, Gelenkfuß, Spezialausführung.' ),
				),
				'required'             => array( 'suchtext' ),
				'additionalProperties' => false,
			),
		),
	);
}

function bf_ki_antworten( WP_REST_Request $request ) {
	if ( ! bf_ki_aktiv() ) {
		return new WP_Error( 'bf_ki_aus', 'Der Berater ist gerade nicht verfügbar.', array( 'status' => 503 ) );
	}

	$ip    = isset( $_SERVER['REMOTE_ADDR'] ) ? sanitize_text_field( wp_unslash( $_SERVER['REMOTE_ADDR'] ) ) : '';
	$key   = 'bf_ki_' . md5( $ip );
	$zahl  = (int) get_transient( $key );
	if ( $zahl >= BF_KI_LIMIT_STUNDE ) {
		return new WP_Error( 'bf_ki_limit', 'Zu viele Anfragen. Bitte versuchen Sie es später erneut oder schreiben Sie uns.', array( 'status' => 429 ) );
	}
	set_transient( $key, $zahl + 1, HOUR_IN_SECONDS );

	// Verlauf aus dem Browser: nur Text, höchstens 20 Nachrichten à 2000 Zeichen.
	$nachrichten = array();
	foreach ( array_slice( (array) $request->get_param( 'verlauf' ), -20 ) as $n ) {
		$rolle = ( $n['rolle'] ?? '' ) === 'assistant' ? 'assistant' : 'user';
		$text  = mb_substr( sanitize_textarea_field( (string) ( $n['text'] ?? '' ) ), 0, 2000 );
		if ( '' !== $text ) {
			$nachrichten[] = array( 'role' => $rolle, 'content' => $text );
		}
	}
	if ( ! $nachrichten || 'user' !== end( $nachrichten )['role'] ) {
		return new WP_Error( 'bf_ki_leer', 'Keine Frage erhalten.', array( 'status' => 400 ) );
	}

	$client   = new \Anthropic\Client( apiKey: BF_ANTHROPIC_API_KEY );
	$gefunden = array();

	try {
		for ( $runde = 0; $runde < BF_KI_MAX_RUNDEN; $runde++ ) {
			$antwort = $client->beta->messages->create(
				model: BF_KI_MODELL,
				maxTokens: 4000,
				system: bf_ki_system(),
				messages: $nachrichten,
				tools: bf_ki_werkzeuge(),
				outputConfig: array( 'effort' => 'low' ),
				fallbacks: 'default',
				betas: array( 'server-side-fallback-2026-07-01' ),
			);

			if ( 'refusal' === $antwort->stopReason ) {
				break;
			}
			if ( 'tool_use' !== $antwort->stopReason ) {
				$text = '';
				foreach ( $antwort->content as $block ) {
					if ( 'text' === $block->type ) {
						$text .= $block->text;
					}
				}
				return rest_ensure_response( array(
					'antwort'  => $text,
					'produkte' => bf_ki_erwaehnte_produkte( $text, $gefunden ),
				) );
			}

			$ergebnisse = array();
			foreach ( $antwort->content as $block ) {
				if ( 'tool_use' !== $block->type ) {
					continue;
				}
				$eingabe = (array) $block->input;
				$liste   = 'katalog_suchen' === $block->name
					? bf_katalog_suchen(
						(string) ( $eingabe['suchtext'] ?? '' ),
						array(
							'Anwendung' => (string) ( $eingabe['anwendung'] ?? '' ),
							'Bauform'   => (string) ( $eingabe['bauform'] ?? '' ),
						)
					)
					: array();
				foreach ( $liste as $p ) {
					$gefunden[ $p['id'] ] = $p;
				}
				$ergebnisse[] = array(
					'type'      => 'tool_result',
					'toolUseID' => $block->id,
					'content'   => $liste
						? wp_json_encode( array_map( static fn( $p ) => array_diff_key( $p, array( 'bild' => 1, 'id' => 1 ) ), $liste ), JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES )
						: 'Keine passenden Artikel im Katalog.',
				);
			}
			$nachrichten[] = array( 'role' => 'assistant', 'content' => $antwort->content );
			$nachrichten[] = array( 'role' => 'user', 'content' => $ergebnisse );
		}
	} catch ( \Throwable $e ) {
		error_log( 'beinundfuss KI-Berater: ' . $e->getMessage() ); // phpcs:ignore WordPress.PHP.DevelopmentFunctions
	}

	return rest_ensure_response( array(
		'antwort'  => 'Dazu kann ich gerade keine sichere Antwort geben. Schreiben Sie uns gern über die Kontaktseite, wir helfen persönlich weiter.',
		'produkte' => array(),
	) );
}

/** Produktkarten nur für Artikel, die der Berater in seiner Antwort tatsächlich nennt. */
function bf_ki_erwaehnte_produkte( string $text, array $gefunden ): array {
	$karten = array();
	foreach ( $gefunden as $p ) {
		if ( str_contains( $text, $p['name'] ) || ( $p['sku'] && str_contains( $text, $p['sku'] ) ) ) {
			$karten[] = array_intersect_key( $p, array_flip( array( 'name', 'url', 'preis', 'bild' ) ) );
		}
	}
	return array_slice( $karten, 0, 4 );
}
