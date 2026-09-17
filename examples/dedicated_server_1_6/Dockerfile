FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SWIR_SERVER_NAME="SwirEngine Container Smoke" \
    SWIR_SERVER_TICK_RATE_HZ=120 \
    SWIR_SERVER_READY_AFTER_TICKS=2 \
    SWIR_SERVER_MAX_TICKS=12

WORKDIR /srv/swirengine
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN python -m pip install --no-cache-dir .
COPY examples/dedicated_server_1_6/run_server.py ./run_server.py

CMD ["python", "run_server.py"]
