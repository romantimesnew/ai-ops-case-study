<?php
/**
 * Plugin Name: Legacy URL 301 redirects
 * Description: Permanent redirects for old URLs that still get search clicks (list taken from Search
 *              Console by the ads & analytics agent). Runs when mu-plugins load, before WordPress routing,
 *              so canonical-redirect guessing never sees these paths.
 * Version:     1.0.0
 *
 * Why a mu-plugin and not .htaccess: on shared hosting .htaccess also holds WordPress's own rules, and a
 * typo there returns 500 for the whole site. This is one file, rolled back by deleting it, and it builds
 * targets from home_url(), so the same file is safe on the preview copy and on production.
 */

defined( 'ABSPATH' ) || exit;

( static function () {
	$method = isset( $_SERVER['REQUEST_METHOD'] ) ? strtoupper( (string) $_SERVER['REQUEST_METHOD'] ) : 'GET';
	if ( ! in_array( $method, array( 'GET', 'HEAD' ), true ) || ! isset( $_SERVER['REQUEST_URI'] ) ) {
		return;
	}

	// Old path (no trailing slash) => new path. Exact, case-sensitive match. Example values only.
	$map = array(
		'/old-staff-profile' => '/team/specialist/',
		'/en'                => '/',
		'/old-service-page'  => '/services/service-name/',
	);

	$uri   = (string) $_SERVER['REQUEST_URI'];
	$path  = (string) parse_url( $uri, PHP_URL_PATH );
	$query = (string) parse_url( $uri, PHP_URL_QUERY );
	$key   = '/' === $path ? '/' : rtrim( $path, '/' );   // trailing slash doesn't matter

	if ( ! isset( $map[ $key ] ) ) {
		return;
	}
	$target = home_url( $map[ $key ] ) . ( '' !== $query ? '?' . $query : '' );   // keep UTM / click IDs
	header( 'Cache-Control: max-age=3600' );
	header( 'Location: ' . $target, true, 301 );
	exit;
} )();
