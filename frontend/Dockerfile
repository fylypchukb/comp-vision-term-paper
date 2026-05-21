# Stage 1 — build the React app
FROM node:20-alpine AS builder

WORKDIR /app

# Install dependencies first (layer cache)
COPY package*.json ./
RUN npm ci

# Copy source and build
COPY . .
RUN npm run build

# Stage 2 — serve via nginx
FROM nginx:alpine

# Copy the built SPA
COPY --from=builder /app/dist /usr/share/nginx/html

# Replace default nginx config with our reverse-proxy config
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
