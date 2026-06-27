# devops-u4-cloudnative

Arquitetura cloud-native com dois microsservicos Flask, conteinerizacao,
Kubernetes, CI/CD, observabilidade, tracing distribuido e simulacao de edge
computing. Entrega da atividade U4.

> Estado atual: **Passos 1 e 2 concluidos e comprovados de ponta a ponta**.
> Passo 1: pipeline verde (build multi-arch + push no GHCR), deploy automatico no
> Minikube (Calico) via self-hosted runner, pods `Running/Ready`, Services
> `ClusterIP`, Deployment usando a tag por SHA curto e chamada real ao gateway.
> Passo 2: `/metrics` nos dois servicos, Prometheus coletando por annotations com
> os dois targets `UP`, OpenTelemetry com sidecar `otel-collector` por pod e
> Jaeger exibindo trace multi-servico (`gateway-service` -> `data-service`).
> Evidencias em `docs/evidencias/passo-1/` e `docs/evidencias/passo-2/`.
> O Passo 3 (edge) e um incremento sobre esta base.

## Arquitetura

```text
usuario --> gateway-service (GET /) --HTTP--> data-service (GET /data)
                                              POST /sync (sincronizacao da borda)
```

- **data-service** (produtor): retorna dados simulados, suporta latencia
  controlada e recebe sincronizacoes idempotentes.
- **gateway-service** (consumidor): chama o `data-service` e formata a resposta,
  com timeout e modo degradado quando o produtor falha ou fica lento.

## Estrutura do repositorio

```text
services/        codigo, Dockerfile e gunicorn.conf.py de cada microsservico
k8s/             manifestos Kubernetes (namespace, deployments, services, observability)
scripts/         scripts de apoio (deploy local, generate-traffic; offline/sync no Passo 3)
docs/            decisoes tecnicas, etica e evidencias por passo
.github/workflows/deploy.yml   pipeline build + push + deploy
```

## Endpoints

### data-service
| Metodo | Rota            | Descricao                                                  |
|--------|-----------------|------------------------------------------------------------|
| GET    | `/data`         | Dados simulados. Latencia opcional via `?delay_ms=<n>` ou env `RESPONSE_DELAY_MS`. |
| POST   | `/sync`         | Recebe lista de eventos `{event_id, timestamp, path, payload}`; deduplica por `event_id`. |
| GET    | `/metrics`      | Metricas Prometheus (`http_requests_total`, `http_request_duration_seconds`, CPU). |
| GET    | `/health/live`  | Liveness.                                                  |
| GET    | `/health/ready` | Readiness.                                                 |

### gateway-service
| Metodo | Rota            | Descricao                                                  |
|--------|-----------------|------------------------------------------------------------|
| GET    | `/`             | Chama `DATA_SERVICE_URL` e formata a resposta. Modo degradado em falha/timeout. |
| GET    | `/metrics`      | Metricas Prometheus (`http_requests_total`, `http_request_duration_seconds`, CPU). |
| GET    | `/health/live`  | Liveness.                                                  |
| GET    | `/health/ready` | Readiness (nao depende do central).                        |

### Variaveis de ambiente
| Servico         | Variavel                        | Padrao                  | Uso                                  |
|-----------------|---------------------------------|-------------------------|--------------------------------------|
| data-service    | `RESPONSE_DELAY_MS`             | `0`                     | Latencia padrao do `/data`.          |
| data-service    | `SYNC_STORE_PATH`               | (vazio)                 | Arquivo para persistir `event_id`.   |
| gateway-service | `DATA_SERVICE_URL`              | `http://localhost:8000` | URL do produtor.                     |
| gateway-service | `DATA_SERVICE_TIMEOUT_SECONDS`  | `2.0`                   | Timeout da chamada ao produtor.      |
| ambos           | `OTEL_SERVICE_NAME`             | nome do servico         | `service.name` no tracing (Jaeger).  |
| ambos           | `OTEL_EXPORTER_OTLP_ENDPOINT`   | `http://localhost:4317` | Sidecar otel-collector (OTLP/gRPC).  |

## Execucao local

### Sem container
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r services/data-service/requirements.txt -r services/gateway-service/requirements.txt

# Terminal 1
PORT=8000 python services/data-service/app.py
# Terminal 2
PORT=8100 DATA_SERVICE_URL=http://localhost:8000 python services/gateway-service/app.py

curl localhost:8100/        # resposta com dados do produtor
```

### Com Docker
```bash
docker build -t data-service services/data-service
docker build -t gateway-service services/gateway-service

docker network create cn || true
docker run -d --name data --network cn -p 8000:8000 data-service
docker run -d --name gw --network cn -p 8100:8000 \
  -e DATA_SERVICE_URL=http://data:8000 gateway-service

curl localhost:8100/
```

Testar modo degradado:
```bash
# Timeout: produtor lento acima do timeout do gateway
curl "localhost:8000/data?delay_ms=1500"   # produtor demora
# (com DATA_SERVICE_TIMEOUT_SECONDS=1.0 o gateway responde degraded=true)
```

Testar idempotencia do `/sync`:
```bash
curl -X POST localhost:8000/sync -H 'Content-Type: application/json' \
  -d '[{"event_id":"e1","timestamp":"t","path":"/","payload":{}}]'
