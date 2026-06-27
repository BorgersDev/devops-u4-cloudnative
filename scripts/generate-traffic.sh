#!/usr/bin/env bash
# Gera trafego contra o gateway-service para popular metricas (Prometheus) e
# traces (Jaeger) no Passo 2.
#
# Cada GET / no gateway dispara uma chamada interna ao data-service, produzindo um
# trace multi-servico (spans de gateway-service e data-service no mesmo trace).
#
# Pre-requisito: expor o gateway localmente, por exemplo:
#   kubectl -n cloudnative port-forward svc/gateway-service 8100:8000
#
# Uso:
#   ./scripts/generate-traffic.sh [url] [total]
# Exemplos:
#   ./scripts/generate-traffic.sh                      # 50 req em http://localhost:8100/
#   ./scripts/generate-traffic.sh http://localhost:8100/ 100
set -euo pipefail

URL="${1:-http://localhost:8100/}"
TOTAL="${2:-50}"

echo "Gerando ${TOTAL} requisicoes para ${URL}"
ok=0
degraded=0
for i in $(seq 1 "$TOTAL"); do
  body="$(curl -s --max-time 5 "$URL" || true)"
  if printf '%s' "$body" | grep -q '"degraded":true'; then
    degraded=$((degraded + 1))
  elif [ -n "$body" ]; then
    ok=$((ok + 1))
  fi
  # Pequeno intervalo para distribuir os pontos no tempo (melhor visualizacao).
  sleep 0.2
done

echo "Concluido: ${ok} respostas normais, ${degraded} degradadas, total ${TOTAL}."
echo "Verifique as metricas em Prometheus (/metrics) e os traces na UI do Jaeger."
