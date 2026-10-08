<?php
/**
 * Plugin Name: beinundfuß Shop
 * Description: Produktwelten, Produktfinder, „Preis auf Anfrage“ und KI-Berater für beinundfuß.de.
 * Version: 0.1.0
 * Requires at least: 6.6
 * Requires PHP: 8.1
 * Requires Plugins: woocommerce
 * Text Domain: beinundfuss
 *
 * @package beinundfuss
 */

defined( 'ABSPATH' ) || exit;

define( 'BF_SHOP_VERSION', '0.1.0' );
define( 'BF_SHOP_DIR', plugin_dir_path( __FILE__ ) );
define( 'BF_SHOP_URL', plugin_dir_url( __FILE__ ) );

if ( file_exists( BF_SHOP_DIR . 'vendor/autoload.php' ) ) {
	require_once BF_SHOP_DIR . 'vendor/autoload.php';
}

require_once BF_SHOP_DIR . 'includes/setup.php';
require_once BF_SHOP_DIR . 'includes/anfrage.php';
require_once BF_SHOP_DIR . 'includes/finder.php';
require_once BF_SHOP_DIR . 'includes/katalog.php';
require_once BF_SHOP_DIR . 'includes/ki-helfer.php';
require_once BF_SHOP_DIR . 'includes/admin-schlank.php';

register_activation_hook( __FILE__, 'bf_shop_aktivieren' );
