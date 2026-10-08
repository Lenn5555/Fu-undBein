<?php
/**
 * Produktfinder: Shortcode [bf_produktfinder].
 *
 * Die Filterlogik läuft im Browser (assets/finder.js) über die WooCommerce Store API,
 * damit neue Produkte und Merkmale ohne Codeänderung im Finder auftauchen.
 *
 * @package beinundfuss
 */

defined( 'ABSPATH' ) || exit;

add_shortcode(
	'bf_produktfinder',
	static function () {
		wp_enqueue_style( 'bf-finder', BF_SHOP_URL . 'assets/finder.css', array(), BF_SHOP_VERSION );
		wp_enqueue_script( 'bf-finder', BF_SHOP_URL . 'assets/finder.js', array(), BF_SHOP_VERSION, true );
		wp_localize_script(
			'bf-finder',
			'bfFinder',
			array(
				'api'    => esc_url_raw( rest_url( 'wc/store/v1/products' ) ),
				'preset' => array(
					'Anwendung' => isset( $_GET['anwendung'] ) ? sanitize_text_field( wp_unslash( $_GET['anwendung'] ) ) : '', // phpcs:ignore WordPress.Security.NonceVerification
				),
			)
		);
		return '<div id="bf-finder" class="bf-finder" aria-live="polite"><p>Produktfinder wird geladen…</p></div>';
	}
);
