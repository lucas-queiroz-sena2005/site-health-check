#!/bin/sh

mkdir -p /etc/nginx/templates/

# Strip any literal quotes that podman-compose might have passed from the .env file
ALLOWED_IPS="${ALLOWED_IPS#\"}"
ALLOWED_IPS="${ALLOWED_IPS%\"}"

if [ -z "$ALLOWED_IPS" ]; then
    export ALLOWED_IPS="allow all;"
else
    # Automatically allow the container's gateway IP (Podman/Docker bridge)
    GATEWAY_IP=$(ip route show default | awk '{print $3}')
    if [ -n "$GATEWAY_IP" ]; then
        export ALLOWED_IPS="allow $GATEWAY_IP; $ALLOWED_IPS"
    fi
fi

if [ "$ENABLE_SSL" = "true" ]; then
    echo "SSL enabled. Using HTTPS Nginx configuration."
    cp /app/nginx-ssl.conf.template /etc/nginx/templates/default.conf.template
else
    echo "SSL disabled. Using HTTP Nginx configuration."
    cp /app/nginx-http.conf.template /etc/nginx/templates/default.conf.template
fi

# Hand off to the original entrypoint script from nginx:alpine
exec /docker-entrypoint.sh "$@"
