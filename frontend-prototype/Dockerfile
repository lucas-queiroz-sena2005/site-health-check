FROM node:20-slim

WORKDIR /app

# Copy package files first to leverage Docker cache
COPY package.json package-lock.json* ./

# Install dependencies
RUN npm install

# Copy the rest of the source code
COPY . .

# Expose the Vite default port
EXPOSE 5173

# Run the dev server and expose it to the host network
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
