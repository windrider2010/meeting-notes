FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/models-cache \
    XDG_CACHE_HOME=/models-cache \
    MN_OUTPUT_DIR=/outputs \
    MN_EXPORT_RETENTION_DAYS=365 \
    MN_EXPORT_MAX_SESSIONS=200 \
    MN_MODEL_SIZE=small \
    MN_DEVICE=cpu \
    MN_COMPUTE_TYPE=int8 \
    MN_TRANSCRIBE_WINDOW_MS=5000 \
    OMP_NUM_THREADS=8

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt /app/requirements.txt
RUN python3 -m pip install --upgrade pip && \
    python3 -m pip install -r /app/requirements.txt

COPY backend/ /app/

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health').read()"

CMD ["python3", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
