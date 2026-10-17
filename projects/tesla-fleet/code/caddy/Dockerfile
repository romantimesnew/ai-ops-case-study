# Caddy + caddy-l4 (layer4 SNI passthrough so fleet-telemetry can share :443)
FROM caddy:2-builder AS builder
RUN xcaddy build --with github.com/mholt/caddy-l4
FROM caddy:2
COPY --from=builder /usr/bin/caddy /usr/bin/caddy
