#!/usr/bin/env bash
# Restaura a conectividade da borda com o central (Passo 3), removendo a
# NetworkPolicy `edge-offline`. Sem a policy, o egress do gateway de borda volta a
# ser irrestrito e ele alcanca o data-service central novamente.
#
# Uso:
#   ./scripts/restore-connection.sh
set -euo pipefail

echo "== Removendo NetworkPolicy edge-offline =="
kubectl -n edge delete networkpolicy edge-offline --ignore-not-found

echo
echo "== Conectividade DEPOIS da restauracao (deve alcancar o central) =="
kubectl -n edge exec deploy/gateway-edge -c gateway-edge -- \
  python -c "import urllib.request;print('central OK ->', urllib.request.urlopen('http://data-service.cloudnative.svc.cluster.local:8000/health/ready', timeout=3).read().decode())" \
  || echo "  (central ainda inacessivel; verifique o data-service no namespace cloudnative)"

echo
echo "Conectividade restaurada. Sincronize o buffer local com:"
echo "  python scripts/sync.py --url http://localhost:8000 --buffer ./buffer.jsonl"
echo "(use port-forward do data-service ou rode o sync de dentro do cluster)"
