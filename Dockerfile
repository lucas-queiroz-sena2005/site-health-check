# --- Build Stage ---
FROM node:22-alpine AS builder

WORKDIR /app

# Copy package files first for layer caching
COPY frontend/package*.json ./
RUN npm install

# Copy the rest of the frontend source
COPY frontend/ ./

# Build the Vite production bundle
RUN npm run build

# --- Serve Stage ---
FROM nginx:alpine

# Copy the built static assets from the builder stage
COPY --from=builder /app/dist /usr/share/nginx/html

# Expose port 80 to the host
EXPOSE 80

# Start Nginx
CMD ["nginx", "-g", "daemon off;"]
