<?php
/**
 * Title: Startseite – Anwendungen
 * Slug: beinundfuss/anwendungen
 * Categories: beinundfuss
 * Inserter: no
 */

$anwendungen = array(
	array( 'Gastronomie – Arbeitstische', 'Gastronomiegerät' ),
	array( 'Spültechnik / Edelstahlmöbel', 'Gastronomiegerät' ),
	array( 'Produktionsmaschinen', 'Maschine / Anlage' ),
	array( 'CNC- und Werkzeugmaschinen', 'Maschine / Anlage' ),
	array( 'Fördertechnik', 'Fördertechnik' ),
	array( 'Verpackungsmaschinen', 'Maschine / Anlage' ),
	array( 'Lebensmittel-Verarbeitung', 'Maschine / Anlage' ),
	array( 'Pharma- und Laboranlagen', 'Maschine / Anlage' ),
	array( 'Schaltschränke / Gehäuse', 'Schaltschrank / Gehäuse' ),
	array( 'Werkbänke und Gestelle', 'Arbeitstisch / Möbel' ),
	array( 'Regale / Betriebseinrichtungen', 'Regal / Gestell' ),
	array( 'Möbel / Küchen / Ladenbau', 'Arbeitstisch / Möbel' ),
	array( 'Klima-, Lüftungs- und Kältetechnik', 'Klima- / Lüftungsgerät' ),
	array( 'Kompressoren / Pumpen / Aggregate', 'Maschine / Anlage' ),
	array( 'Schwere Anlagen', 'Maschine / Anlage' ),
);
?>
<!-- wp:group {"align":"wide","anchor":"anwendungen","style":{"spacing":{"padding":{"top":"48px","bottom":"32px"}}},"layout":{"type":"default"}} -->
<div id="anwendungen" class="wp-block-group alignwide" style="padding-top:48px;padding-bottom:32px">
<!-- wp:heading {"textAlign":"center"} -->
<h2 class="wp-block-heading has-text-align-center">Stabile Lösungen für jede Anwendung</h2>
<!-- /wp:heading -->
<!-- wp:group {"layout":{"type":"grid","minimumColumnWidth":"220px"}} -->
<div class="wp-block-group">
<?php foreach ( $anwendungen as $i => $a ) : ?>
<!-- wp:html -->
<div class="bf-kachel"><a href="<?php echo esc_url( add_query_arg( 'anwendung', rawurlencode( $a[1] ), home_url( '/produktfinder/' ) ) ); ?>"><h3><span class="bf-nummer"><?php echo (int) $i + 1; ?></span><?php echo esc_html( $a[0] ); ?></h3><img loading="lazy" src="<?php echo esc_url( get_theme_file_uri( sprintf( 'assets/anwendungen/anwendung-%02d.jpg', $i + 1 ) ) ); ?>" alt="" style="width:100%;height:auto;margin-top:.5rem;border-radius:4px"></a></div>
<!-- /wp:html -->
<?php endforeach; ?>
</div>
<!-- /wp:group -->
</div>
<!-- /wp:group -->
