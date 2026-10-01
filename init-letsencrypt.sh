#!/bin/bash
# init-letsencrypt.sh

if ! [ -x "$(command -v docker)" ]; then
  echo 'Error: docker is not installed.' >&2
  exit 1
fi

# Explicitly load variables from .env if present
if [ -f .env ]; then
  set -a; source .env; set +a
fi

# Sanitize ENABLE_SSL and LOCAL_HTTPS (lowercase, remove spaces)
SAFE_ENABLE_SSL=$(echo "$ENABLE_SSL" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')
SAFE_LOCAL_HTTPS=$(echo "$LOCAL_HTTPS" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')

if [ "$SAFE_ENABLE_SSL" != "true" ]; then
  echo "ENABLE_SSL is set to '$ENABLE_SSL' (not true). Skipping Let's Encrypt initialization."
  exit 0
fi

if [ -z "$DOMAIN_NAME" ] || [ -z "$CERTBOT_EMAIL" ]; then
  echo "Error: DOMAIN_NAME or CERTBOT_EMAIL environment variables are not set."
  echo "Ensure these are configured in GitLab CI/CD Variables."
  exit 1
fi

# Sanitize DOMAIN_NAME (strip whitespace and carriage returns)
CLEAN_DOMAIN=$(echo "$DOMAIN_NAME" | tr -d '[:space:]')
domains=($CLEAN_DOMAIN)
rsa_key_size=4096
data_path="./certbot"
email="$CERTBOT_EMAIL"

if [ -d "$data_path/conf/live/$domains" ]; then
  echo "Existing data found for $domains. Skipping initialization."
  exit 0
fi

if [ "$SAFE_LOCAL_HTTPS" = "true" ] && [ -f "$LOCAL_CA_DIR/rootCA.pem" ]; then
  echo "### Generating signed local certificate for $domains using Local CA..."
  host_path="./certbot/conf/live/$domains"
  mkdir -p "$host_path"
  
  openssl genrsa -out "$host_path/privkey.pem" $rsa_key_size
  
  cat > "$host_path/req.cnf" <<EOF
[req]
req_extensions = v3_req
distinguished_name = req_distinguished_name
prompt = no
[req_distinguished_name]
CN = $domains
[v3_req]
subjectAltName = @alt_names
[alt_names]
DNS.1 = $domains
EOF

  openssl req -new -key "$host_path/privkey.pem" -out "$host_path/cert.csr" -config "$host_path/req.cnf"

  cat > "$host_path/v3.ext" <<EOF
authorityKeyIdentifier=keyid,issuer
basicConstraints=CA:FALSE
keyUsage = digitalSignature, nonRepudiation, keyEncipherment, dataEncipherment
subjectAltName = @alt_names
[alt_names]
DNS.1 = $domains
EOF

  openssl x509 -req -in "$host_path/cert.csr" \
    -CA "$LOCAL_CA_DIR/rootCA.pem" \
    -CAkey "$LOCAL_CA_DIR/rootCA.key" \
    -CAcreateserial -out "$host_path/fullchain.pem" \
    -days 365 -extfile "$host_path/v3.ext"
    
  rm "$host_path/req.cnf" "$host_path/v3.ext" "$host_path/cert.csr"
else
  docker compose run --rm --entrypoint "sh -c '\
    mkdir -p /etc/letsencrypt/live/$domains && \
    openssl req -x509 -nodes -newkey rsa:$rsa_key_size -days 1\
      -keyout /etc/letsencrypt/live/$domains/privkey.pem \
      -out /etc/letsencrypt/live/$domains/fullchain.pem \
      -subj /CN=localhost'" certbot
fi
echo

echo "### Starting nginx ..."
docker compose up --force-recreate -d frontend
echo

if [ "$SAFE_LOCAL_HTTPS" = "true" ]; then
  echo "### LOCAL_HTTPS is true. Keeping dummy certificate and skipping Let's Encrypt."
  echo "### Local HTTPS setup complete."
  exit 0
fi

echo "### Deleting dummy certificate for $domains ..."
docker compose run --rm --entrypoint "sh -c '\
  rm -Rf /etc/letsencrypt/live/$domains && \
  rm -Rf /etc/letsencrypt/archive/$domains && \
  rm -Rf /etc/letsencrypt/renewal/$domains.conf'" certbot
echo

echo "### Requesting Let's Encrypt certificate for $domains ..."
# Join $domains to -d args
domain_args=""
for domain in "${domains[@]}"; do
  domain_args="$domain_args -d $domain"
done

# Select appropriate email arg
case "$email" in
  "") email_arg="--register-unsafely-without-email" ;;
  *) email_arg="--email $email" ;;
esac

staging_arg=""
if [ "$USE_STAGING_SSL" = "true" ]; then
  echo "### Using Let's Encrypt Staging Environment..."
  staging_arg="--staging"
fi

docker compose run --rm --entrypoint "\
  certbot certonly --webroot -w /var/www/certbot \
    $email_arg \
    $domain_args \
    --rsa-key-size $rsa_key_size \
    --agree-tos \
    --non-interactive \
    $staging_arg \
    --force-renewal" certbot
echo

echo "### Reloading nginx ..."
docker compose exec frontend nginx -s reload
echo
