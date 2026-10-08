<?php
/**
 * Einrichtung: Produktwelten (Kategorien), Finder-Merkmale (globale Attribute) und Seiten.
 * Läuft beim Aktivieren des Plugins und ist wiederholbar, bestehende Einträge bleiben unverändert.
 *
 * @package beinundfuss
 */

defined( 'ABSPATH' ) || exit;

/**
 * Produktwelten aus dem Konzept. Der Importer ordnet Produkte über den Namen zu,
 * die Slugs legen wir hier fest, damit die Links im Theme stimmen.
 */
function bf_shop_produktwelten(): array {
	return array(
		'einschlagfuesse'             => array( 'Einschlagfüße', 'Für Vierkant- und Rundrohre: einschlagen, ausrichten, fertig.', array(
			'vierkantrohr' => 'Vierkantrohr',
			'rundrohr'     => 'Rundrohr',
		) ),
		'edelstahl-stellbeine'        => array( 'Edelstahl-Stellbeine', 'Höhenverstellbare Beine für Gastronomie, Großküche und Möbelbau.', array(
			'geraetebeine' => 'Gerätebeine',
		) ),
		'maschinenfuesse'             => array( 'Maschinenfüße', 'Gewindespindel und Fußteller zum exakten Ausrichten von Maschinen.', array() ),
		'gelenkfuesse'                => array( 'Gelenkfüße', 'Neigbarer Teller für unebene oder geneigte Böden.', array() ),
		'fuesse-mit-bodenbefestigung' => array( 'Füße mit Bodenbefestigung', 'Teller mit Befestigungslöchern gegen Verschieben, Vibration und Kippen.', array() ),
		'schwingungsdaempfer'         => array( 'Schwingungsdämpfer', 'Metall und Elastomer zum Entkoppeln von Aggregaten und Klimageräten.', array() ),
		'hygienefuesse'               => array( 'Hygienefüße', 'Edelstahlfüße für Lebensmittel-, Getränke- und Pharmaanlagen.', array() ),
		'schwerlastfuesse'            => array( 'Schwerlastfüße', 'Große Teller und kräftige Spindeln für schwere Anlagen.', array() ),
		'rollen-sonderloesungen'      => array( 'Rollen & Sonderlösungen', 'Rollen, Kombinationen aus Rolle und Fuß und Sonderanfertigungen.', array() ),
		'zubehoer'                    => array( 'Zubehör', 'Montageplatten und Ergänzungen.', array() ),
	);
}

/** Globale Merkmale, nach denen der Produktfinder filtert. */
function bf_shop_merkmale(): array {
	return array( 'Anwendung', 'Funktion', 'Bauform', 'Material', 'Rohrmaß', 'Gewinde', 'Fußform', 'Anschluss', 'Bodenbefestigung' );
}

function bf_shop_aktivieren(): void {
	if ( ! function_exists( 'wc_create_attribute' ) ) {
		return;
	}

	foreach ( bf_shop_produktwelten() as $slug => list( $name, $beschreibung, $unter ) ) {
		$term = term_exists( $slug, 'product_cat' );
		if ( ! $term ) {
			$term = wp_insert_term( $name, 'product_cat', array( 'slug' => $slug, 'description' => $beschreibung ) );
		}
		if ( is_wp_error( $term ) ) {
			continue;
		}
		foreach ( $unter as $unter_slug => $unter_name ) {
			if ( ! term_exists( $unter_slug, 'product_cat' ) ) {
				wp_insert_term( $unter_name, 'product_cat', array( 'slug' => $unter_slug, 'parent' => (int) $term['term_id'] ) );
			}
		}
	}

	foreach ( bf_shop_merkmale() as $name ) {
		if ( ! wc_attribute_taxonomy_id_by_name( $name ) ) {
			wc_create_attribute( array( 'name' => $name, 'type' => 'select', 'has_archives' => false ) );
		}
	}

	if ( ! get_page_by_path( 'produktfinder' ) ) {
		wp_insert_post( array(
			'post_type'    => 'page',
			'post_status'  => 'publish',
			'post_title'   => 'Produktfinder',
			'post_name'    => 'produktfinder',
			'post_content' => '<!-- wp:shortcode -->[bf_produktfinder]<!-- /wp:shortcode -->',
		) );
	}
}
