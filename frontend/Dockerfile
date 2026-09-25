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

# Copy custom nginx config for API proxying to templates so environment variables are replaced
COPY nginx.conf /etc/nginx/templates/default.conf.template

# Expose port 80 to the host
EXPOSE 80

# Start Nginx
CMD ["nginx", "-g", "daemon off;"]
