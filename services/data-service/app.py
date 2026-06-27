"""data-service: microsservico produtor.

Expoe dados simulados, suporta latencia controlada para testar o timeout do
gateway e recebe sincronizacoes idempotentes da borda via POST /sync.

Passo 2: expoe metricas Prometheus em GET /metrics e emite spans OpenTelemetry
para o sidecar otel-collector.
"""

import os
import threading
import time
from datetime import datetime, timezone

from flask import Flask, Response, g, jsonify, request
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Histogram,
    generate_latest,
)

app = Flask(__name__)

# Nome usado nas labels de metricas e como service.name no tracing.
SERVICE_NAME = os.environ.get("OTEL_SERVICE_NAME", "data-service")

# Metricas exigidas pelo Passo 2 (FR-12). O contador e o histograma sao rotulados
# por servico, metodo e endpoint. A metrica de CPU (process_cpu_seconds_total) vem
# automaticamente do ProcessCollector padrao do prometheus_client.
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
    BatchSpanProcessor mantem uma thread propria que nao sobrevive ao fork. O
    exportador OTLP/gRPC le OTEL_EXPORTER_OTLP_ENDPOINT (sidecar em localhost:4317).
    """
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.flask import FlaskInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(resource=Resource.create({"service.name": SERVICE_NAME}))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
    FlaskInstrumentor().instrument_app(app)
    app.logger.info("OpenTelemetry configurado para service.name=%s", SERVICE_NAME)

# Latencia padrao aplicada ao GET /data quando o cliente nao informa delay_ms.
# Permite simular um produtor lento sem alterar o cliente (usado no Passo 3).
DEFAULT_DELAY_MS = int(os.environ.get("RESPONSE_DELAY_MS", "0"))

# Arquivo opcional para persistir os event_id ja recebidos. Quando ausente, a
# deduplicacao vive apenas em memoria, o que basta para a demonstracao.
SYNC_STORE_PATH = os.environ.get("SYNC_STORE_PATH", "")

_sync_lock = threading.Lock()
_seen_event_ids: set[str] = set()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_seen_events() -> None:
    """Carrega event_id persistidos para manter idempotencia entre reinicios."""
    if not SYNC_STORE_PATH or not os.path.exists(SYNC_STORE_PATH):
        return
    try:
        with open(SYNC_STORE_PATH, "r", encoding="utf-8") as handle:
            for line in handle:
                event_id = line.strip()
                if event_id:
                    _seen_event_ids.add(event_id)
    except OSError:
        # Falha ao ler o store nao deve derrubar o servico; seguimos em memoria.
        app.logger.warning("nao foi possivel ler SYNC_STORE_PATH=%s", SYNC_STORE_PATH)


def _persist_event_id(event_id: str) -> None:
    if not SYNC_STORE_PATH:
        return
    try:
        os.makedirs(os.path.dirname(SYNC_STORE_PATH) or ".", exist_ok=True)
        with open(SYNC_STORE_PATH, "a", encoding="utf-8") as handle:
            handle.write(f"{event_id}\n")
    except OSError:
        app.logger.warning("nao foi possivel gravar em SYNC_STORE_PATH=%s", SYNC_STORE_PATH)


@app.get("/data")
def get_data():
    """Retorna dados simulados com latencia opcional.

    A latencia vem de ?delay_ms=<n> ou, na ausencia, de RESPONSE_DELAY_MS.
    Use um delay acima do DATA_SERVICE_TIMEOUT_SECONDS do gateway para exercitar
    o modo degradado.
    """
    delay_ms = request.args.get("delay_ms", default=DEFAULT_DELAY_MS, type=int)
    if delay_ms and delay_ms > 0:
        time.sleep(delay_ms / 1000.0)

    payload = {
        "service": "data-service",
        "generated_at": _now_iso(),
        "delay_ms": delay_ms,
        "items": [
            {"id": 1, "name": "sensor-temperatura", "value": 21.5, "unit": "C"},
            {"id": 2, "name": "sensor-umidade", "value": 58.2, "unit": "%"},
            {"id": 3, "name": "sensor-pressao", "value": 1013.2, "unit": "hPa"},
        ],
    }
    return jsonify(payload)


@app.post("/sync")
def sync():
    """Recebe eventos bufferizados pela borda e deduplica por event_id.

    Corpo esperado: lista de eventos {event_id, timestamp, path, payload} ou um
    objeto {"events": [...]}. Responde com o resumo de aceitos e ignorados,
    garantindo idempotencia entre rodadas repetidas.
    """
    body = request.get_json(silent=True)
    if isinstance(body, dict) and "events" in body:
        events = body["events"]
    elif isinstance(body, list):
        events = body
    else:
        return jsonify({"error": "esperado lista de eventos ou {events: [...]}"}), 400

    if not isinstance(events, list):
        return jsonify({"error": "events deve ser uma lista"}), 400

    accepted: list[str] = []
    ignored: list[str] = []
    invalid = 0

    with _sync_lock:
        for event in events:
            if not isinstance(event, dict) or "event_id" not in event:
                invalid += 1
                continue
            event_id = str(event["event_id"])
            if event_id in _seen_event_ids:
                ignored.append(event_id)
                continue
            _seen_event_ids.add(event_id)
            _persist_event_id(event_id)
            accepted.append(event_id)
            app.logger.info(
                "evento sincronizado event_id=%s path=%s",
                event_id,
                event.get("path"),
            )

    return jsonify(
        {
            "received": len(events),
            "accepted": accepted,
            "ignored": ignored,
            "invalid": invalid,
            "total_known": len(_seen_event_ids),
        }
    )


@app.get("/health/live")
def health_live():
    return jsonify({"status": "alive"})


@app.get("/health/ready")
def health_ready():
    return jsonify({"status": "ready"})


_load_seen_events()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    app.run(host="0.0.0.0", port=port)
