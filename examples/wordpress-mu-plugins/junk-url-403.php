<?php
/**
 * Plugin Name: Junk URL 403
 * Description: GET/HEAD requests whose path or query contains a spam pattern (also URL-encoded or
 *              double-encoded) get 403 before WordPress builds the page. POST, admin and REST are never
 *              filtered, and normal tracking links (utm_*, gclid, fbclid) are unaffected.
 *              Rollback: delete this file.
 * Version:     1.0.0
 */

defined( 'ABSPATH' ) || exit;

( static function () {
	$patterns = array( 'shop/items' ); // spam pattern observed in search results; extend as needed

	$method = isset( $_SERVER['REQUEST_METHOD'] ) ? strtoupper( (string) $_SERVER['REQUEST_METHOD'] ) : '';
	if ( 'GET' !== $method && 'HEAD' !== $method ) {
		return;
	}
	$uri = isset( $_SERVER['REQUEST_URI'] ) ? (string) $_SERVER['REQUEST_URI'] : '';
	if ( '' === $uri ) {
		return;
	}
	$path = strtolower( (string) parse_url( $uri, PHP_URL_PATH ) );
	if ( 0 === strpos( $path, '/wp-admin' ) || 0 === strpos( $path, '/wp-json' ) ) {
		return;
	}

	$matches = static function ( $s ) use ( $patterns ) {
		foreach ( $patterns as $p ) {
			if ( false !== strpos( $s, $p ) || false !== strpos( $s, str_replace( '/', '%2f', $p ) ) ) {
				return true;
			}
		}
		return false;
	};

	$check = strtolower( $uri );
	$found = $matches( $check );
	for ( $i = 0; ! $found && $i < 3; $i++ ) {   // catch double-encoded variants
		$decoded = strtolower( rawurldecode( str_replace( '+', ' ', $check ) ) );
		if ( $decoded === $check ) {
			break;
		}
		$check = $decoded;
		$found = $matches( $check );
	}
	if ( ! $found ) {
		return;
	}

	if ( ! headers_sent() ) {
		http_response_code( 403 );
		header( 'Content-Type: text/plain; charset=UTF-8' );
		header( 'X-Robots-Tag: noindex, nofollow' );
		header( 'Cache-Control: no-store, max-age=0' );
	}
	if ( 'HEAD' !== $method ) {
		echo 'Forbidden';
	}
	exit;
} )();
