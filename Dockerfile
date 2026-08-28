# One image, three services.
#
# The collector, agent and dashboard all import common/, so they ship as a
# single image deployed three times with different start commands. Building
# once means the shared code physically cannot drift between services.
#
# The start command is supplied per-deploy via SERVICE_MODULE, defaulting to
# the dashboard.

FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies first so the layer caches across code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY common/    ./common/
COPY collector/ ./collector/
COPY diff/      ./diff/
COPY agent/     ./agent/
COPY dashboard/ ./dashboard/
COPY config/    ./config/

# Cloud Run injects PORT; default to 8080 for local runs.
ENV PORT=8080
ENV SERVICE_MODULE=dashboard.main:app

# Shell form so $SERVICE_MODULE and $PORT are expanded at runtime.
CMD exec uvicorn "$SERVICE_MODULE" --host 0.0.0.0 --port "$PORT"
