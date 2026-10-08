<?php
/**
 * Title: Startseite – Produktwelten
 * Slug: beinundfuss/produktwelten
 * Categories: beinundfuss
 * Inserter: no
 */

$welten = array(
	array( 'einschlagfuesse', 'Einschlagfüße', 'Für Vierkant- und Rundrohr, aus Kunststoff, Zamak oder Edelstahl.' ),
	array( 'edelstahl-stellbeine', 'Edelstahl-Stellbeine', 'Höhenverstellbar für Gastronomie, Großküche und Möbelbau.' ),
	array( 'maschinenfuesse', 'Maschinenfüße', 'Gewindespindel und Fußteller zum exakten Ausrichten.' ),
	array( 'gelenkfuesse', 'Gelenkfüße', 'Neigbarer Teller für unebene und schräge Böden.' ),
	array( 'fuesse-mit-bodenbefestigung', 'Bodenbefestigung', 'Teller mit Löchern gegen Verrutschen und Kippen.' ),
	array( 'schwingungsdaempfer', 'Schwingungsdämpfer', 'Entkoppeln Kompressoren, Pumpen und Klimageräte.' ),
	array( 'hygienefuesse', 'Hygienefüße', 'Edelstahl für Lebensmittel, Getränke und Pharma.' ),
	array( 'schwerlastfuesse', 'Schwerlastfüße', 'Große Teller und Spindeln für schwere Anlagen.' ),
);
?>
<!-- wp:group {"align":"wide","style":{"spacing":{"padding":{"top":"32px","bottom":"32px"}}},"layout":{"type":"default"}} -->
<div class="wp-block-group alignwide" style="padding-top:32px;padding-bottom:32px">
<!-- wp:heading {"textAlign":"center"} -->
<h2 class="wp-block-heading has-text-align-center">Unsere Produktwelten</h2>
<!-- /wp:heading -->
<!-- wp:group {"layout":{"type":"grid","minimumColumnWidth":"240px"}} -->
<div class="wp-block-group">
<?php foreach ( $welten as $w ) : ?>
<!-- wp:html -->
<div class="bf-kachel"><a href="<?php echo esc_url( home_url( '/produkt-kategorie/' . $w[0] . '/' ) ); ?>"><h3><?php echo esc_html( $w[1] ); ?></h3><p><?php echo esc_html( $w[2] ); ?></p></a></div>
<!-- /wp:html -->
<?php endforeach; ?>
</div>
<!-- /wp:group -->
</div>
<!-- /wp:group -->
