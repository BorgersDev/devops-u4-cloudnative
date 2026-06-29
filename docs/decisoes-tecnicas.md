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

## Passo 3: Simulacao de Edge Computing

### Mesma imagem, comportamento por ambiente
O gateway de borda usa a **mesma imagem** do gateway central; o modo borda e ligado
por variaveis de ambiente, nao por um novo build:
- `EDGE_BUFFER_PATH` (vazio no central) ativa a gravacao no buffer local quando o
  gateway cai em modo degradado. Sem a variavel, o comportamento dos Passos 1 e 2
  fica intacto.
- `OTEL_SDK_DISABLED=true` desliga o tracing na borda, onde nao ha sidecar
  `otel-collector` nem Jaeger alcancavel. Sem isso, o exportador OTLP tentaria
  `localhost:4317` e geraria erros. O guard fica no `setup_tracing` do gateway.

### Buffer local e contrato de evento
No modo degradado (timeout, conexao bloqueada por `NetworkPolicy` ou erro do
central), o gateway gera **um `event_id` (uuid) por requisicao** e grava um evento
`{event_id, timestamp, path, payload}` em JSONL no buffer. O `event_id` e o que
viabiliza a deduplicacao idempotente no `POST /sync` (mesmo contrato do Passo 1). O
`payload` carrega apenas dados da requisicao (reason, method, query), nunca dados
pessoais (privacidade).

### Volume do buffer: hostPath
Preferimos **`hostPath`** (`/mnt/edge-buffer`, `DirectoryOrCreate`) a `emptyDir`
porque sobrevive a recriacao do pod, demonstrando melhor a resiliencia (o PRD nota
que `emptyDir` perde dados quando o pod e removido). No Minikube aponta para o
filesystem da VM/container do Minikube; inspecionavel com `minikube ssh`. Para uma
demo efemera, `emptyDir` serve.

### NetworkPolicy: bloqueio realista da desconexao
`k8s/edge/networkpolicy.yaml` (`edge-offline`) e uma policy de **egress allow-list**
sobre o pod `gateway-edge`: libera apenas DNS (kube-system:53) e o proprio namespace
`edge` (Pushgateway local), deixando o namespace `cloudnative` **sem rota**. Assim a
chamada ao central estoura o timeout e cai em modo degradado, em vez de falhar no
DNS. Aplicada por `scripts/simulate-offline.sh` e removida por
`scripts/restore-connection.sh`. **Requer CNI que aplica policy** (Calico/K3s); o CNI
padrao do Minikube aceitaria a policy sem bloquear nada, invalidando a simulacao.

### Latencia separada da desconexao
Sao dois cenarios distintos e ambos bufferizam, com `reason` diferente:
- **Latencia**: produtor lento (`RESPONSE_DELAY_MS` no central) acima do
  `DATA_SERVICE_TIMEOUT_SECONDS=1.0` do gateway de borda -> `reason: timeout`.
- **Desconexao**: `NetworkPolicy` bloqueando o central -> `reason: conexao
  bloqueada/recusada`.

### Probes tolerantes (justificativa dos valores)
- **liveness** (`/health/live`, `periodSeconds: 15`, `failureThreshold: 6`): so
  verifica o processo local, **nao depende do central**. Tolera ~90s de instabilidade
  antes de reiniciar, evitando restart desnecessario em quedas curtas.
- **readiness** (`/health/ready`, `periodSeconds: 10`, `failureThreshold: 3`):
  retorna pronto **mesmo em modo degradado**, pois o gateway atende localmente e
  bufferiza. O pod permanece `Ready` durante o offline, refletindo autonomia local.
  Readiness de borda nao deve depender exclusivamente do central.

### Observabilidade offline: Pushgateway local
`k8s/edge/pushgateway.yaml` roda **dentro do namespace `edge`**, entao continua
acessivel mesmo com a `NetworkPolicy` bloqueando a saida ao central. O gateway envia
o acumulado de eventos bufferizados como Gauge `edge_buffered_events_total`. Limitacao
consciente: o Pushgateway **apenas retem o ultimo valor por job** ate ser raspado por
um Prometheus apos a reconexao, nao mantem historico. Falha de push e tolerada; o
**log local** do container e a evidencia minima offline (alternativa mais simples, no
espirito do PRD).

### Sincronizacao idempotente (`scripts/sync.py`)
Le o buffer JSONL, envia em lote ao `POST /sync` e, **so apos sucesso**, remove do
buffer os eventos reconhecidos (`accepted` + `ignored`). Usa apenas `urllib` (stdlib)
para rodar no host sem dependencias. Reexecucoes nao duplicam: o central deduplica por
`event_id`, entao um reenvio cai todo em `ignored`. Comprovado em
`docs/evidencias/passo-3/validacao-local.md`.

### Validacoes executadas no Passo 3
- Buffer gravado nos dois cenarios (offline e latencia), com `event_id` por
  requisicao e contrato `{event_id, timestamp, path, payload}`.
- `sync.py` enviando ao central, removendo do buffer e sendo idempotente em
  reexecucao (segundo envio inteiro em `ignored`, `total_known` estavel).
- Comprovado no cluster (Minikube + Calico): `NetworkPolicy` bloqueando o central
  (chamada direta da borda da timeout), modo degradado, buffer no `hostPath`, probes
  mantendo o pod `Ready` sem restart, Pushgateway retendo `edge_buffered_events_total`
  e sync idempotente. Evidencia em `docs/evidencias/passo-3/validacao-cluster.md`;
  buffer/sync/idempotencia tambem em `validacao-local.md` e o passo a passo em
  `reproduzir-no-cluster.md`.
