# ResearchMind: one image containing the API and the built frontend.
# Ollama is NOT included; the container talks to the Ollama running on your machine (see docker-compose.yml).

FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 RM_DATA_DIR=/data RM_HOST=0.0.0.0 RM_PORT=8000
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt
COPY backend/ backend/
COPY run.py .
COPY --from=web /web/dist frontend/dist
RUN useradd --create-home app && mkdir /data && chown app /data
USER app
VOLUME /data
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status==200 else 1)"
# exec form so SIGTERM from `docker stop` reaches run.py, which stops the server cleanly
CMD ["python", "run.py", "--no-browser", "--host", "0.0.0.0", "--port", "8000"]
