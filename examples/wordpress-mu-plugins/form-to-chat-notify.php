<?php
/**
 * Plugin Name: Form → team chat notification
 * Description: Forwards Contact Form 7 submissions to a Telegram channel the front desk actually reads.
 *              Fails soft: a chat outage never breaks the form. Never logs the token or message body.
 * Version:     1.0.0
 *
 * wp-config.php (never commit): define( 'SITE_CHAT_BOT_TOKEN', '...' ); define( 'SITE_CHAT_ID', '...' );
 */

defined( 'ABSPATH' ) || exit;

// mail_sent and mail_failed are mutually exclusive per submission: no double send.
add_action( 'wpcf7_mail_sent', 'site_form_chat_notify' );
add_action( 'wpcf7_mail_failed', 'site_form_chat_notify' );

function site_form_chat_notify( $contact_form ) {
	$token = defined( 'SITE_CHAT_BOT_TOKEN' ) ? (string) SITE_CHAT_BOT_TOKEN : '';
	$chat  = defined( 'SITE_CHAT_ID' ) ? (string) SITE_CHAT_ID : '';
	if ( '' === $token || '' === $chat || ! class_exists( 'WPCF7_Submission' ) ) {
		return;
	}
	$submission = WPCF7_Submission::get_instance();
	$data       = $submission ? $submission->get_posted_data() : null;
	if ( ! is_array( $data ) ) {
		return;
	}

	$field = static function ( $key, $cb = 'sanitize_text_field' ) use ( $data ) {
		return isset( $data[ $key ] ) ? call_user_func( $cb, (string) $data[ $key ] ) : '';
	};
	$tz    = wp_timezone();
	$lines = array(
		'New enquiry',
		'',
		'Name: ' . ( $field( 'your-name' ) ?: '—' ),
		'Phone: ' . ( $field( 'your-phone' ) ?: '—' ),
		'Email: ' . ( $field( 'your-email', 'sanitize_email' ) ?: '—' ),
		'Message: ' . ( $field( 'your-message', 'sanitize_textarea_field' ) ?: '—' ),
		'',
		'Form: ' . ( method_exists( $contact_form, 'title' ) ? $contact_form->title() : 'CF7' ),
		'Time: ' . ( new DateTime( 'now', $tz ) )->format( 'd.m.Y H:i' ) . ' (' . $tz->getName() . ')',
	);

	$response = wp_remote_post(
		'https://api.telegram.org/bot' . $token . '/sendMessage',
		array(
			'timeout' => 8,
			'body'    => array(
				'chat_id'                  => $chat,
				'text'                     => implode( "\n", $lines ),
				'disable_web_page_preview' => true,
			),
		)
	);

	if ( is_wp_error( $response ) ) {
		error_log( 'Form→chat: request failed' );
		return;
	}
	$code = (int) wp_remote_retrieve_response_code( $response );
	if ( $code < 200 || $code >= 300 ) {
		error_log( 'Form→chat: HTTP ' . $code ); // status only, never the body or token
	}
}
