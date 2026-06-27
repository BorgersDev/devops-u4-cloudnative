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

# --workers 1 conforme entrega: registro do prometheus_client consistente e um unico
# worker para o OpenTelemetry (setup no post_fork de gunicorn.conf.py).
CMD ["gunicorn", "-c", "gunicorn.conf.py", "--workers", "1", "--bind", "0.0.0.0:8000", "app:app"]
