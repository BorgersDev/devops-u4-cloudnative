#!/usr/bin/env bash
# Simula a QUEDA DE CONECTIVIDADE da borda com o central (Passo 3).
#
# Aplica a NetworkPolicy `edge-offline`, que bloqueia o egress do gateway de borda
# ate o namespace `cloudnative`. A partir dai, GET / no gateway de borda estoura o
# timeout, responde em modo degradado e grava o evento no buffer local.
#
# Pre-requisito: cluster com CNI que APLICA NetworkPolicy (Calico no Minikube ou K3s);
# caso contrario a policy e aceita mas nao bloqueia nada, invalidando a simulacao.
#
# Uso:
#   ./scripts/simulate-offline.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
POLICY="$ROOT/k8s/edge/networkpolicy.yaml"

echo "== Conectividade ANTES do bloqueio (deve alcancar o central) =="
kubectl -n edge exec deploy/gateway-edge -c gateway-edge -- \
  python -c "import urllib.request;print('central OK ->', urllib.request.urlopen('http://data-service.cloudnative.svc.cluster.local:8000/health/ready', timeout=3).read().decode())" \
  || echo "  (gateway de borda ainda nao esta pronto ou ja sem conectividade)"

echo
echo "== Aplicando NetworkPolicy edge-offline =="
kubectl apply -f "$POLICY"
kubectl -n edge get networkpolicy edge-offline

echo
echo "Conectividade bloqueada. O gateway de borda passa a responder em modo degradado"
echo "e a gravar eventos no buffer local (/data/buffer.jsonl)."
echo "Gere trafego com:  kubectl -n edge port-forward svc/gateway-edge 8200:8000 &"
echo "                   curl localhost:8200/"
echo "Restaure depois com: ./scripts/restore-connection.sh"
