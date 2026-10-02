# syntax=docker/dockerfile:1
FROM python:3.12-slim@sha256:dddfd7e07f9d15aeeca61529320492139d21cac7f0070c00609243e51e4e0016 AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
RUN groupadd --gid 10001 oj && useradd --uid 10001 --gid oj --no-create-home oj \
    && mkdir /data /evidence && chown oj:oj /data /evidence

FROM base AS mock
COPY tests/mock_oj/server.py /app/mock_server.py
USER 10001:10001
EXPOSE 8099
CMD ["python", "mock_server.py", "--host", "0.0.0.0", "--port", "8099"]

FROM base AS smoke
COPY scripts/smoke_compose.py /app/smoke_compose.py
USER 10001:10001
ENTRYPOINT ["python", "smoke_compose.py"]

FROM base AS platform
COPY requirements-runtime.lock ./
RUN python -m pip install --no-cache-dir -r requirements-runtime.lock && python -m pip check
COPY backend/ backend/
COPY config_center/ config_center/
COPY core_engine/ core_engine/
COPY plugins/ plugins/
COPY task_center/ task_center/
COPY storage/ storage/
COPY profiles/ profiles/
COPY frontend/ frontend/
COPY main.py ./
ARG PLATFORM_SHA=unknown
ENV OJ_PLATFORM_SHA=${PLATFORM_SHA} OJ_DB=/data/tasks.db OJ_REPORT_DIR=/data/reports
LABEL org.opencontainers.image.revision=${PLATFORM_SHA}
USER 10001:10001
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "backend.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
