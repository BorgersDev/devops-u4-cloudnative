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

## Passo 2 (planejado)
Metricas Prometheus (`/metrics`, contador, histograma), annotations de scrape,
OpenTelemetry SDK, sidecar OTel Collector e Jaeger.

## Passo 3 (planejado)
Namespace `edge`, `NetworkPolicy` com CNI que aplica policy, simulacao de
latencia separada da desconexao, probes tolerantes, buffer local, observabilidade
offline e `scripts/sync.py` idempotente.
