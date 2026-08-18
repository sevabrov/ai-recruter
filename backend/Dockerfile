# AI Recruiter API.
#
# Nothing is installed on the host: Python, the dependencies and the test runner
# all live in here.
#
#   docker compose up -d backend                     http://localhost:8000
#   docker compose run --rm backend pytest -q        run the suite (needs postgres)
#   docker compose run --rm backend alembic current  schema revision
#
# Dev dependencies are part of the image on purpose — this is the phase where the
# suite is run inside the container. A slim production target (runtime deps only,
# no --reload) is a Phase 9 concern.

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencies first so code edits do not reinstall them.
COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt

COPY pyproject.toml alembic.ini ./
COPY alembic ./alembic
COPY app ./app
COPY tests ./tests

# Don't run as root, even in development.
RUN useradd --create-home --uid 10001 api && chown -R api:api /app
USER api

EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=5 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).status == 200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
