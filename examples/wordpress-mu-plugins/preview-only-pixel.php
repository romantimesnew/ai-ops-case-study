<?php
/**
 * Plugin Name: Meta Pixel (preview copy only)
 * Description: PageView on all front-end pages and Lead on Contact Form 7's successful-send event.
 *              Hard guard: outputs nothing unless home_url() host equals SITE_PREVIEW_HOST,
 *              so an accidental copy to production is inert.
 * Version:     1.0.0
 *
 * wp-config.php:
 *   define( 'SITE_PREVIEW_HOST', 'preview.example.org' );
 *   define( 'SITE_META_PIXEL_ID', '...' );
 *
 * Pitfall found in testing: when outgoing mail is suppressed on a preview copy, Contact Form 7 still
 * reports "mail_sent" and the browser still fires wpcf7mailsent, so a test submission here WOULD send a
 * real Lead to Meta. Don't submit test leads on the preview copy, or use Events Manager test mode.
 */

defined( 'ABSPATH' ) || exit;

function site_preview_pixel_enabled() {
	if ( ! defined( 'SITE_PREVIEW_HOST' ) || ! defined( 'SITE_META_PIXEL_ID' ) ) {
		return false;
	}
	$host = strtolower( (string) wp_parse_url( home_url(), PHP_URL_HOST ) );
	if ( strtolower( (string) SITE_PREVIEW_HOST ) !== $host ) {
		return false;
	}
	if ( is_admin() || wp_doing_ajax() || wp_doing_cron() || is_feed() || is_embed() ) {
		return false;
	}
	if ( defined( 'REST_REQUEST' ) && REST_REQUEST ) {
		return false;
	}
	return true;
}

add_action( 'wp_head', static function () {
	if ( ! site_preview_pixel_enabled() ) {
		return;
	}
	$id = (string) SITE_META_PIXEL_ID;
	?>
<script>
!function(f,b,e,v,n,t,s){if(f.fbq)return;n=f.fbq=function(){n.callMethod?
n.callMethod.apply(n,arguments):n.queue.push(arguments)};if(!f._fbq)f._fbq=n;
n.push=n;n.loaded=!0;n.version='2.0';n.queue=[];t=b.createElement(e);t.async=!0;
t.src=v;s=b.getElementsByTagName(e)[0];s.parentNode.insertBefore(t,s)}(window,
document,'script','https://connect.facebook.net/en_US/fbevents.js');
fbq('init', '<?php echo esc_js( $id ); ?>');
fbq('track', 'PageView');
</script>
<noscript><img height="1" width="1" style="display:none" alt=""
src="https://www.facebook.com/tr?id=<?php echo rawurlencode( $id ); ?>&amp;ev=PageView&amp;noscript=1"/></noscript>
	<?php
}, 6 );

add_action( 'wp_footer', static function () {
	if ( ! site_preview_pixel_enabled() ) {
		return;
	}
	?>
<script>
(function () {
  if (window.siteMetaLeadHooked) { return; }   // guard against double subscription
  window.siteMetaLeadHooked = true;
  document.addEventListener('wpcf7mailsent', function () {
    if (typeof fbq === 'function') { fbq('track', 'Lead'); }
  }, false);
  // wpcf7mailfailed / wpcf7invalid / wpcf7spam / wpcf7submit intentionally send nothing.
})();
</script>
	<?php
}, 20 );
