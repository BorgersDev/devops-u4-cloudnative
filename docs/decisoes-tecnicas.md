# Decisoes Tecnicas

Registro das escolhas e trade-offs. Atualizado conforme os passos avancam.

## Passo 1: Microsservicos, Containers, Kubernetes e CI/CD

### Stack
- **Python 3.12 + Flask** nos dois servicos, conforme decisao fixada no PRD.
  Flask e suficiente para APIs JSON simples e tem instrumentacao OpenTelemetry
  madura (relevante no Passo 2).
- **gunicorn com `--workers 1`**. Trade-off consciente: um unico worker limita o
  throughput, mas mantem o registro do `prometheus_client` consistente entre
  scrapes (Passo 2). Com varios workers seria preciso `PROMETHEUS_MULTIPROC_DIR`
  e o `MultiProcessCollector`, alem de inicializar o OpenTelemetry no hook
  `post_fork`. Para um laboratorio, um worker e mais simples e correto.

### Contrato de eventos
O evento bufferizado/sincronizado tem formato unico em todo o fluxo:
`{event_id, timestamp, path, payload}`. O `data-service` deduplica por
`event_id`, o que torna a idempotencia testavel de ponta a ponta. O `POST /sync`
aceita tanto uma lista crua quanto `{"events": [...]}` para facilitar o script
de sincronizacao do Passo 3.

### Idempotencia
Os `event_id` ja recebidos ficam em um `set` em memoria e, opcionalmente, sao
persistidos em `SYNC_STORE_PATH` (um id por linha). Persistir e barato e mantem
a deduplicacao mesmo apos reinicio do pod. Sem banco real, conforme escopo.

### Modo degradado do gateway
O `gateway-service` responde **HTTP 200 com `degraded: true`** em vez de
propagar 500 quando o produtor falha (conexao) ou estoura o timeout. Isso mantem
o gateway util ao cliente e prepara o terreno para a resiliencia de borda do
Passo 3 (buffer local). O timeout e configuravel por `DATA_SERVICE_TIMEOUT_SECONDS`.

### Kubernetes
- **Namespace `cloudnative`** isola a aplicacao principal.
- **`requests` e `limits`** em todos os containers: responsabilidade com
  recursos compartilhados e pre-requisito para evidencia de CPU no Passo 2.
- **Labels** `app`, `component`, `tier`, `part-of` consistentes entre Deployment,
  template e Service; selectors batem com `app`.
- **Services `ClusterIP`**: comunicacao interna entre microsservicos. O gateway
  resolve o produtor por DNS interno
  (`data-service.cloudnative.svc.cluster.local`).
- **Probes** em ambos os servicos usam endpoints locais (`/health/live`,
  `/health/ready`), sem dependencia do central. Os valores de borda mais
  tolerantes serao calibrados no Passo 3.

### CI/CD
- **GHCR** como registry: evita secrets externos alem do `GITHUB_TOKEN`.
- **Duas tags**: `latest` e **SHA curto**. Implantamos o SHA curto via
  `kubectl set image` para rastreabilidade (o Deployment mostra o commit exato).
- **Dois jobs**: build/push em runner hospedado pelo GitHub; deploy em
  **self-hosted runner** (label `k8s`) com acesso ao cluster local. Runners
  hospedados pelo GitHub nao alcancam um Minikube/K3s local, entao o self-hosted
  e o caminho para deploy automatico real, validado por `kubectl rollout status`.
- **imagePullSecret**: se as imagens GHCR forem privadas, criar um
  `imagePullSecret` no namespace e referencia-lo nos Deployments. Imagens
  publicas evitam esse passo e simplificam a atividade.

### Validacoes executadas no Passo 1
- `/data`, `/health/live`, `/health/ready` respondem JSON valido.
- Gateway retorna dados reais do produtor no caminho feliz.
- Modo degradado confirmado nos dois cenarios: produtor indisponivel e produtor
  lento acima do timeout.
- `POST /sync` aceita novos `event_id` e ignora repetidos (idempotencia), com
  persistencia em arquivo.
- `docker build` e `docker run` funcionam para os dois servicos; o gateway em
  container alcanca o data-service pela rede Docker.

## Passo 2: Observabilidade com Prometheus e Tracing com Jaeger

