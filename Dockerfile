# phantra-growth: the bots' image (2026-10-26). One image, one process group
# per bot in fly.toml. ffmpeg is here for ffprobe: the Discord bot measures a
# clip's length on its own host before anything is uploaded.
# BASE is only overridden to build from a mirror when Docker Hub rate-limits
ARG BASE=python:3.12-slim
FROM ${BASE}

RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY bots/requirements.txt bots/requirements.txt
RUN pip install --no-cache-dir -r bots/requirements.txt

COPY bots bots

# a non-root user; the state volume is mounted at /data (fly.toml)
RUN useradd --create-home --uid 10001 bot && mkdir -p /data && chown bot /data
USER bot

ENV PYTHONUNBUFFERED=1 \
    PHANTRA_BOT_STATE_DIR=/data

CMD ["python", "-m", "bots.discord"]
