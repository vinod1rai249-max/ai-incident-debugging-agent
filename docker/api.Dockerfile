FROM python:3.11-slim AS builder
WORKDIR /app
COPY requirements-docker.txt ./
RUN pip install --prefix=/install -r requirements-docker.txt

FROM python:3.11-slim AS runtime
WORKDIR /app
COPY --from=builder /install /usr/local
COPY core/ core/
COPY genai/ genai/
COPY agents/ agents/
COPY apps/api/ apps/api/
COPY apps/incident_debugger/ apps/incident_debugger/
COPY data/ data/
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
