FROM docker.io/library/node:22-alpine AS build
WORKDIR /app
COPY package.json ./
RUN npm install
COPY . .
RUN npm run build

FROM docker.io/library/nginx:1.27-alpine
# openssl generates the htpasswd hash for optional basic auth — see
# docker-entrypoint.d/20-basic-auth.sh.
RUN apk add --no-cache openssl
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY docker-entrypoint.d/20-basic-auth.sh /docker-entrypoint.d/20-basic-auth.sh
RUN chmod +x /docker-entrypoint.d/20-basic-auth.sh \
    && touch /etc/nginx/basic-auth.conf

EXPOSE 80

HEALTHCHECK --interval=10s --timeout=5s --start-period=5s --retries=5 \
    CMD wget -qO- http://127.0.0.1:80/api/health || exit 1
