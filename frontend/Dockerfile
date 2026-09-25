# --- Build Stage ---
FROM docker.io/library/node:22-alpine AS builder

WORKDIR /app

# Copy package files first for layer caching
COPY package*.json ./
RUN npm install

# Copy the rest of the frontend source
COPY . ./

# Build the Vite production bundle
RUN npm run build

# --- Serve Stage ---
FROM docker.io/library/nginx:alpine

# Copy the built static assets from the builder stage
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy the custom nginx config templates
COPY nginx-http.conf.template /etc/nginx/templates/nginx-http.conf.template
COPY nginx-ssl.conf.template /etc/nginx/templates/nginx-ssl.conf.template

# Copy and set up the dynamic entrypoint
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Expose port 80 to the host
EXPOSE 80

# Use our custom entrypoint
ENTRYPOINT ["/app/entrypoint.sh"]

# Start Nginx
CMD ["nginx", "-g", "daemon off;"]
