# Evidencias - Passo 3 (validacao local do buffer e da sincronizacao)

Validacao executada localmente (sem cluster) do nucleo do Passo 3: modo degradado da
borda gravando eventos no buffer local, `scripts/sync.py` enviando ao `POST /sync` do
data-service e idempotencia por `event_id`. Data: 2026-06-28.

As evidencias de Kubernetes (namespace `edge`, NetworkPolicy bloqueando o trafego,
probes durante a instabilidade e Pushgateway local) estao no guia de reproducao em
[`reproduzir-no-cluster.md`](reproduzir-no-cluster.md), pois dependem de um cluster com
CNI que aplica `NetworkPolicy` (Calico/K3s).

## Como reproduzir localmente

```bash
source .venv/bin/activate
# 1) data-service central
PORT=8000 SYNC_STORE_PATH=./seen.txt python services/data-service/app.py &
# 2) gateway de borda apontando para um upstream morto -> forca offline + buffer
PORT=8200 DATA_SERVICE_URL=http://localhost:9999 DATA_SERVICE_TIMEOUT_SECONDS=1.0 \
  EDGE_BUFFER_PATH=./buffer.jsonl OTEL_SDK_DISABLED=true \
  python services/gateway-service/app.py &
curl localhost:8200/                 # resposta degradada + buffered_event_id
python scripts/sync.py --url http://localhost:8000 --buffer ./buffer.jsonl
```

## 1. Modo offline: gateway responde degradado e bufferiza (US-012)

`GET /` no gateway de borda com o central inacessivel responde HTTP 200 com
`degraded: true` e um `buffered_event_id` (sem 500 bruto):

```json
{"buffered_event_id":"323f715c-21e9-4c61-9eea-9631a01032ae","degraded":true,
 "reason":"data-service indisponivel (conexao bloqueada ou recusada)",
 "message":"resposta degradada: produtor central indisponivel ou lento",
 "data":null,"upstream":"http://localhost:9999/data","service":"gateway-service"}
```

Buffer local (`buffer.jsonl`) apos duas requisicoes, no contrato
`{event_id, timestamp, path, payload}`:

```json
{"event_id": "323f715c-21e9-4c61-9eea-9631a01032ae", "timestamp": "2026-06-28T14:36:04.296352+00:00", "path": "/", "payload": {"reason": "data-service indisponivel (conexao bloqueada ou recusada)", "method": "GET", "query": {}}}
{"event_id": "08a31b9b-37cb-4d67-9e34-3cba1982bf1e", "timestamp": "2026-06-28T14:36:04.320040+00:00", "path": "/", "payload": {"reason": "data-service indisponivel (conexao bloqueada ou recusada)", "method": "GET", "query": {}}}
```

Log do gateway gravando no buffer:

```text
WARNING in app: modo degradado: data-service indisponivel (conexao bloqueada ou recusada)
INFO in app: evento bufferizado localmente event_id=323f715c-... path=/ buffer=./buffer.jsonl
```

## 2. Latencia demonstrada separadamente da desconexao (FR-17, US-010)

Mesmo com o central ACESSIVEL, um produtor lento (`RESPONSE_DELAY_MS=1500`) acima do
timeout do gateway (`DATA_SERVICE_TIMEOUT_SECONDS=0.5`) gera modo degradado por
**timeout** (reason diferente do caso offline) e tambem bufferiza:

```json
{"buffered_event_id":"eda3d39d-3172-43bc-83d7-871fe399f6bd","degraded":true,
 "reason":"timeout ao chamar data-service","upstream":"http://localhost:8000/data"}
```

```text
WARNING in app: modo degradado: timeout ao chamar data-service
```

## 3. Sincronizacao apos reconexao (US-014)

`scripts/sync.py` le o buffer, envia ao `POST /sync` e remove do buffer apenas os
eventos reconhecidos pelo central:

```text
buffer ./buffer.jsonl: 2 linhas, 2 eventos validos, 0 invalidas
resposta do central: recebidos=2 aceitos=2 ignorados=0 invalidos=0 total_conhecidos=2
buffer atualizado: 2 reconhecidos removidos, 0 restantes.
```

Segunda execucao (buffer ja vazio):

```text
buffer ./buffer.jsonl: 0 linhas, 0 eventos validos, 0 invalidas
nada a sincronizar.
```

## 4. Idempotencia por event_id (US-014)

Reenviando os mesmos `event_id` (com `--keep` para nao limpar o buffer), o central
deduplica: o segundo envio cai todo em `ignorados` e `total_conhecidos` nao cresce.

```text
-- 1o envio: recebidos=2 aceitos=1 ignorados=1 invalidos=0 total_conhecidos=3
-- 2o envio: recebidos=2 aceitos=0 ignorados=2 invalidos=0 total_conhecidos=3
```

`event_id` persistidos no central (`seen.txt`), sem duplicatas:

```text
323f715c-21e9-4c61-9eea-9631a01032ae
08a31b9b-37cb-4d67-9e34-3cba1982bf1e
dup-1
```
