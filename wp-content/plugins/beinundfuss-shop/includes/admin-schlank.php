<?php
/**
 * Schlanker Admin für Shop-Verwalter: nur Produkte, Bestellungen und Kunden.
 * Gilt für die WooCommerce-Rolle „Shop-Manager“, Administratoren sehen alles.
 *
 * @package beinundfuss
 */

defined( 'ABSPATH' ) || exit;

function bf_ist_schlank(): bool {
	$user = wp_get_current_user();
	return in_array( 'shop_manager', (array) $user->roles, true ) && ! in_array( 'administrator', (array) $user->roles, true );
}

add_action(
	'admin_menu',
	static function () {
		if ( ! bf_ist_schlank() ) {
			return;
		}
		foreach ( array( 'edit.php', 'upload.php', 'edit.php?post_type=page', 'edit-comments.php', 'tools.php', 'themes.php', 'plugins.php', 'options-general.php', 'woocommerce-marketing', 'wc-admin&path=/analytics/overview' ) as $seite ) {
			remove_menu_page( $seite );
		}
	},
	999
);

add_action(
	'admin_init',
	static function () {
		if ( bf_ist_schlank() && 'index.php' === ( $GLOBALS['pagenow'] ?? '' ) ) {
			wp_safe_redirect( admin_url( 'edit.php?post_type=product' ) );
			exit;
		}
	}
);
