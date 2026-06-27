# Imagem leve conforme criterio de aceite (US-003).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py gunicorn.conf.py ./

EXPOSE 8000

# --workers 1 mantem o registro do prometheus_client consistente entre scrapes e
# garante um unico worker para o OpenTelemetry (setup no post_fork de gunicorn.conf.py).
# Para varios workers seria preciso configurar PROMETHEUS_MULTIPROC_DIR.
CMD ["gunicorn", "-c", "gunicorn.conf.py", "--workers", "1", "--bind", "0.0.0.0:8000", "app:app"]
