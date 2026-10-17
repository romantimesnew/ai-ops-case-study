<?php
/**
 * Plugin Name: Lead events for GA4 + Google Ads
 * Description: Site-side lead measurement. A successful Contact Form 7 send fires GA4 `generate_lead`
 *              plus the Ads lead conversion (primary). A `tel:` click fires GA4 `phone_click` plus the
 *              Ads phone conversion (secondary). Messenger links fire GA4 `messenger_click`.
 *              Event parameters carry only placement info (form_location, link_location, messenger),
 *              never form field values.
 * Version:     1.1.0
 *
 * Requires the base gtag loader from ads-conversion-tag.php (one loader per page).
 *
 * Define in wp-config.php (placeholders, never commit real values to a public repo):
 *   define( 'SITE_ADS_TAG_ID', '...' );           // Google Ads tag ID
 *   define( 'SITE_ADS_LEAD_LABEL', '...' );       // label of the primary "form lead" action
 *   define( 'SITE_ADS_PHONE_LABEL', '...' );      // label of the secondary "phone click" action
 *
 * GA4 side (done by the ads & analytics agent via the Admin API, not by this file):
 *   event-scoped custom dimensions form_location, link_location, messenger;
 *   generate_lead and phone_click marked as key events.
 */

defined( 'ABSPATH' ) || exit;

add_action( 'wp_footer', static function () {
	if ( is_admin() || ! defined( 'SITE_ADS_TAG_ID' ) ) {
		return;
	}
	$ads   = (string) SITE_ADS_TAG_ID;
	$lead  = defined( 'SITE_ADS_LEAD_LABEL' ) ? $ads . '/' . SITE_ADS_LEAD_LABEL : '';
	$phone = defined( 'SITE_ADS_PHONE_LABEL' ) ? $ads . '/' . SITE_ADS_PHONE_LABEL : '';
	?>
	<script>
	(function () {
	  if (window.siteLeadEventsHooked) { return; }   // never bind twice
	  window.siteLeadEventsHooked = true;
	  var LEAD = '<?php echo esc_js( $lead ); ?>', PHONE = '<?php echo esc_js( $phone ); ?>';
	  function g() { if (typeof gtag === 'function') { gtag.apply(null, arguments); } }

	  // Placement of a link, by page section. Adjust selectors per theme.
	  function where(el) {
	    var map = [['header', 'header'], ['#hero', 'hero'], ['#contacts', 'contacts'], ['footer', 'footer']];
	    for (var i = 0; i < map.length; i++) { if (el.closest(map[i][0])) { return map[i][1]; } }
	    return 'other';
	  }

	  // 1. Lead: only on a successful send (not on validation errors or spam).
	  document.addEventListener('wpcf7mailsent', function (e) {
	    var form = e.target && e.target.closest ? e.target.closest('.wpcf7') : null;
	    g('event', 'generate_lead', { form_location: form ? where(form) : 'other' });
	    if (LEAD) { g('event', 'conversion', { send_to: LEAD }); }
	  }, false);

	  // 2-3. Delegated clicks; beacon transport so the hit survives leaving the page.
	  document.addEventListener('click', function (e) {
	    var a = e.target && e.target.closest ? e.target.closest('a[href]') : null;
	    if (!a) { return; }
	    var href = a.getAttribute('href') || '';
	    if (/^tel:/i.test(href)) {
	      g('event', 'phone_click', { link_location: where(a), transport_type: 'beacon' });
	      if (PHONE) { g('event', 'conversion', { send_to: PHONE, transport_type: 'beacon' }); }
	      return;
	    }
	    var m = /instagram\.com/i.test(href) ? 'instagram'
	          : /(^|\/\/)t\.me\//i.test(href) ? 'telegram'
	          : /^viber:/i.test(href) ? 'viber'
	          : /wa\.me|whatsapp/i.test(href) ? 'whatsapp' : '';
	    if (m) { g('event', 'messenger_click', { messenger: m, link_location: where(a), transport_type: 'beacon' }); }
	  }, true);
	})();
	</script>
	<?php
}, 20 );
