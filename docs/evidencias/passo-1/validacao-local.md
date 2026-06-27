# Evidencias - Passo 1 (validacao local)

Saidas reais capturadas durante o desenvolvimento do Passo 1. As evidencias de
pipeline verde, pods `Running/Ready` e `kubectl rollout status` devem ser
adicionadas apos a execucao no cluster com o self-hosted runner (prints/logs do
GitHub Actions e do `kubectl`).

## 1. data-service responde JSON valido

```text
$ curl -s localhost:8000/health/live
{"status":"alive"}
$ curl -s localhost:8000/health/ready
{"status":"ready"}
$ curl -s localhost:8000/data
{ "service": "data-service", "generated_at": "...", "delay_ms": 0,
  "items": [ {"id":1,"name":"sensor-temperatura","value":21.5,"unit":"C"}, ... ] }
```

## 2. gateway-service chama o data-service (caminho feliz)

```text
$ curl -s localhost:8100/
{"data":{"delay_ms":0,"items":[...],"service":"data-service"},
 "degraded":false,"service":"gateway-service","upstream":"http://localhost:8000/data"}
```

## 3. Modo degradado (timeout e indisponibilidade)

```text
# Produtor indisponivel (DATA_SERVICE_URL aponta para porta morta)
$ curl -s localhost:8101/
{"degraded":true,"reason":"data-service indisponivel","data":null, ...}

# Produtor lento: RESPONSE_DELAY_MS=1500 com DATA_SERVICE_TIMEOUT_SECONDS=1.0
$ curl -s localhost:8102/
{"degraded":true,"reason":"timeout ao chamar data-service","data":null, ...}
```

## 4. POST /sync idempotente

```text
$ curl -s -X POST localhost:8000/sync -H 'Content-Type: application/json' \
    -d '[{"event_id":"e1",...},{"event_id":"e2",...}]'
{"accepted":["e1","e2"],"ignored":[],"invalid":0,"received":2,"total_known":2}

# Reenvio: e1 ja conhecido -> ignorado; e3 novo -> aceito
$ curl -s -X POST localhost:8000/sync -H 'Content-Type: application/json' \
    -d '[{"event_id":"e1",...},{"event_id":"e3",...}]'
{"accepted":["e3"],"ignored":["e1"],"invalid":0,"received":2,"total_known":3}

# SYNC_STORE_PATH persistido (um event_id por linha):
e1
e2
e3
```

## 5. Docker build e run

```text
$ docker build -t data-service services/data-service     # OK
$ docker build -t gateway-service services/gateway-service  # OK

# Gateway em container alcanca o data-service pela rede Docker (DNS interno):
$ docker run -d --name ds --network cn data-service
$ docker run -d --name gw --network cn -p 8200:8000 -e DATA_SERVICE_URL=http://ds:8000 gateway-service
$ curl -s localhost:8200/
{"data":{...,"service":"data-service"},"degraded":false, ...}
```

## Execucao no cluster (concluida)

Todas as evidencias abaixo foram coletadas e estao em arquivos dedicados:

- [x] Build + push no GHCR -> [`ci-cd-github-actions.md`](ci-cd-github-actions.md)
- [x] Deploy automatico (self-hosted runner) -> [`ci-cd-github-actions.md`](ci-cd-github-actions.md)
- [x] `kubectl rollout status` dos dois Deployments -> [`deploy-kubernetes.md`](deploy-kubernetes.md)
- [x] Deployment usando a imagem com tag por SHA curto -> [`deploy-kubernetes.md`](deploy-kubernetes.md)
- [x] `kubectl get pods -n cloudnative` (Running/Ready) -> [`deploy-kubernetes.md`](deploy-kubernetes.md)
- [x] `kubectl get svc -n cloudnative` (ClusterIP) -> [`deploy-kubernetes.md`](deploy-kubernetes.md)
- [x] Requisicao ao gateway no cluster com dados do data-service -> [`deploy-kubernetes.md`](deploy-kubernetes.md)
