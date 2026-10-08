<?php
/**
 * Title: Startseite – Vorteile
 * Slug: beinundfuss/vorteile
 * Categories: beinundfuss
 * Inserter: no
 */

$vorteile = array(
	array( 'Schnell zum passenden Produkt', '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>' ),
	array( 'Für jede Anwendung', '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1 7 17M17 7l2.1-2.1"/>' ),
	array( 'Bewährte Qualität', '<path d="m12 3 2.6 5.6 6.1.7-4.5 4.2 1.2 6L12 16.6 6.6 19.5l1.2-6-4.5-4.2 6.1-.7z"/>' ),
	array( 'Direkt verfügbar', '<path d="M2 7h11v9H2zM13 10h4l3 3v3h-7"/><circle cx="6" cy="17.5" r="1.5"/><circle cx="17" cy="17.5" r="1.5"/>' ),
	array( 'Persönliche Beratung', '<path d="M4 14v-2a8 8 0 0 1 16 0v2"/><rect x="2" y="14" width="4" height="6" rx="1"/><rect x="18" y="14" width="4" height="6" rx="1"/>' ),
);
?>
<!-- wp:group {"align":"full","className":"bf-band","style":{"spacing":{"padding":{"top":"28px","bottom":"28px"}}},"layout":{"type":"constrained"}} -->
<div class="wp-block-group alignfull bf-band" style="padding-top:28px;padding-bottom:28px">
<!-- wp:group {"align":"wide","layout":{"type":"grid","minimumColumnWidth":"200px"}} -->
<div class="wp-block-group alignwide">
<?php foreach ( $vorteile as $v ) : ?>
<!-- wp:html -->
<div class="bf-band-item"><svg viewBox="0 0 24 24" aria-hidden="true"><?php echo $v[1]; // phpcs:ignore WordPress.Security.EscapeOutput -- statisches SVG ?></svg><span><?php echo esc_html( $v[0] ); ?></span></div>
<!-- /wp:html -->
<?php endforeach; ?>
</div>
<!-- /wp:group -->
</div>
<!-- /wp:group -->
