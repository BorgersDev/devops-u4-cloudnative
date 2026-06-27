"""gateway-service: microsservico consumidor.

Recebe a requisicao do usuario, chama o data-service e formata a resposta.
Trata indisponibilidade e latencia acima do timeout com modo degradado.

Passo 2: expoe metricas Prometheus em GET /metrics e emite spans OpenTelemetry,
propagando o contexto W3C traceparent para o data-service (trace multi-servico).
O buffer local de borda entra no Passo 3.
"""

import os
import time
from datetime import datetime, timezone

import requests
from flask import Flask, Response, g, jsonify, request
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Histogram,
    generate_latest,
)

app = Flask(__name__)

DATA_SERVICE_URL = os.environ.get("DATA_SERVICE_URL", "http://localhost:8000")
DATA_SERVICE_TIMEOUT_SECONDS = float(
    os.environ.get("DATA_SERVICE_TIMEOUT_SECONDS", "2.0")
)

# Nome usado nas labels de metricas e como service.name no tracing.
SERVICE_NAME = os.environ.get("OTEL_SERVICE_NAME", "gateway-service")

# Metricas exigidas pelo Passo 2 (FR-12). A metrica de CPU
# (process_cpu_seconds_total) vem do ProcessCollector padrao do prometheus_client.
REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total de requisicoes HTTP processadas",
    ["service", "method", "endpoint", "http_status"],
)
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "Duracao das requisicoes HTTP em segundos",
    ["service", "method", "endpoint"],
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@app.before_request
def _start_timer():
    g._start_time = time.perf_counter()


@app.after_request
def _record_metrics(response):
    """Registra contador e latencia por requisicao, exceto o proprio /metrics."""
    endpoint = request.endpoint or "unknown"
    if endpoint != "metrics":
        elapsed = time.perf_counter() - getattr(g, "_start_time", time.perf_counter())
        REQUEST_LATENCY.labels(SERVICE_NAME, request.method, endpoint).observe(elapsed)
        REQUEST_COUNT.labels(
            SERVICE_NAME, request.method, endpoint, response.status_code
        ).inc()
    return response


@app.get("/metrics")
def metrics():
    """Exposicao no formato texto do Prometheus (scrape por annotations)."""
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)


def setup_tracing():
    """Configura o OpenTelemetry no worker pos-fork do gunicorn.

    Roda no hook post_fork (ver gunicorn.conf.py) e nao no master, pois o
    BatchSpanProcessor mantem uma thread propria que nao sobrevive ao fork. Alem do
    Flask, instrumenta a lib requests para propagar o header W3C traceparent ate o
    data-service, gerando um trace unico com spans dos dois servicos.
    """
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.flask import FlaskInstrumentor
    from opentelemetry.instrumentation.requests import RequestsInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(resource=Resource.create({"service.name": SERVICE_NAME}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
    FlaskInstrumentor().instrument_app(app)
    RequestsInstrumentor().instrument()
    app.logger.info("OpenTelemetry configurado para service.name=%s", SERVICE_NAME)


@app.get("/")
def index():
    """Chama o data-service e devolve uma resposta enriquecida.

    Em caso de timeout, erro de conexao ou status nao-2xx, responde em modo
    degradado (HTTP 200 com degraded=true) em vez de propagar um 500 bruto,
    para que o gateway continue util mesmo com o produtor instavel.
    """
    upstream = f"{DATA_SERVICE_URL.rstrip('/')}/data"
    try:
        response = requests.get(upstream, timeout=DATA_SERVICE_TIMEOUT_SECONDS)
        response.raise_for_status()
        data = response.json()
        return jsonify(
            {
                "service": "gateway-service",
                "served_at": _now_iso(),
                "degraded": False,
                "upstream": upstream,
                "data": data,
            }
        )
    except requests.exceptions.Timeout:
        return _degraded(upstream, reason="timeout ao chamar data-service")
    except requests.exceptions.ConnectionError:
        return _degraded(upstream, reason="data-service indisponivel")
    except requests.exceptions.RequestException as exc:
        return _degraded(upstream, reason=f"falha ao chamar data-service: {exc}")


def _degraded(upstream: str, reason: str):
    app.logger.warning("modo degradado: %s", reason)
    body = {
        "service": "gateway-service",
        "served_at": _now_iso(),
        "degraded": True,
        "upstream": upstream,
        "reason": reason,
        "data": None,
        "message": "resposta degradada: produtor central indisponivel ou lento",
    }
    # 200 proposital: o gateway permanece funcional do ponto de vista do cliente.
    return jsonify(body), 200


@app.get("/health/live")
def health_live():
    return jsonify({"status": "alive"})


@app.get("/health/ready")
def health_ready():
    # Readiness nao depende do central: o gateway pode atender em modo degradado.
    return jsonify({"status": "ready"})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    app.run(host="0.0.0.0", port=port)
