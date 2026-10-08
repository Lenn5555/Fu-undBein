<?php
/**
 * Kompakter Produktkatalog für den KI-Berater.
 *
 * @package beinundfuss
 */

defined( 'ABSPATH' ) || exit;

/**
 * Alle veröffentlichten Produkte als schlanke Arrays. 10 Minuten zwischengespeichert,
 * beim Speichern eines Produkts geleert.
 */
function bf_katalog(): array {
	$katalog = get_transient( 'bf_katalog' );
	if ( is_array( $katalog ) ) {
		return $katalog;
	}

	$katalog = array();
	foreach ( wc_get_products( array( 'status' => 'publish', 'limit' => -1 ) ) as $p ) {
		$merkmale = array();
		foreach ( $p->get_attributes() as $attr ) {
			$name              = wc_attribute_label( $attr->get_name() );
			$merkmale[ $name ] = $attr->is_taxonomy()
				? wc_get_product_terms( $p->get_id(), $attr->get_name(), array( 'fields' => 'names' ) )
				: $attr->get_options();
		}
		$preis     = $p->get_price();
		$katalog[] = array(
			'id'        => $p->get_id(),
			'sku'       => $p->get_sku(),
			'name'      => $p->get_name(),
			'url'       => get_permalink( $p->get_id() ),
			'kategorie' => wp_strip_all_tags( wc_get_product_category_list( $p->get_id(), ', ' ) ),
			'kurz'      => wp_strip_all_tags( $p->get_short_description() ),
			'preis'     => '' === $preis ? 'Preis auf Anfrage' : ( $p->is_type( 'variable' ) ? 'ab ' : '' ) . number_format( (float) $preis, 2, ',', '.' ) . ' € netto',
			'bild'      => wp_get_attachment_image_url( $p->get_image_id(), 'woocommerce_thumbnail' ) ?: '',
			'merkmale'  => $merkmale,
		);
	}
	set_transient( 'bf_katalog', $katalog, 10 * MINUTE_IN_SECONDS );
	return $katalog;
}

add_action( 'woocommerce_update_product', static fn() => delete_transient( 'bf_katalog' ) );
add_action( 'woocommerce_new_product', static fn() => delete_transient( 'bf_katalog' ) );

/**
 * Einfache Suche: jedes Suchwort zählt einen Treffer, wenn es in Name, Text oder Merkmalen vorkommt.
 * Filter (z. B. Rohrmaß) müssen exakt passen.
 */
function bf_katalog_suchen( string $suchtext, array $filter = array(), int $max = 8 ): array {
	$woerter  = array_filter( preg_split( '/[\s,;]+/u', mb_strtolower( $suchtext ) ) );
	$treffer  = array();
	foreach ( bf_katalog() as $p ) {
		foreach ( $filter as $merkmal => $wert ) {
			if ( '' === $wert ) {
				continue;
			}
			$werte = array_map( 'mb_strtolower', (array) ( $p['merkmale'][ $merkmal ] ?? array() ) );
			if ( ! in_array( mb_strtolower( $wert ), $werte, true ) ) {
				continue 2;
			}
		}
		$heu   = mb_strtolower( $p['name'] . ' ' . $p['kurz'] . ' ' . $p['kategorie'] . ' ' . wp_json_encode( $p['merkmale'], JSON_UNESCAPED_UNICODE ) );
		$score = 0;
		foreach ( $woerter as $w ) {
			if ( str_contains( $heu, $w ) ) {
				++$score;
			}
		}
		if ( $score > 0 || ! $woerter ) {
			$treffer[] = array( $score, $p );
		}
	}
	usort( $treffer, static fn( $a, $b ) => $b[0] <=> $a[0] );
	return array_map( static fn( $t ) => $t[1], array_slice( $treffer, 0, $max ) );
}