# Reenviar e1 -> aparece em "ignored", nunca duplica.
```

## Deploy no Kubernetes

Pre-requisito: cluster com CNI que aplica `NetworkPolicy` (necessario no Passo 3).
```bash
minikube start --cni=calico      # ou K3s
```

> **Atencao ao placeholder.** Os manifestos referenciam
> `ghcr.io/OWNER/devops-u4-cloudnative/<service>:latest`. Aplicar os YAMLs sem
> substituir `OWNER` gera `ImagePullBackOff` (a imagem nao existe). Use o script
> abaixo, que substitui `OWNER` (e opcionalmente a tag) antes do apply, ou deixe
> o pipeline trocar a imagem pela tag por SHA curto.

Deploy manual (substitui `OWNER` automaticamente):
```bash
./scripts/deploy-local.sh <owner> [tag]
# ex.: ./scripts/deploy-local.sh meu-usuario latest
```

Ou apply direto (lembre de trocar `OWNER` nos YAMLs antes):
```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/data-service/
kubectl apply -f k8s/gateway-service/

kubectl -n cloudnative get pods
kubectl -n cloudnative get svc       # ambos ClusterIP

# Testar o gateway via port-forward
kubectl -n cloudnative port-forward svc/gateway-service 8100:8000
curl localhost:8100/
```

## Observabilidade (Passo 2)

Metricas com Prometheus e tracing distribuido com OpenTelemetry + Jaeger. Cada pod
da aplicacao roda dois containers: o app e um **sidecar `otel-collector`** que
recebe spans em `localhost:4317` e os encaminha ao Jaeger.

Instalar o stack de observabilidade (uma vez; e infra, nao a aplicacao):
```bash
kubectl apply -f k8s/observability/otel-collector-config.yaml   # config do sidecar
kubectl apply -f k8s/observability/prometheus.yaml
kubectl apply -f k8s/observability/jaeger.yaml
kubectl -n cloudnative rollout status deployment/prometheus
kubectl -n cloudnative rollout status deployment/jaeger
```
> O ConfigMap `otel-collector-config` tambem e aplicado pelo pipeline antes dos
> Deployments, pois o sidecar o monta como volume e precisa dele para subir.

Gerar trafego e abrir as UIs:
```bash
kubectl -n cloudnative port-forward svc/gateway-service 8100:8000 &
kubectl -n cloudnative port-forward svc/prometheus 9090:9090 &
kubectl -n cloudnative port-forward svc/jaeger 16686:16686 &

./scripts/generate-traffic.sh http://localhost:8100/ 60

# Prometheus: http://localhost:9090/targets  (data-service e gateway-service UP)
#   PromQL: http_requests_total / http_request_duration_seconds_count / process_cpu_seconds_total
# Jaeger:   http://localhost:16686  (Service gateway-service, operacao GET /)
#   trace com spans de gateway-service e data-service
```

## CI/CD: estrategia de deploy automatico

`.github/workflows/deploy.yml` dispara em push para `main` e tem dois jobs:

1. **build-and-push** (runner `ubuntu-latest` hospedado pelo GitHub): builda as
   duas imagens e publica no **GHCR** com duas tags: `latest` e o **SHA curto**
   do commit. Usa apenas `GITHUB_TOKEN` com `permissions: packages: write`.
2. **deploy** (**self-hosted runner** com label `k8s`): aplica os manifestos,
   troca as imagens dos Deployments para a tag por SHA curto com
   `kubectl set image` e valida com `kubectl rollout status`.

**Por que self-hosted runner?** Um runner hospedado pelo GitHub nao alcanca um
Minikube/K3s local. Para deploy automatico real com `kubectl apply`, registra-se
um self-hosted runner na mesma maquina do cluster (ou um cluster acessivel
remotamente). Implantar a tag por **SHA curto** (e nao apenas `latest`) garante
rastreabilidade: o Deployment mostra exatamente qual commit esta rodando.

Registrar o self-hosted runner (na maquina do cluster):
```bash
# GitHub > Settings > Actions > Runners > New self-hosted runner
# Apos configurar, adicione o label "k8s" e garanta que o usuario do runner
# tenha um kubeconfig valido apontando para o cluster.
./run.sh
```

Imagens **publicas** no GHCR evitam `imagePullSecret`. Se forem privadas, crie um
`imagePullSecret` no namespace e referencie em `imagePullSecrets` (ver
`docs/decisoes-tecnicas.md`).

## Documentacao

- [`docs/decisoes-tecnicas.md`](docs/decisoes-tecnicas.md) - escolhas e trade-offs.
- [`docs/etica-e-principios.md`](docs/etica-e-principios.md) - etica aplicada.
- `docs/evidencias/passo-1/` - evidencias de build, deploy e execucao.
- `docs/evidencias/passo-2/` - evidencias de metricas (Prometheus), tracing (Jaeger) e sidecar.

## Seguranca

Nenhum secret, token ou kubeconfig e versionado. O pipeline usa o `GITHUB_TOKEN`
nativo. Veja `.gitignore`.
