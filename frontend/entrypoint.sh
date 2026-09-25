#!/bin/sh

if [ "$ENABLE_SSL" = "true" ]; then
    echo "SSL enabled. Using HTTPS Nginx configuration."
    cp /etc/nginx/templates/nginx-ssl.conf.template /etc/nginx/templates/default.conf.template
else
    echo "SSL disabled. Using HTTP Nginx configuration."
    cp /etc/nginx/templates/nginx-http.conf.template /etc/nginx/templates/default.conf.template
fi

# Hand off to the original entrypoint script from nginx:alpine
exec /docker-entrypoint.sh "$@"
