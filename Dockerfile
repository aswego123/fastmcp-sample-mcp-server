FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MCP_NOTES_DB=/data/notes.db \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=8000 \
    MCP_TRANSPORT=sse

WORKDIR /app

# Install Python deps first to leverage layer caching
COPY requirements.txt ./
RUN pip install -r requirements.txt

# Copy the server package
COPY server/ ./server/

# Persisted notes DB lives here
RUN mkdir -p /data
VOLUME ["/data"]

EXPOSE 8000

# Use exec form so signals (SIGTERM) reach Python cleanly
ENTRYPOINT ["python", "-m", "server"]
