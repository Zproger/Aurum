#!/bin/sh
# Runs before nginx starts, same convention as 20-basic-auth.sh next door.
#
# Writes the Host allow-list that nginx.conf includes. This is what stops DNS
# rebinding: a page on the open internet can point its own hostname at
# 127.0.0.1, wait for the DNS TTL to expire, and then have the victim's own
# browser issue same-origin requests to whatever is listening there. The
# browser's origin checks don't help — as far as it's concerned the request
# really is same-origin — but the Host header still carries the attacker's
# domain, so refusing hostnames we don't expect closes it.
#
# AURUM_ALLOWED_HOSTS is a space- or comma-separated list. Default covers
# local access only; add your own hostname when you serve Aurum under one
# (see .env.example). "*" disables the check entirely.
set -eu

FRAGMENT=/etc/nginx/allowed-hosts.conf
HOSTS="${AURUM_ALLOWED_HOSTS:-localhost 127.0.0.1}"

if [ "$HOSTS" = "*" ]; then
  : > "$FRAGMENT"
  echo "[aurum] Host header check disabled (AURUM_ALLOWED_HOSTS=*)." >&2
  return 0 2>/dev/null || exit 0
fi

# "a,b c" -> "a|b|c", with regex metacharacters in each entry escaped so an
# IP's dots can't match any character.
PATTERN="$(printf '%s' "$HOSTS" \
  | tr ',' ' ' \
  | tr -s ' ' '\n' \
  | sed '/^$/d' \
  | sed 's/[].[^$*\/+?(){}|\\]/\\&/g' \
  | paste -sd '|' -)"

cat > "$FRAGMENT" <<EOF
# Generated at container start by docker-entrypoint.d/25-allowed-hosts.sh.
# \$host is the Host header without the port, so entries here are bare
# hostnames. "if" is normally best avoided in nginx, but a bare "return"
# inside it is one of the two documented-safe uses.
if (\$host !~* '^(${PATTERN})\$') {
    return 421 "Aurum: unexpected Host header '\$host'. Add it to AURUM_ALLOWED_HOSTS in .env (see .env.example), or set that variable to * to disable this check.\n";
}
EOF

echo "[aurum] Host header allow-list: ${HOSTS}" >&2