### Metricas (prometheus_client)
- **`/metrics`** nos dois servicos via `prometheus_client`, exposto no formato
  texto do Prometheus.
- **Contador `http_requests_total`** e **histograma
  `http_request_duration_seconds`** rotulados por `service`, `method`, `endpoint`
  (e `http_status` no contador), preenchidos por hooks `before_request`/
  `after_request`. O proprio `/metrics` e excluido para nao se auto-contar.
- **CPU**: `process_cpu_seconds_total` vem de graca do `ProcessCollector` padrao
  do `prometheus_client`, atendendo a evidencia de CPU sem componentes extras.
- O motivo de `gunicorn --workers 1` (ja fixado no Passo 1) se concretiza aqui:
  um unico registro do `prometheus_client`, sem valores divergentes entre scrapes.

### Coleta (Prometheus por annotations)
- **Annotations `prometheus.io/scrape|path|port`** nos pods da app. O Prometheus
  usa `kubernetes_sd_configs` (role `pod`, restrito ao namespace `cloudnative`) e
  `relabel_configs` para descobrir e raspar so os pods anotados, na porta 8000.
- **Sem Prometheus Operator**: usamos annotations + `kubernetes_sd_configs` em vez
  de `ServiceMonitor`, conforme a Technical Consideration do PRD. RBAC e somente
  leitura (`get/list/watch` de pods/services/endpoints/nodes).
- O Prometheus e instalado **a parte** (`k8s/observability/prometheus.yaml`), pois
  e infra de observabilidade, nao a aplicacao. O deploy da app permanece no
  pipeline. Armazenamento `emptyDir` (laboratorio).

### Tracing (OpenTelemetry + sidecar + Jaeger)
- **OpenTelemetry SDK** nos dois servicos: `FlaskInstrumentor` em ambos e
  `RequestsInstrumentor` no gateway, que propaga o contexto W3C `traceparent` ao
  data-service, gerando um **trace unico multi-servico**.
- **Inicializacao no `post_fork` do gunicorn** (`gunicorn.conf.py`): o
  `BatchSpanProcessor` sobe uma thread exportadora que **nao sobrevive ao fork**;
  inicializar no master perderia spans. Com `--workers 1`, um unico provider no
  worker. Validado pelos logs do sidecar mostrando spans chegando.
- **`OTEL_SERVICE_NAME`** distinto (`data-service` / `gateway-service`) separa os
  servicos no Jaeger. Export OTLP/gRPC para `http://localhost:4317` (o `http://`
  sinaliza canal inseguro, sem TLS).
- **Padrao sidecar (FR-15)**: cada pod da app tem o container do app **e** um
  `otel-collector` (imagem contrib oficial, multi-arch). O collector recebe OTLP
  em `localhost:4317/4318` e encaminha ao Service do Jaeger. A config do collector
  e um ConfigMap compartilhado, **aplicado pelo pipeline** antes dos Deployments
  (e montado como volume), para que o sidecar suba junto com a app.
- **Jaeger all-in-one** (`k8s/observability/jaeger.yaml`) com `COLLECTOR_OTLP_ENABLED=true`,
  expondo UI (16686) e OTLP (4317/4318). Armazenamento em memoria (laboratorio).

### setuptools fixado < 81
`opentelemetry-instrumentation` 0.48b0 ainda importa `pkg_resources`, removido no
`setuptools >= 81`. Sem o pin, o worker do gunicorn falhava ao bootar
(`ModuleNotFoundError: No module named 'pkg_resources'`). Fixamos `setuptools==80.9.0`.

### Validacoes executadas no Passo 2
- Build local das duas imagens com as novas dependencias; `/data`, `/metrics` e
  modo degradado confirmados antes do push.
- Pipeline verde (build multi-arch + deploy automatico), pods `2/2` (app +
  sidecar) na tag por SHA curto `9bbd924`.
- Prometheus com os dois targets `UP`; tres consultas PromQL com dados
  (`http_requests_total`, `http_request_duration_seconds`, `process_cpu_seconds_total`).
- Jaeger com trace multi-servico (`gateway-service GET /` -> `data-service GET /data`).

## Passo 3 (planejado)
Namespace `edge`, `NetworkPolicy` com CNI que aplica policy, simulacao de
latencia separada da desconexao, probes tolerantes, buffer local, observabilidade
offline e `scripts/sync.py` idempotente.
