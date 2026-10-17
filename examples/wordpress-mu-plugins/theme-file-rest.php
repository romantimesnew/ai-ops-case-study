<?php
/**
 * Plugin Name: Child-theme file access over REST (preview first)
 * Description: Lets the executor agent read and write child-theme files through the WordPress REST API
 *              with an application password, when the hosting's file channel (FTP/FTPS) is unreliable.
 *              Built after no ready-made plugin fitted and the cost of an own solution was estimated first.
 * Version:     0.3.0
 *
 * Guards: admin capability required; paths are resolved with realpath() and must stay inside the child
 * theme; only listed extensions; no deletes; the agent backs up the file and compares hashes before a PUT.
 * Endpoints:
 *   GET  /wp-json/site-ops/v1/theme-files            list files
 *   GET  /wp-json/site-ops/v1/theme-file?path=...    read one file
 *   PUT  /wp-json/site-ops/v1/theme-file             {path, content} write one file
 */

defined( 'ABSPATH' ) || exit;

function site_ops_theme_root() {
	return realpath( get_stylesheet_directory() );
}

function site_ops_resolve( $relative, $must_exist = true ) {
	$relative = ltrim( str_replace( '\\', '/', (string) $relative ), '/' );
	$ext_ok   = (bool) preg_match( '/\.(php|css|js|json|txt)$/i', $relative );
	if ( '' === $relative || false !== strpos( $relative, '..' ) || ! $ext_ok ) {
		return new WP_Error( 'bad_path', 'Path is not allowed.', array( 'status' => 400 ) );
	}
	$root = site_ops_theme_root();
	$full = $must_exist ? realpath( $root . '/' . $relative ) : realpath( dirname( $root . '/' . $relative ) );
	if ( false === $full || 0 !== strpos( $full, $root ) ) {
		return new WP_Error( 'bad_path', 'Path is not allowed.', array( 'status' => 400 ) );
	}
	return $must_exist ? $full : $full . '/' . basename( $relative );
}

add_action( 'rest_api_init', static function () {
	$can = static function () {
		return current_user_can( 'edit_themes' );
	};

	register_rest_route( 'site-ops/v1', '/theme-files', array(
		'methods'             => 'GET',
		'permission_callback' => $can,
		'callback'            => static function () {
			$root  = site_ops_theme_root();
			$files = array();
			$it    = new RecursiveIteratorIterator( new RecursiveDirectoryIterator( $root, FilesystemIterator::SKIP_DOTS ) );
			foreach ( $it as $f ) {
				if ( $f->isFile() ) {
					$files[] = ltrim( substr( $f->getPathname(), strlen( $root ) ), '/' );
				}
			}
			sort( $files );
			return array( 'files' => $files );
		},
	) );

	register_rest_route( 'site-ops/v1', '/theme-file', array(
		array(
			'methods'             => 'GET',
			'permission_callback' => $can,
			'callback'            => static function ( WP_REST_Request $r ) {
				$full = site_ops_resolve( $r->get_param( 'path' ) );
				if ( is_wp_error( $full ) ) {
					return $full;
				}
				$body = (string) file_get_contents( $full );
				return array( 'content' => $body, 'sha256' => hash( 'sha256', $body ), 'size' => strlen( $body ) );
			},
		),
		array(
			'methods'             => 'PUT',
			'permission_callback' => $can,
			'callback'            => static function ( WP_REST_Request $r ) {
				$full = site_ops_resolve( $r->get_param( 'path' ), false );
				if ( is_wp_error( $full ) ) {
					return $full;
				}
				$body = (string) $r->get_param( 'content' );
				if ( false === file_put_contents( $full, $body, LOCK_EX ) ) {
					return new WP_Error( 'write_failed', 'Could not write file.', array( 'status' => 500 ) );
				}
				return array( 'ok' => true, 'size' => strlen( $body ), 'sha256' => hash( 'sha256', $body ) );
			},
		),
	) );
} );
