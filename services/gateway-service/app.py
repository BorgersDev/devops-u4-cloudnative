"""gateway-service: microsservico consumidor.

Recebe a requisicao do usuario, chama o data-service e formata a resposta.
Trata indisponibilidade e latencia acima do timeout com modo degradado.

Escopo do Passo 1. Metricas, OpenTelemetry e buffer local de borda entram nos
Passos 2 e 3.
"""

import os
from datetime import datetime, timezone

import requests
from flask import Flask, jsonify

app = Flask(__name__)

DATA_SERVICE_URL = os.environ.get("DATA_SERVICE_URL", "http://localhost:8000")
DATA_SERVICE_TIMEOUT_SECONDS = float(
    os.environ.get("DATA_SERVICE_TIMEOUT_SECONDS", "2.0")
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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
