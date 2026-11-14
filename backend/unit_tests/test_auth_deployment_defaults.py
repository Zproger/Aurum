"""Deployment defaults for the first-owner test rollout."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_develop_compose_enables_first_owner_setup_without_operator_env_edits() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")

    assert "AURUM_APP_AUTH_REQUIRED: ${AURUM_APP_AUTH_REQUIRED:-true}" in compose
    assert "AURUM_APP_AUTH_REQUIRED=true" in env_example
    assert "AURUM_ALLOW_INSECURE_HTTP: ${AURUM_ALLOW_INSECURE_HTTP:-true}" in compose
    assert "AURUM_ALLOW_INSECURE_HTTP=true" in env_example


def test_disposable_postgres_runtime_is_never_a_deployment_setting() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")

    assert "AURUM_DISPOSABLE_POSTGRES_RUNTIME" not in compose
    assert "AURUM_DISPOSABLE_POSTGRES_RUNTIME" not in env_example


def test_tls_proxy_uses_an_internal_port_instead_of_trusting_client_forwarded_proto() -> None:
    nginx = (ROOT / "frontend/nginx.conf").read_text(encoding="utf-8")
    caddy = (ROOT / "Caddyfile").read_text(encoding="utf-8")
    tls_compose = (ROOT / "docker-compose.tls.yml").read_text(encoding="utf-8")

    assert "$http_x_forwarded_proto" not in nginx
    assert "listen 8080;" in nginx
    assert "8080 1;" in nginx
    assert "reverse_proxy web:8080" in caddy
    assert "header_up X-Real-IP {remote_host}" in caddy
    assert "8080 $http_x_real_ip;" in nginx
    assert "default $aurum_port80_client;" in nginx
    assert "default $aurum_port80_proto;" in nginx
    assert "include /etc/nginx/trusted-tls-proxy.conf;" in nginx
    assert "limit_req_zone $aurum_forwarded_client" in nginx
    assert "proxy_set_header X-Real-IP $aurum_forwarded_client;" in nginx
    assert (
        "auth/bootstrap/initial-owner|auth/invitations/accept|workspaces/invitations/accept|"
        "workspaces/[^/]+/invitations"
    ) in nginx
    assert "client_max_body_size 16k;" in nginx
    assert "subnet:" not in tls_compose
    assert "ipv4_address:" not in tls_compose


def test_compose_uses_portable_docker_networking_and_publishes_http() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    tunnel = (ROOT / "docker-compose.cloudflare-tunnel.yml").read_text(encoding="utf-8")

    assert "ipv4_address:" not in compose
    assert "ipam:" not in compose
    assert '${AURUM_BIND_ADDRESS:-0.0.0.0}:${AURUM_WEB_PORT:-3000}:80' in compose
    assert "ports: !reset []" not in tunnel
    assert "services: {}" in tunnel


def test_nginx_preserves_external_host_port_for_same_origin_checks() -> None:
    nginx = (ROOT / "frontend/nginx.conf").read_text(encoding="utf-8")

    assert "default $http_host;" in nginx
    assert "proxy_set_header Host $aurum_forwarded_host;" in nginx
    assert "proxy_set_header Host $host;" not in nginx


def test_compose_provisions_a_shared_proxy_identity_independent_of_bridge_ip() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    nginx = (ROOT / "frontend/nginx.conf").read_text(encoding="utf-8")
    dockerfile = (ROOT / "frontend/Dockerfile").read_text(encoding="utf-8")

    assert "proxy_shared_secret" in compose
    assert "AURUM_AUTH_PROXY_SHARED_SECRET_FILE: /run/aurum-secrets/proxy_shared_secret" in compose
    # backend, web, and the optional Telegram worker all read the same
    # installation-owned secrets without depending on a Docker bridge IP.
    assert compose.count("aurum_auth_secrets:/run/aurum-secrets:ro") == 3
    assert "30-proxy-identity.sh" in dockerfile
    assert nginx.count("include /etc/nginx/proxy-identity.conf;") == 3


def test_operator_guidance_matches_default_required_auth_boundary() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    docs = (ROOT / "DOCS.md").read_text(encoding="utf-8")
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    entrypoint = (
        ROOT / "frontend/docker-entrypoint.d/20-basic-auth.sh"
    ).read_text(encoding="utf-8")

    combined = "\n".join((readme, docs, env_example, compose, entrypoint))
    assert "has no built-in login system" not in combined
    assert "This instance has NO authentication" not in combined
    assert "Both unset = no login screen at all" not in combined
    assert "default required-auth" in readme
    assert "readiness-blocked with `503`" in docs
    assert "Required application authentication always suppresses" in env_example
    assert "Basic Auth perimeter is disabled" in entrypoint


def test_forwarded_proto_is_trusted_only_by_explicit_cloudflare_opt_in() -> None:
    script = (ROOT / "frontend/docker-entrypoint.d/27-trusted-tls-proxy.sh").read_text(encoding="utf-8")
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    dockerfile = (ROOT / "frontend/Dockerfile").read_text(encoding="utf-8")

    assert "AURUM_TRUSTED_TLS_PROXY: ${AURUM_TRUSTED_TLS_PROXY:-none}" in compose
    assert 'MODE="${AURUM_TRUSTED_TLS_PROXY:-none}"' in script
    cloudflare, rest = script.split("  none|\"\")", 1)
    # Client headers appear only in the cloudflare branch.
    assert "$http_x_forwarded_proto" in cloudflare and "$http_cf_connecting_ip" in cloudflare
    safe_branch = rest.split("  *)", 1)[0]
    assert "$http_" not in safe_branch
    assert "AURUM_TRUSTED_TLS_PROXY=none /docker-entrypoint.d/27-trusted-tls-proxy.sh" in dockerfile


def test_csp_allows_the_pdf_worker_but_no_blob_frames() -> None:
    nginx = (ROOT / "frontend/nginx.conf").read_text(encoding="utf-8")
    csp = next(line for line in nginx.splitlines() if "add_header Content-Security-Policy" in line)

    # Statement PDFs are drawn by pdf.js in a same-origin worker, not framed.
    assert "worker-src 'self'" in csp
    assert "frame-src" not in csp
    assert "connect-src 'self';" in csp
