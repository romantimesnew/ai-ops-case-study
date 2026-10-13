<?php
/**
 * Plugin Name: Ads + GA4 tag with form-success conversion
 * Description: One gtag.js loader for Google Ads and GA4 on all front-end pages, plus an Ads conversion
 *              fired only on Contact Form 7's successful-send event (not on validation errors or spam).
 * Version:     1.0.0
 *
 * Define in wp-config.php (placeholders, never commit real values to a public repo):
 *   define( 'SITE_ADS_TAG_ID', '...' );          // Google Ads tag ID
 *   define( 'SITE_ADS_CONVERSION_LABEL', '...' ); // conversion label
 *   define( 'SITE_GA4_MEASUREMENT_ID', '...' );   // GA4 web stream measurement ID
 */

defined( 'ABSPATH' ) || exit;

function site_tag_ids() {
	return array(
		'ads'   => defined( 'SITE_ADS_TAG_ID' ) ? (string) SITE_ADS_TAG_ID : '',
		'label' => defined( 'SITE_ADS_CONVERSION_LABEL' ) ? (string) SITE_ADS_CONVERSION_LABEL : '',
		'ga4'   => defined( 'SITE_GA4_MEASUREMENT_ID' ) ? (string) SITE_GA4_MEASUREMENT_ID : '',
	);
}

/** Base tag in <head>: ONE loader, two config lines. A second loader would double-count. */
add_action( 'wp_head', static function () {
	if ( is_admin() ) {
		return;
	}
	$ids = site_tag_ids();
	if ( '' === $ids['ads'] ) {
		return;
	}
	?>
	<script async src="https://www.googletagmanager.com/gtag/js?id=<?php echo esc_attr( $ids['ads'] ); ?>"></script>
	<script>
	  window.dataLayer = window.dataLayer || [];
	  function gtag(){dataLayer.push(arguments);}
	  gtag('js', new Date());
	  gtag('config', '<?php echo esc_js( $ids['ads'] ); ?>');
	  <?php if ( '' !== $ids['ga4'] ) : ?>
	  gtag('config', '<?php echo esc_js( $ids['ga4'] ); ?>');
	  <?php endif; ?>
	</script>
	<?php
}, 5 );

/** Conversion only on a successful send. */
add_action( 'wp_footer', static function () {
	if ( is_admin() ) {
		return;
	}
	$ids = site_tag_ids();
	if ( '' === $ids['ads'] || '' === $ids['label'] ) {
		return;
	}
	$send_to = $ids['ads'] . '/' . $ids['label'];
	?>
	<script>
	document.addEventListener('wpcf7mailsent', function () {
	  if (typeof gtag === 'function') {
	    gtag('event', 'conversion', {'send_to': '<?php echo esc_js( $send_to ); ?>'});
	    <?php /* Optional GA4 lead event (proposed by the ads audit; not in the originally shipped version): */ ?>
	    gtag('event', 'generate_lead', {'method': 'contact_form'});
	  }
	}, false);
	</script>
	<?php
}, 20 );
