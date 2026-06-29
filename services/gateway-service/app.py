"""gateway-service: microsservico consumidor.

Recebe a requisicao do usuario, chama o data-service e formata a resposta.
Trata indisponibilidade e latencia acima do timeout com modo degradado.

Passo 2: expoe metricas Prometheus em GET /metrics e emite spans OpenTelemetry,
propagando o contexto W3C traceparent para o data-service (trace multi-servico).
O buffer local de borda entra no Passo 3.
"""

import json
import os
import threading
import time
import uuid
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

# Passo 3 (borda): quando EDGE_BUFFER_PATH esta definido, o gateway opera em modo
# de borda e grava um evento no buffer local sempre que cai em modo degradado
# (timeout, conexao bloqueada por NetworkPolicy ou erro do central). Vazio = gateway
# central, sem bufferizacao (comportamento dos Passos 1 e 2 preservado).
EDGE_BUFFER_PATH = os.environ.get("EDGE_BUFFER_PATH", "")
EDGE_MODE = bool(EDGE_BUFFER_PATH)
# Pushgateway local opcional para observabilidade offline (US-013). Quando vazio, a
# observabilidade offline fica apenas no log local do container.
PUSHGATEWAY_URL = os.environ.get("PUSHGATEWAY_URL", "")

# Serializa escritas concorrentes no buffer e protege o contador offline. Com
# gunicorn --workers 1 ha um unico processo, mas o Flask atende em threads.
_buffer_lock = threading.Lock()
_offline_buffered_count = 0

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

    No gateway de borda (Passo 3) nao ha sidecar otel-collector nem Jaeger
    alcancavel, entao OTEL_SDK_DISABLED=true desliga o tracing para nao gerar erros
    de exportacao. Os Passos 1 e 2 (gateway central) seguem com a variavel ausente.
    """
    if os.environ.get("OTEL_SDK_DISABLED", "").lower() == "true":
        app.logger.info("OpenTelemetry desabilitado via OTEL_SDK_DISABLED (modo borda)")
        return

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
        return _degraded(
            upstream, reason="data-service indisponivel (conexao bloqueada ou recusada)"
        )
    except requests.exceptions.RequestException as exc:
        return _degraded(upstream, reason=f"falha ao chamar data-service: {exc}")


def _degraded(upstream: str, reason: str):
    """Resposta degradada controlada. Em modo borda, bufferiza o evento localmente.

    O gateway nunca propaga 500 bruto: responde HTTP 200 com degraded=true para
    permanecer util ao cliente. Quando EDGE_MODE esta ativo, grava o evento da
    requisicao no buffer local (US-012) para sincronizacao posterior via sync.py.
    """
    app.logger.warning("modo degradado: %s", reason)
    buffered_event_id = _buffer_event(reason) if EDGE_MODE else None
    body = {
        "service": "gateway-service",
        "served_at": _now_iso(),
        "degraded": True,
        "upstream": upstream,
        "reason": reason,
        "data": None,
        "message": "resposta degradada: produtor central indisponivel ou lento",
        # None no gateway central; uuid do evento bufferizado no gateway de borda.
        "buffered_event_id": buffered_event_id,
    }
    # 200 proposital: o gateway permanece funcional do ponto de vista do cliente.
    return jsonify(body), 200


def _buffer_event(reason: str):
    """Grava um evento da requisicao no buffer local de borda e retorna seu event_id.

    O evento segue o contrato unico do fluxo: {event_id, timestamp, path, payload}.
    O event_id (uuid) e gerado uma unica vez por requisicao e e o que viabiliza a
    deduplicacao idempotente no POST /sync do data-service (US-014). O payload usa
    apenas dados simulados/da requisicao, nunca dados pessoais (privacidade).
    """
    event = {
        "event_id": str(uuid.uuid4()),
        "timestamp": _now_iso(),
        "path": request.path,
        "payload": {
            "reason": reason,
            "method": request.method,
            "query": request.args.to_dict(),
        },
    }
    try:
        with _buffer_lock:
            buffer_dir = os.path.dirname(EDGE_BUFFER_PATH)
            if buffer_dir:
                os.makedirs(buffer_dir, exist_ok=True)
            with open(EDGE_BUFFER_PATH, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        app.logger.info(
            "evento bufferizado localmente event_id=%s path=%s buffer=%s",
            event["event_id"],
            event["path"],
            EDGE_BUFFER_PATH,
        )
        _push_offline_metric()
        return event["event_id"]
    except OSError:
        # Falha de escrita no buffer nao deve derrubar a resposta ao cliente.
        app.logger.error("falha ao gravar buffer local em %s", EDGE_BUFFER_PATH)
        return None


def _push_offline_metric():
    """Envia o total de eventos bufferizados ao Pushgateway local (observabilidade offline).

    O Pushgateway apenas retem o ultimo valor por job ate ser raspado por um
    Prometheus apos a reconexao. Por isso enviamos o acumulado como Gauge. Falha de
    envio e tolerada: o log local continua sendo a evidencia minima offline.
    """
    global _offline_buffered_count
    with _buffer_lock:
        _offline_buffered_count += 1
        current = _offline_buffered_count
    if not PUSHGATEWAY_URL:
        return
    try:
        from prometheus_client import CollectorRegistry, Gauge, push_to_gateway

        registry = CollectorRegistry()
        gauge = Gauge(
            "edge_buffered_events_total",
            "Eventos gravados no buffer local durante o modo offline da borda",
            registry=registry,
        )
        gauge.set(current)
        push_to_gateway(
            PUSHGATEWAY_URL, job="gateway-edge", registry=registry, timeout=2
        )
    except Exception as exc:  # pushgateway pode estar fora; nao e fatal
        app.logger.warning("pushgateway indisponivel (%s): %s", PUSHGATEWAY_URL, exc)


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
