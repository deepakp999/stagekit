# Works on ARM (OCI Ampere A1) and x86. CPU-only PyTorch keeps the image small.
# build-essential: some audio packages (diffq) have no ARM64 wheel and compile from source.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 DATA_DIR=/data
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg curl unzip ca-certificates libsndfile1 build-essential \
    && rm -rf /var/lib/apt/lists/*

# yt-dlp needs a JavaScript runtime for current YouTube pages.
RUN curl -fsSL https://deno.land/install.sh | DENO_INSTALL=/usr/local sh -s -- -y \
    && deno --version

WORKDIR /srv
COPY requirements.txt .
RUN pip install --extra-index-url https://download.pytorch.org/whl/cpu torch \
    && pip install -r requirements.txt

COPY app ./app
COPY web ./web
COPY start.sh .
RUN chmod +x start.sh && useradd -m -u 1000 stagekit && mkdir -p /data && chown stagekit /data
USER stagekit

EXPOSE 8080
HEALTHCHECK --interval=60s --timeout=5s CMD curl -fs http://localhost:8080/api/health || exit 1
CMD ["./start.sh"]