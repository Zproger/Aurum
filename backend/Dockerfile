FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

# Drop root. The app never writes to disk (PYTHONDONTWRITEBYTECODE above, no
# uploads, no local cache), so it only needs read access to /app — which is
# why the source stays root-owned and is merely readable here. Anything that
# manages to execute code in this container now lands as an unprivileged user
# instead of root, which is the difference between a bad day and a container
# escape.
#
# Note for running the test suite (see tests/README.md): installing
# requirements-dev.txt inside the container now needs `--user`, or run the
# exec with `-u root`.
RUN useradd --create-home --uid 10001 aurum
USER aurum

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=5 \
    CMD curl -f http://localhost:8000/api/health || exit 1

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
