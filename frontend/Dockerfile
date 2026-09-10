FROM node:22-alpine AS build
WORKDIR /app
COPY package.json ./
RUN npm install
COPY . .
RUN npm run build

FROM nginx:1.27-alpine
# openssl generates the htpasswd hash for optional basic auth — see
# docker-entrypoint.d/20-basic-auth.sh.
RUN apk add --no-cache openssl
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY docker-entrypoint.d/20-basic-auth.sh /docker-entrypoint.d/20-basic-auth.sh
COPY docker-entrypoint.d/25-allowed-hosts.sh /docker-entrypoint.d/25-allowed-hosts.sh
# sed strips any stray CR: cloned on Windows with core.autocrlf=true the
# scripts arrive as CRLF, the kernel reads the shebang as "/bin/sh\r", and
# nginx dies on boot with "not found" (exit 127). .gitattributes fixes this
# at the repository level; this line covers checkouts that predate it.
# The empty .conf files matter: nginx.conf includes both unconditionally, and
# an include of a missing file is a startup error.
RUN sed -i 's/\r$//' /docker-entrypoint.d/20-basic-auth.sh /docker-entrypoint.d/25-allowed-hosts.sh \
    && chmod +x /docker-entrypoint.d/20-basic-auth.sh /docker-entrypoint.d/25-allowed-hosts.sh \
    && touch /etc/nginx/basic-auth.conf /etc/nginx/allowed-hosts.conf

EXPOSE 80

HEALTHCHECK --interval=10s --timeout=5s --start-period=5s --retries=5 \
    CMD wget -qO- http://127.0.0.1:80/api/health || exit 1
