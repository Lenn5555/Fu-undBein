<?php
/**
 * „Preis auf Anfrage“: Produkte ohne Preis zeigen statt Warenkorb einen Anfrage-Link.
 *
 * Die E-Mail-Adresse kommt aus der Option bf_anfrage_email (Fallback: Admin-E-Mail).
 *
 * @package beinundfuss
 */

defined( 'ABSPATH' ) || exit;

function bf_anfrage_email(): string {
	return (string) get_option( 'bf_anfrage_email', get_option( 'admin_email' ) );
}

function bf_anfrage_link( WC_Product $produkt ): string {
	$betreff = sprintf( 'Anfrage: %s (%s)', $produkt->get_name(), $produkt->get_sku() );
	$text    = "Guten Tag,\n\nbitte senden Sie mir ein Angebot für:\n" . $produkt->get_name() . ' – ' . $produkt->get_sku() . "\nMenge: \nGewünschte Ausführung: \n\nFirma: \nAnsprechpartner: \nTelefon: \n";
	return 'mailto:' . rawurlencode( bf_anfrage_email() ) . '?subject=' . rawurlencode( $betreff ) . '&body=' . rawurlencode( $text );
}

add_filter(
	'woocommerce_get_price_html',
	static function ( $html, $produkt ) {
		if ( '' === $produkt->get_price() ) {
			return '<span class="bf-preis-anfrage">Preis auf Anfrage</span>';
		}
		return $html;
	},
	10,
	2
);

add_action(
	'woocommerce_single_product_summary',
	static function () {
		global $product;
		if ( $product instanceof WC_Product && '' === $product->get_price() && ! $product->is_type( 'variable' ) ) {
			printf(
				'<p><a class="button wp-element-button" href="%s">Angebot anfragen</a></p>',
				esc_url( bf_anfrage_link( $product ) )
			);
		}
	},
	31
);
