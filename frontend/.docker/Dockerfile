# Phase 1
FROM node:20.20.0-alpine3.23 AS builder

WORKDIR /app

COPY package.json .
COPY package-lock.json .
RUN npm install && npm install @rollup/rollup-linux-x64-musl

COPY . .

RUN npm run build

# Phase 2
FROM nginx:1.29.2-alpine3.22-slim AS production

# 🔧 Tambahkan apk update & upgrade untuk update libcrypto3/libssl3
RUN apk update && apk upgrade --no-cache

COPY --from=builder /app/dist /usr/share/nginx/html
COPY .docker/default.conf.template /etc/nginx/templates/default.conf.template

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]