<?php
/**
 * Plugin Name: Preview copy guard
 * Description: For a pre-production copy ONLY. Forces noindex/nofollow everywhere, serves a Disallow-all
 *              robots.txt, disables sitemaps, blocks all outgoing mail (wp_mail + Contact Form 7) and any
 *              HTTP request to the team-chat notification API. Contains no secrets.
 * Version:     1.1.0
 */

defined( 'ABSPATH' ) || exit;

/* 1. No indexing */
add_filter( 'pre_option_blog_public', static function () {
	return '0';
}, 999 );

add_filter( 'wp_headers', static function ( $headers ) {
	$headers['X-Robots-Tag'] = 'noindex, nofollow';
	return $headers;
}, 999 );

foreach ( array( 'send_headers', 'admin_init', 'login_init', 'rest_api_init' ) as $hook ) {
	add_action( $hook, static function () {
		if ( ! headers_sent() ) {
			header( 'X-Robots-Tag: noindex, nofollow', true );
		}
	}, 1 );
}
unset( $hook );

// Runs after any SEO plugin that sets "index" on the front page.
add_filter( 'wp_robots', static function ( $robots ) {
	unset( $robots['index'], $robots['follow'], $robots['max-image-preview'] );
	$robots['noindex']  = true;
	$robots['nofollow'] = true;
	return $robots;
}, 9999 );

add_filter( 'robots_txt', static function () {
	return "User-agent: *\nDisallow: /\n";
}, 9999 );

add_filter( 'wp_sitemaps_enabled', '__return_false', 999 );

/* 2. No outgoing mail */
add_filter( 'pre_wp_mail', static function () {
	return false;
}, 9999 );

// NOTE: CF7 treats skipped mail as success and still fires wpcf7mailsent in the browser.
add_filter( 'wpcf7_skip_mail', '__return_true', 9999 );

add_action( 'phpmailer_init', static function ( $phpmailer ) {
	$phpmailer->clearAllRecipients();   // belt and braces: no recipients, no send
	$phpmailer->clearReplyTos();
}, 9999 );

/* 3. No team-chat notifications */
add_filter( 'pre_http_request', static function ( $pre, $args, $url ) {
	$host = strtolower( (string) wp_parse_url( (string) $url, PHP_URL_HOST ) );
	if ( preg_match( '/(^|\.)(telegram\.org|t\.me)$/', $host ) ) {
		return new WP_Error( 'preview_blocked', 'Notifications are disabled on the preview copy.' );
	}
	return $pre;
}, 1, 3 );
