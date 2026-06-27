#!/usr/bin/env bash
# Deploy manual no cluster sem o pipeline.
#
# Os manifestos usam o placeholder ghcr.io/OWNER/... Este script substitui OWNER
# pelo dono real (e, opcionalmente, a tag) antes de aplicar, evitando
# ImagePullBackOff por imagem inexistente.
#
# Uso:
#   ./scripts/deploy-local.sh <owner> [tag]
# Exemplo:
#   ./scripts/deploy-local.sh borges-arthur latest
#   ./scripts/deploy-local.sh borges-arthur a1b2c3d
set -euo pipefail

OWNER="${1:?uso: ./scripts/deploy-local.sh <owner> [tag]}"
TAG="${2:-latest}"
OWNER_LC=$(printf '%s' "$OWNER" | tr '[:upper:]' '[:lower:]')

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

cp -R "$ROOT/k8s/." "$TMP/"

# Substitui OWNER e a tag :latest dos Deployments.
find "$TMP" -name '*.yaml' -print0 | while IFS= read -r -d '' f; do
  sed -i.bak "s#ghcr.io/OWNER/#ghcr.io/${OWNER_LC}/#g" "$f"
  sed -i.bak "s#\(devops-u4-cloudnative/[a-z-]*\):latest#\1:${TAG}#g" "$f"
  rm -f "${f}.bak"
done

kubectl apply -f "$TMP/namespace.yaml"
kubectl apply -f "$TMP/data-service/"
kubectl apply -f "$TMP/gateway-service/"

kubectl -n cloudnative rollout status deployment/data-service --timeout=120s
kubectl -n cloudnative rollout status deployment/gateway-service --timeout=120s
kubectl -n cloudnative get pods
kubectl -n cloudnative get svc
