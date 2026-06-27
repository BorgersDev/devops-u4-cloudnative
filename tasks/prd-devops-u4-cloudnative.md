# PRD: Arquitetura Cloud-Native com Microsservicos, Observabilidade e Edge Computing

> Repositorio alvo: `devops-u4-cloudnative`
> Atividade U4: conteinerizacao avancada, Kubernetes, CI/CD, observabilidade, tracing distribuido e simulacao de edge computing.

## Status De Execucao

- **Passo 1 (Microsservicos, Containers, Kubernetes e CI/CD): CONCLUIDO e comprovado de ponta a ponta.**
  - Repo publico: https://github.com/BorgersDev/devops-u4-cloudnative
  - Pipeline `build-and-deploy` verde (build multi-arch + push GHCR + deploy automatico).
  - Cluster Minikube com Calico; deploy pelo self-hosted runner (label `k8s`).
  - Pods `Running/Ready`, Services `ClusterIP`, Deployments na tag por SHA curto, gateway respondendo com dados do data-service.
  - Evidencias em `docs/evidencias/passo-1/` (`ci-cd-github-actions.md`, `deploy-kubernetes.md`, `validacao-local.md`).
- **Passo 2 (Observabilidade e Tracing): PENDENTE.**
- **Passo 3 (Edge Computing): PENDENTE.**

## 1. Introducao / Visao Geral

Esta atividade constroi um cenario cloud-native integrado de ponta a ponta. O projeto deve conter dois microsservicos Flask conteinerizados, deployados em Kubernetes, publicados por pipeline de CI/CD no GitHub Actions, observados com Prometheus e Jaeger/OpenTelemetry e adaptados para uma simulacao de execucao em borda com conectividade instavel.

O objetivo pedagogico e demonstrar, em um unico repositorio, os pilares de DevOps moderno: conteinerizacao, orquestracao, entrega continua, observabilidade, tracing distribuido, padrao sidecar, resiliencia local e sincronizacao posterior em ambiente distribuido.

## 2. Escopo Da Entrega

### Decisoes Tecnicas Fixadas

- Stack principal: Python 3.12 + Flask para os dois microsservicos.
- Microsservico produtor: `data-service`, responsavel por retornar dados simulados e receber sincronizacoes da borda.
- Microsservico consumidor: `gateway-service`, responsavel por receber a requisicao do usuario, chamar o `data-service` e formatar a resposta.
- Registry de imagens: GitHub Container Registry (`ghcr.io`) para evitar dependencia de secrets externos alem do `GITHUB_TOKEN`.
- Cluster principal: Minikube local com Calico (`minikube start --cni=calico`) ou K3s. Play with Kubernetes so deve ser usado se houver evidencia de que `NetworkPolicy` e aplicada.
- Deploy principal: manifestos Kubernetes YAML aplicados com `kubectl apply`.
- Deploy automatizado real: GitHub Actions com self-hosted runner conectado ao cluster local ou cluster Kubernetes acessivel remotamente. O workflow deve aplicar manifests, atualizar imagens pela tag do commit e validar `rollout status`.
- Observabilidade: Prometheus instalado no cluster, coletando pods por annotations.
- Tracing: OpenTelemetry SDK nas aplicacoes e OpenTelemetry Collector sidecar nos pods, exportando spans para Jaeger.
- Edge: simulacao com namespace `edge` isolado por `NetworkPolicy`, restricao de latencia, probes tolerantes, buffer local e script de sincronizacao posterior.

### Fora Do Escopo

- Nao usar cloud gerenciada como EKS, GKE ou AKS.
- Nao implementar frontend completo. HTML simples ou JSON formatado e suficiente.
- Nao implementar autenticacao, autorizacao ou TLS de producao.
- Nao usar banco de dados real. Os dados podem ser simulados em memoria e o buffer pode ser baseado em arquivo.
- Nao tornar Helm ou Kustomize obrigatorios. Eles podem ser citados como melhoria opcional.

## 3. Estrutura Sugerida Do Repositorio

```text
devops-u4-cloudnative/
+-- services/
|   +-- data-service/
|   |   +-- app.py
|   |   +-- requirements.txt
|   |   +-- Dockerfile
|   |   +-- .dockerignore
|   +-- gateway-service/
|       +-- app.py
|       +-- requirements.txt
|       +-- Dockerfile
|       +-- .dockerignore
+-- k8s/
|   +-- data-service/
|   |   +-- deployment.yaml
|   |   +-- service.yaml
|   +-- gateway-service/
|   |   +-- deployment.yaml
|   |   +-- service.yaml
|   +-- observability/
|   |   +-- prometheus.yaml
|   |   +-- jaeger.yaml
|   +-- edge/
|       +-- namespace.yaml
|       +-- networkpolicy.yaml
|       +-- gateway-edge-deployment.yaml
|       +-- gateway-edge-service.yaml
|       +-- pushgateway.yaml
+-- scripts/
|   +-- generate-traffic.sh
|   +-- simulate-offline.sh
|   +-- restore-connection.sh
|   +-- sync.py
+-- docs/
|   +-- decisoes-tecnicas.md
|   +-- etica-e-principios.md
|   +-- evidencias/
|       +-- passo-1/
|       +-- passo-2/
|       +-- passo-3/
+-- .github/workflows/
|   +-- deploy.yml
+-- README.md
```

## 4. Plano De Execucao Passo A Passo

### Preparacao

1. Criar o repositorio `devops-u4-cloudnative` no GitHub.
2. Instalar ou escolher o ambiente Kubernetes. Para a entrega principal, usar Minikube com Calico ou K3s.
3. Subir o cluster com um CNI que aplique `NetworkPolicy`. No Minikube use `minikube start --cni=calico`, pois o CNI padrao aceita a policy mas nao a aplica, o que invalidaria a simulacao de borda do Passo 3. K3s ja aplica policies por padrao.
4. Definir o namespace principal da aplicacao, por exemplo `cloudnative`.
5. Configurar acesso ao GHCR no GitHub Actions com `permissions: packages: write`.
6. Registrar um self-hosted runner na maquina que executa o cluster, ou usar um cluster Kubernetes acessivel remotamente pelo GitHub Actions. Esse e o caminho principal para cumprir deploy automatizado.
7. Definir que as imagens serao publicadas com tag por SHA curto e `latest`, e que o deploy usara a tag por SHA curto para rastreabilidade.
8. Criar `docs/evidencias/` desde o inicio para armazenar prints e logs por passo.
9. Criar `docs/etica-e-principios.md` para registrar as decisoes eticas e seu impacto pratico na entrega.

### Passo 1: Microsservicos, Containers, Kubernetes E CI/CD

#### Objetivo

Criar dois microsservicos, empacotar cada um em uma imagem Docker, publicar as imagens e fazer deploy no Kubernetes com pipeline automatizado.

#### Atividades

1. Criar o `data-service` em Flask.
2. Implementar `GET /data`, retornando JSON com dados simulados.
3. Implementar suporte de latencia controlada no `GET /data`, por exemplo via query `delay_ms` ou variavel `RESPONSE_DELAY_MS`, para permitir teste do Passo 3.
4. Implementar `GET /health/live` e `GET /health/ready`.
5. Implementar `POST /sync` no `data-service` para receber eventos enviados posteriormente pelo script da borda.
6. Criar o `gateway-service` em Flask.
7. Implementar `GET /`, chamando `DATA_SERVICE_URL` e retornando uma resposta formatada.
8. Configurar timeout de chamada ao produtor via `DATA_SERVICE_TIMEOUT_SECONDS`.
9. Implementar tratamento gracioso quando o `data-service` estiver indisponivel ou lento acima do timeout.
10. Criar `Dockerfile` e `.dockerignore` para cada servico.
11. Rodar os containers localmente para validar portas e variaveis de ambiente.
12. Criar `deployment.yaml` e `service.yaml` para os dois servicos.
13. Definir `resources.requests` e `resources.limits` em cada Deployment.
14. Definir labels consistentes, por exemplo `app`, `component`, `tier` e `part-of`.
15. Usar `Service` do tipo `ClusterIP` para comunicacao interna entre os microsservicos.
16. Criar `.github/workflows/deploy.yml`.
17. No workflow, buildar as duas imagens, publicar no GHCR, aplicar os YAMLs com `kubectl apply`, atualizar a tag da imagem com `kubectl set image` ou Kustomize e validar `kubectl rollout status`.
18. Registrar evidencias do pipeline verde, dos pods prontos, da tag implantada e de uma chamada bem sucedida ao gateway.

#### Criterios De Aceite

- [x] `data-service` responde `GET /data` com JSON valido.
- [x] `data-service` permite simular latencia controlada para testar timeout e modo degradado.
- [x] `gateway-service` chama o `data-service` usando a variavel `DATA_SERVICE_URL`.
- [x] `gateway-service` usa `DATA_SERVICE_TIMEOUT_SECONDS` para evitar travar em chamadas lentas.
- [x] Ambos os servicos possuem `GET /health/live` e `GET /health/ready`.
- [x] Ambos os servicos possuem Dockerfile baseado em imagem leve, como `python:3.12-slim`.
- [x] As imagens sao publicadas no `ghcr.io/<owner>/devops-u4-cloudnative/<service>:<tag>`.
- [x] Os Deployments possuem `requests`, `limits`, labels e selectors coerentes.
- [x] Os Services sao `ClusterIP`.
- [x] O pipeline `deploy.yml` executa build, push e deploy automatico no cluster.
- [x] O pipeline atualiza as imagens dos Deployments com a tag do commit e valida `kubectl rollout status`.
- [x] O README explica a estrategia usada para o deploy automatico no cluster escolhido.

#### Evidencias Esperadas

- Print ou log do GitHub Actions com sucesso no build e push.
- Print ou log do GitHub Actions com sucesso no deploy automatico.
- Print ou log do `kubectl rollout status` executado pelo workflow.
- Print ou log do Deployment usando a imagem com tag por SHA curto.
- Saida de `kubectl get pods -n cloudnative` com os pods `Running` e `Ready`.
- Saida de `kubectl get svc -n cloudnative` mostrando os Services `ClusterIP`.
- Print ou log de uma requisicao ao `gateway-service` retornando dados vindos do `data-service`.

### Passo 2: Observabilidade Com Prometheus E Tracing Com Jaeger

#### Objetivo

Adicionar metricas e tracing distribuido aos microsservicos para acompanhar requisicoes, latencias e fluxo entre servicos.

#### Atividades

1. Adicionar `prometheus_client` aos dois servicos.
2. Expor `GET /metrics` em ambos os servicos.
3. Criar contador de requisicoes HTTP, por exemplo `http_requests_total`.
4. Criar histograma de latencia, por exemplo `http_request_duration_seconds`.
5. Adicionar annotations nos pods: `prometheus.io/scrape`, `prometheus.io/path` e `prometheus.io/port`.
6. Instalar o Prometheus no cluster usando YAML proprio ou chart documentado.
7. Configurar o Prometheus para descobrir pods por annotations com `kubernetes_sd_configs`.
8. Acessar a UI do Prometheus com `kubectl port-forward`.
9. Validar targets `UP` e metricas dos dois servicos.
10. Registrar consultas PromQL para evidencias: `http_requests_total`, `http_request_duration_seconds` e CPU por `process_cpu_seconds_total` ou `container_cpu_usage_seconds_total` quando disponivel.
11. Adicionar OpenTelemetry SDK aos dois servicos.
12. Instrumentar Flask e requests para propagar contexto via header W3C `traceparent`.
13. Adicionar um OpenTelemetry Collector sidecar em cada Deployment da aplicacao.
14. Configurar os apps para exportar spans para o sidecar em `localhost:4317` ou `localhost:4318`.
15. Configurar cada sidecar para encaminhar spans ao Jaeger no cluster.
16. Instalar Jaeger all-in-one no cluster, expondo coletor OTLP e UI.
17. Gerar trafego com `scripts/generate-traffic.sh`.
18. Acessar a UI do Jaeger com `kubectl port-forward` e localizar um trace completo envolvendo `gateway-service` e `data-service`.
19. Registrar evidencia de que cada pod da aplicacao possui pelo menos dois containers: app e `otel-collector` sidecar.

#### Criterios De Aceite

- [ ] Ambos os servicos expoem `GET /metrics` no formato Prometheus.
- [ ] Prometheus mostra targets dos dois servicos como `UP`.
- [ ] Prometheus exibe contador de requisicoes, histograma de latencia e metrica de CPU.
- [ ] Os pods possuem sidecar de OpenTelemetry Collector ou agent equivalente.
- [ ] `gateway-service` e `data-service` usam nomes de servico distintos em `OTEL_SERVICE_NAME`.
- [ ] Uma chamada ao gateway gera um trace unico com spans dos dois servicos.
- [ ] Jaeger UI mostra tempo por etapa e relacionamento entre os spans.

#### Evidencias Esperadas

- Print da pagina de targets do Prometheus com os servicos `UP`.
- Print de uma consulta PromQL usando `http_requests_total`.
- Print de uma consulta PromQL usando `http_request_duration_seconds`.
- Print de uma consulta PromQL usando `process_cpu_seconds_total` ou `container_cpu_usage_seconds_total`.
- Print ou log mostrando os containers `app` e `otel-collector` no mesmo pod.
- Print da UI do Jaeger com trace completo multi-servico.
- Log ou print do script de geracao de trafego.

### Passo 3: Simulacao De Edge Computing Com Latencia E Conectividade Restrita

#### Objetivo

Simular a execucao do `gateway-service` em ambiente de borda, mantendo funcionamento local durante indisponibilidade do ambiente central e sincronizando dados quando a conexao for restabelecida.

#### Atividades

1. Criar namespace `edge`.
2. Deployar uma variante do `gateway-service` no namespace `edge`.
3. Configurar `NetworkPolicy` para restringir acesso ao namespace principal e simular queda de conectividade.
4. Simular latencia configurando delay no `data-service` acima de `DATA_SERVICE_TIMEOUT_SECONDS` do gateway de borda.
5. Adicionar probes no Deployment de borda.
6. Configurar `livenessProbe` para verificar somente se o processo esta vivo.
7. Configurar `readinessProbe` para verificar se o servico consegue atender localmente, mesmo em modo degradado.
8. Montar volume local para buffer, preferencialmente `hostPath` ou PVC se o ambiente permitir. `emptyDir` pode ser usado apenas para demonstracao temporaria.
9. Adaptar o `gateway-service` para, ao detectar falha, bloqueio ou timeout no `data-service`, registrar eventos ou payloads em arquivo local.
10. Configurar log rotativo local ou Pushgateway local no namespace `edge` para simular observabilidade parcial offline.
11. Criar `scripts/simulate-offline.sh` para aplicar ou alterar a `NetworkPolicy` e bloquear o caminho ate o ambiente central.
12. Criar `scripts/restore-connection.sh` para restaurar a conectividade.
13. Criar `scripts/sync.py` para ler o buffer local e enviar eventos ao `POST /sync` do `data-service`.
14. Tornar a sincronizacao idempotente usando um `event_id` por registro.
15. Gerar evidencias do gateway respondendo em modo degradado por latencia, offline por bloqueio de rede, das probes durante a instabilidade e da sincronizacao apos reconexao.
16. Documentar os ajustes feitos para resiliencia e autonomia local.

#### Criterios De Aceite

- [ ] Namespace `edge` criado.
- [ ] `gateway-service` roda no namespace `edge`.
- [ ] `NetworkPolicy` simula conectividade restrita com o ambiente central.
- [ ] Latencia e simulada com delay no produtor ou timeout controlado no gateway, gerando modo degradado sem derrubar o pod.
- [ ] Liveness e readiness probes estao configuradas com `initialDelaySeconds`, `periodSeconds`, `timeoutSeconds` e `failureThreshold` justificados em comentario ou documento.
- [ ] Gateway continua respondendo quando o `data-service` central fica indisponivel.
- [ ] Eventos sao gravados em buffer local durante o modo offline.
- [ ] Observabilidade offline e demonstrada com Pushgateway local ou log rotativo local.
- [ ] `scripts/sync.py` envia dados ao ambiente central apos reconexao.
- [ ] A sincronizacao nao duplica eventos ja enviados.
- [ ] README ou documento em `docs/` explica as decisoes de resiliencia da borda.

#### Evidencias Esperadas

- Saida de `kubectl get pods -n edge` mostrando o gateway de borda pronto.
- Print ou log da `NetworkPolicy` ativa bloqueando o acesso ao central.
- Print ou log de uma requisicao com latencia acima do timeout resultando em resposta degradada controlada.
- Print ou log do gateway respondendo em modo degradado.
- Log mostrando gravacao de eventos no buffer local.
- Print ou log das probes durante a instabilidade.
- Log do `scripts/sync.py` enviando eventos apos restaurar conexao.
- Print ou log no `data-service` confirmando recebimento dos eventos sincronizados.

## 5. User Stories

### US-001: Criar O Microsservico Produtor

**Descricao:** Como desenvolvedor, quero um `data-service` que exponha dados por API para que outros servicos possam consumir informacoes simuladas.

**Acceptance Criteria:**

- [x] `services/data-service/app.py` contem app Flask funcional.
- [x] `GET /data` retorna JSON valido.
- [x] `GET /data` permite simular latencia controlada por `delay_ms` ou `RESPONSE_DELAY_MS` para testar timeout do gateway.
- [x] `POST /sync` recebe uma lista de eventos no formato `{event_id, timestamp, path, payload}` e responde com o resumo de aceitos e ignorados.
- [x] `POST /sync` mantem o conjunto de `event_id` ja recebidos (em memoria ou arquivo) e ignora repetidos, garantindo idempotencia.
- [x] `GET /health/live` retorna status vivo.
- [x] `GET /health/ready` retorna status pronto.
- [x] `requirements.txt` fixa dependencias necessarias.

### US-002: Criar O Microsservico Consumidor

**Descricao:** Como usuario, quero acessar o `gateway-service` para receber uma resposta formatada a partir dos dados do `data-service`.

**Acceptance Criteria:**

- [x] `services/gateway-service/app.py` contem app Flask funcional.
- [x] `GET /` chama o `data-service` via `DATA_SERVICE_URL`.
- [x] `GET /` usa timeout configuravel via `DATA_SERVICE_TIMEOUT_SECONDS`.
- [x] A resposta e exibida como JSON enriquecido ou HTML simples.
- [x] Falhas de conexao, bloqueio por policy ou latencia acima do timeout geram resposta degradada controlada.
- [x] `GET /health/live` e `GET /health/ready` estao disponiveis.

### US-003: Conteinerizar Os Servicos

**Descricao:** Como desenvolvedor, quero imagens Docker reproduziveis para executar os microsservicos em qualquer ambiente compativel.

**Acceptance Criteria:**

- [x] Cada servico possui `Dockerfile` proprio.
- [x] Cada servico possui `.dockerignore`.
- [x] As imagens usam base leve, como `python:3.12-slim`.
- [x] Os containers rodam com servidor adequado para container, como `gunicorn`.
- [x] O `gunicorn` roda com `--workers 1` na entrega, para manter o registro do `prometheus_client` consistente entre scrapes. Se mais de um worker for necessario, o modo multiprocess do `prometheus_client` deve ser configurado via `PROMETHEUS_MULTIPROC_DIR`.
- [x] `docker build` e `docker run` funcionam para os dois servicos.

### US-004: Orquestrar No Kubernetes

**Descricao:** Como operador, quero manifestos Kubernetes para subir os dois servicos no cluster com comunicacao interna.

**Acceptance Criteria:**

- [x] `k8s/data-service/deployment.yaml` e `service.yaml` existem.
- [x] `k8s/gateway-service/deployment.yaml` e `service.yaml` existem.
- [x] Deployments usam `resources.requests` e `resources.limits`.
- [x] Labels e selectors sao consistentes.
- [x] Services sao `ClusterIP`.
- [x] O gateway resolve o produtor por DNS interno do Kubernetes.

### US-005: Automatizar Build, Push E Deploy

**Descricao:** Como desenvolvedor, quero que commits no repositorio acionem build, publicacao de imagens e deploy no cluster.

**Acceptance Criteria:**

- [x] `.github/workflows/deploy.yml` dispara em push para `main`.
- [x] Workflow builda as duas imagens.
- [x] Workflow publica as imagens no GHCR com tag por SHA curto e `latest`.
- [x] Workflow usa self-hosted runner ou cluster acessivel para aplicar os manifestos com `kubectl apply`.
- [x] Workflow atualiza as imagens implantadas com a tag por SHA curto usando `kubectl set image` ou Kustomize.
- [x] Workflow executa `kubectl rollout status` para os dois Deployments.
- [x] README documenta a estrategia de acesso ao cluster usada pelo pipeline.

### US-006: Expor Metricas Prometheus

**Descricao:** Como SRE, quero metricas padrao Prometheus nos servicos para monitorar carga, saude e latencia.

**Acceptance Criteria:**

- [ ] Ambos os servicos expoem `GET /metrics`.
- [ ] Existe contador `http_requests_total` ou equivalente.
- [ ] Existe histograma `http_request_duration_seconds` ou equivalente.
- [ ] Existe metrica de CPU do processo ou do container disponivel para evidencia.
- [ ] Pods possuem annotations de scrape do Prometheus.

### US-007: Instalar Prometheus No Cluster

**Descricao:** Como SRE, quero Prometheus rodando no Kubernetes e coletando metricas automaticamente dos pods.

**Acceptance Criteria:**

- [ ] `k8s/observability/prometheus.yaml` existe ou o uso de Helm esta documentado.
- [ ] Prometheus descobre pods por annotations.
- [ ] UI do Prometheus e acessivel via `kubectl port-forward`.
- [ ] Targets dos dois microsservicos aparecem como `UP`.

### US-008: Instrumentar Tracing Com OpenTelemetry

**Descricao:** Como desenvolvedor, quero spans distribuidos para rastrear o caminho de uma requisicao entre gateway e produtor.

**Acceptance Criteria:**

- [ ] OpenTelemetry SDK esta configurado nos dois servicos.
- [ ] Flask e requests estao instrumentados.
- [ ] Contexto de trace e propagado via `traceparent`.
- [ ] `OTEL_SERVICE_NAME` diferencia `gateway-service` e `data-service`.
- [ ] Apps exportam spans para o sidecar OpenTelemetry Collector.
- [ ] O manifesto de cada app demonstra o padrao sidecar com container da aplicacao e container `otel-collector` no mesmo pod.

### US-009: Instalar Jaeger E Visualizar Trace Completo

**Descricao:** Como SRE, quero Jaeger no cluster para visualizar traces completos e latencias entre os servicos.

**Acceptance Criteria:**

- [ ] `k8s/observability/jaeger.yaml` existe ou o uso de Helm esta documentado.
- [ ] Jaeger recebe spans via OTLP.
- [ ] UI do Jaeger e acessivel via `kubectl port-forward`.
- [ ] Uma requisicao ao gateway gera trace com spans de ambos os servicos.

### US-010: Simular Ambiente De Borda

**Descricao:** Como engenheiro de edge, quero rodar o gateway em ambiente isolado para simular execucao descentralizada.

**Acceptance Criteria:**

- [ ] Namespace `edge` existe.
- [ ] Gateway possui Deployment especifico para borda.
- [ ] O cluster usa um CNI que aplica `NetworkPolicy` (Calico no Minikube ou K3s) e ha evidencia de que a policy realmente bloqueia o trafego.
- [ ] NetworkPolicy restringe comunicacao com o central.
- [ ] Ha evidencia separada de restricao por latencia, usando delay no produtor acima do timeout do gateway.
- [ ] A alternativa com K3s e documentada como opcional.

### US-011: Configurar Probes Tolerantes

**Descricao:** Como engenheiro de edge, quero sondas que tolerem instabilidade sem reiniciar o servico desnecessariamente.

**Acceptance Criteria:**

- [ ] `livenessProbe` usa endpoint local e nao depende do central.
- [ ] `readinessProbe` confirma capacidade de atender em modo normal ou degradado.
- [ ] Tempos e thresholds estao ajustados para quedas curtas.
- [ ] A justificativa dos valores esta documentada.

### US-012: Implementar Buffer Local Offline

**Descricao:** Como engenheiro de edge, quero armazenar eventos localmente quando nao houver conectividade com o central.

**Acceptance Criteria:**

- [ ] Deployment de borda monta volume para buffer.
- [ ] Gateway detecta timeout ou erro de conexao com o central.
- [ ] Ao receber uma requisicao em modo offline, o gateway grava no buffer um evento `{event_id (uuid), timestamp, path, payload}`.
- [ ] O `event_id` e gerado uma unica vez por requisicao e e o que viabiliza a deduplicacao no `POST /sync`.
- [ ] Gateway continua retornando resposta controlada ao usuario.

### US-013: Simular Observabilidade Offline

**Descricao:** Como SRE de edge, quero reter informacoes locais de observabilidade durante desconexao temporaria.

**Acceptance Criteria:**

- [ ] Pushgateway local ou log rotativo local esta configurado.
- [ ] A escolha e documentada com limitacoes, incluindo que o Pushgateway apenas retem metricas ate ser raspado por um Prometheus apos a reconexao.
- [ ] Ha evidencia de metricas ou logs sendo retidos offline.

### US-014: Sincronizar Dados Apos Reconexao

**Descricao:** Como engenheiro de edge, quero enviar dados bufferizados ao central quando a conexao voltar.

**Acceptance Criteria:**

- [ ] `scripts/sync.py` le o buffer local de eventos `{event_id, timestamp, path, payload}`.
- [ ] Script envia os eventos ao `POST /sync` do `data-service` ou endpoint mock documentado.
- [ ] Script marca eventos sincronizados ou os remove apenas apos resposta de sucesso.
- [ ] Rodadas repetidas nao duplicam eventos no central, pois o `data-service` deduplica por `event_id`.

### US-015: Documentar Decisoes E Evidencias

**Descricao:** Como avaliador, quero consultar documentacao e evidencias para validar a execucao completa da atividade.

**Acceptance Criteria:**

- [ ] README possui instrucoes de execucao local, Kubernetes, observabilidade e edge.
- [ ] `docs/decisoes-tecnicas.md` descreve escolhas e trade-offs.
- [ ] `docs/etica-e-principios.md` descreve responsabilidade, colaboracao, bem comum, seguranca de secrets, uso consciente de recursos e transparencia das evidencias.
- [ ] `docs/evidencias/passo-1/` contem evidencias de build, deploy e execucao.
- [ ] `docs/evidencias/passo-2/` contem evidencias de Prometheus e Jaeger.
- [ ] `docs/evidencias/passo-3/` contem evidencias de offline, probes, buffer e sync.

## 6. Functional Requirements

- FR-1: O sistema deve conter dois microsservicos Flask independentes: `data-service` e `gateway-service`.
- FR-2: O `data-service` deve expor `GET /data`, `POST /sync`, `GET /health/live`, `GET /health/ready` e `GET /metrics`.
- FR-3: O `gateway-service` deve expor `GET /`, `GET /health/live`, `GET /health/ready` e `GET /metrics`.
- FR-4: O `gateway-service` deve chamar o `data-service` via HTTP usando `DATA_SERVICE_URL`.
- FR-5: O `data-service` deve permitir simulacao de latencia controlada para validar timeout e modo degradado.
- FR-6: O `gateway-service` deve usar timeout configuravel via `DATA_SERVICE_TIMEOUT_SECONDS`.
- FR-7: Cada servico deve ter Dockerfile proprio e imagem publicada no GHCR.
- FR-8: Cada servico deve possuir Deployment e Service Kubernetes.
- FR-9: Cada Deployment deve declarar requests, limits, labels e selectors consistentes.
- FR-10: Cada Service da aplicacao deve ser do tipo `ClusterIP`.
- FR-11: O workflow `deploy.yml` deve buildar, publicar imagens, aplicar manifestos, atualizar imagens implantadas com tag por SHA curto e validar `rollout status`.
- FR-12: Cada servico deve expor metricas Prometheus com contador de requisicoes, histograma de latencia e metrica de CPU do processo ou container.
- FR-13: O Prometheus deve coletar metricas automaticamente por annotations nos pods.
- FR-14: Os dois servicos devem emitir spans OpenTelemetry e propagar contexto entre si.
- FR-15: Os pods da aplicacao devem demonstrar o padrao sidecar com OpenTelemetry Collector ou agent equivalente.
- FR-16: O Jaeger deve exibir um trace unico contendo spans do `gateway-service` e do `data-service`.
- FR-17: O `gateway-service` deve poder rodar no namespace `edge` com conectividade restrita e latencia simulada.
- FR-18: O Deployment de borda deve usar liveness e readiness probes calibradas para conectividade instavel.
- FR-19: Em modo offline, o gateway de borda deve continuar respondendo e gravar eventos em buffer local.
- FR-20: O projeto deve conter script para simular queda e restauracao de conectividade.
- FR-21: O projeto deve conter script de sincronizacao posterior com comportamento idempotente.
- FR-22: A entrega deve conter documentacao e evidencias dos tres passos da atividade.
- FR-23: A entrega deve conter documentacao de etica aplicada, conectando as decisoes tecnicas a responsabilidade, colaboracao, bem comum, seguranca e uso consciente de recursos.

## 7. Technical Considerations

- `NetworkPolicy` so e aplicada por CNIs que suportam policies. O CNI padrao do Minikube aceita o objeto mas nao o aplica, entao a simulacao de offline do Passo 3 nao bloquearia nada. Suba o Minikube com `minikube start --cni=calico` ou use K3s, que aplica policies por padrao. Verifique com um teste de conectividade antes e depois de aplicar a policy.
- O `gunicorn` deve rodar com `--workers 1` na entrega. Com varios workers, cada um mantem seu proprio registro do `prometheus_client` e o `/metrics` retorna valores divergentes a cada scrape. Se varios workers forem realmente necessarios, configure `PROMETHEUS_MULTIPROC_DIR` e o `MultiProcessCollector`, e inicialize o OpenTelemetry no hook `post_fork` do gunicorn.
- O evento bufferizado e sincronizado tem formato unico em todo o fluxo: `{event_id (uuid), timestamp, path, payload}`. O gateway de borda gera o `event_id`, o `scripts/sync.py` o transmite e o `data-service` deduplica por esse campo. Esse contrato torna a idempotencia testavel de ponta a ponta.
- GitHub-hosted runners normalmente nao conseguem acessar um Minikube local. Para cumprir deploy automatico real com `kubectl apply`, use self-hosted runner na mesma maquina do cluster ou um cluster acessivel remotamente. O workflow deve provar o deploy com `kubectl rollout status` e registrar a imagem com tag por SHA curto no Deployment.
- Evite depender apenas de `latest` para a evidencia de deploy. Publique `latest` e uma tag por SHA curto, mas implante a tag por SHA curto usando `kubectl set image deployment/<nome> <container>=<imagem>:<sha>` ou Kustomize `images`.
- Se as imagens GHCR forem privadas, sera necessario criar `imagePullSecret`. Para simplificar a atividade, imagens publicas no GHCR reduzem configuracao.
- `ServiceMonitor` so deve ser usado se o Prometheus Operator estiver instalado. Sem operator, use annotations e `kubernetes_sd_configs`.
- Para evidenciar metricas exigidas pela atividade, registre ao menos tres consultas PromQL: contador de requisicoes (`http_requests_total`), tempo de resposta (`http_request_duration_seconds`) e CPU (`process_cpu_seconds_total` ou `container_cpu_usage_seconds_total`).
- Jaeger all-in-one aceita OTLP nas portas 4317 e 4318 quando configurado para isso. O sidecar OpenTelemetry Collector deve encaminhar spans para o Service do Jaeger.
- O padrao sidecar deve aparecer nos manifests da aplicacao, nao apenas como um Deployment separado de observabilidade.
- A restricao de latencia do edge deve ser demonstrada separadamente da desconexao. Uma forma simples e configurar delay no `data-service` acima do timeout do gateway, gerando fallback controlado e evento no buffer local.
- `emptyDir` perde dados quando o pod e removido. Para demonstrar resiliencia melhor, prefira `hostPath` em ambiente local ou PVC se disponivel. No Minikube, `hostPath` aponta para o sistema de arquivos da VM ou container do Minikube, nao para o macOS do host. Use `minikube ssh` para inspecionar o arquivo de buffer.
- O Pushgateway nao raspa nem expoe historico sozinho: ele apenas retem o ultimo valor enviado ate ser raspado por um Prometheus. No modelo de borda, o Pushgateway local guarda as metricas durante a desconexao e o Prometheus central as raspa apos a reconexao. Por simplicidade, um log rotativo local cumpre o mesmo papel de observabilidade parcial offline com menos componentes.
- Readiness em ambiente de borda nao deve depender exclusivamente do servico central. O gateway pode estar pronto se conseguir atender localmente em modo degradado e gravar no buffer.
- O endpoint `POST /sync` pode armazenar eventos em memoria ou arquivo simples. O importante e demonstrar recebimento, idempotencia por `event_id` e evidencia nos logs.

## 8. Etica E Principios Cristaos Aplicados Ao DevOps

Esta secao existe para cobrir explicitamente o criterio de etica e alinhamento com principios cristaos, conectando valores a decisoes praticas do projeto.

- Responsabilidade: usar `requests` e `limits` nos pods para evitar desperdicio de recursos compartilhados no cluster.
- Transparencia: documentar comandos, evidencias, limitacoes e trade-offs em Markdown, permitindo que outra pessoa reproduza a entrega.
- Colaboracao: organizar o repositorio com nomes claros, README completo e scripts de apoio para facilitar revisao e aprendizado por outros colegas.
- Respeito ao bem comum: simular falhas, latencia e borda em ambiente controlado, sem afetar sistemas de terceiros ou redes externas.
- Seguranca e integridade: nao versionar secrets, tokens ou kubeconfigs; usar `GITHUB_TOKEN`, `imagePullSecret` quando necessario e variaveis de ambiente.
- Privacidade: nao registrar dados pessoais nos logs, metricas, traces ou eventos bufferizados. O `payload` deve ser dado simulado.
- Mordomia de recursos: usar imagens leves, replicas controladas, `gunicorn --workers 1` para o exercicio e componentes de observabilidade dimensionados para laboratorio.
- Honestidade academica: as evidencias devem refletir execucoes reais, com prints ou logs dos comandos e UIs usados no projeto.
- Resiliencia com proposito: o modo offline evita perda de dados e melhora continuidade do servico, refletindo cuidado com usuarios em contextos de conectividade limitada.

O arquivo `docs/etica-e-principios.md` deve explicar esses pontos e relacionar cada principio a uma escolha tecnica do projeto.

## 9. Alinhamento Com Criterios De Avaliacao

### Aplicacao De Praticas Cloud-Native: 30 por cento

- Cobertura no plano: Dockerfiles, imagens GHCR, Kubernetes Deployments e Services, requests/limits, labels/selectors, CI/CD com GitHub Actions, deploy automatico e rollout status.
- Evidencias obrigatorias: pipeline verde, imagens publicadas, pods prontos, services ClusterIP, Deployment usando tag por SHA curto e chamada real ao gateway.
- Onde aparece: Passo 1, US-001 a US-005, FR-1 a FR-11.

### Observabilidade E Automacao Distribuida: 30 por cento

- Cobertura no plano: `/metrics`, Prometheus, PromQL para requisicoes, latencia e CPU, OpenTelemetry, sidecar OTel Collector, Jaeger e trace multi-servico.
- Evidencias obrigatorias: targets `UP`, consultas PromQL, pod com container app e sidecar, trace no Jaeger com `gateway-service` e `data-service`.
- Onde aparece: Passo 2, US-006 a US-009, FR-12 a FR-16.

### Adaptacao Ao Contexto De Edge Computing: 20 por cento

- Cobertura no plano: namespace `edge`, CNI com `NetworkPolicy`, bloqueio de trafego, simulacao de latencia, probes tolerantes, buffer local, observabilidade offline e sincronizacao idempotente.
- Evidencias obrigatorias: policy bloqueando trafego, resposta degradada por latencia, resposta offline, buffer com `{event_id, timestamp, path, payload}`, sync posterior e deduplicacao.
- Onde aparece: Passo 3, US-010 a US-014, FR-17 a FR-21.

### Organizacao, Linguagem Tecnica E Estrutura: 10 por cento

- Cobertura no plano: estrutura padronizada de repositorio, README, docs, scripts, manifests separados por dominio e checklist por passo.
- Evidencias obrigatorias: arvore de arquivos, README reproduzivel, `docs/decisoes-tecnicas.md`, `docs/evidencias/` com pastas por passo.
- Onde aparece: Estrutura sugerida, US-015, Definition of Done e Checklist de Entrega.

### Etica E Principios Cristaos: 10 por cento

- Cobertura no plano: responsabilidade com recursos, transparencia, colaboracao, respeito ao bem comum, seguranca, privacidade, honestidade academica e resiliencia em favor do usuario.
- Evidencias obrigatorias: `docs/etica-e-principios.md` e comentarios no README ou decisoes tecnicas conectando valores a escolhas reais.
- Onde aparece: secao 8, US-015 e FR-23.

## 10. Definition Of Done

- [x] Repositorio `devops-u4-cloudnative` criado e versionado no GitHub.
- [x] Dois microsservicos executam localmente.
- [x] Duas imagens sao publicadas no GHCR.
- [x] Manifestos Kubernetes sobem a aplicacao no cluster.
- [x] Pipeline do GitHub Actions executa build, push, deploy automatico, update de imagem por SHA curto e `rollout status`.
- [ ] Prometheus coleta metricas dos dois servicos.
- [ ] Jaeger mostra trace distribuido com spans dos dois servicos.
- [ ] Sidecar OpenTelemetry Collector ou agent equivalente aparece nos pods da aplicacao.
- [ ] Namespace `edge` simula conectividade restrita.
- [ ] Gateway de borda opera em modo degradado com buffer local.
- [ ] Script de sincronizacao envia dados ao central apos reconexao.
- [ ] Simulacao de latencia e simulacao de desconexao foram demonstradas separadamente.
- [x] `docs/etica-e-principios.md` conecta decisoes tecnicas a responsabilidade, colaboracao, bem comum, seguranca e transparencia.
- [ ] Evidencias dos tres passos estao salvas em `docs/evidencias/` (Passo 1 concluido; Passos 2 e 3 pendentes).
- [x] README descreve como reproduzir a entrega.

## 11. Success Metrics

- Pipeline `deploy.yml` conclui com sucesso e publica as imagens.
- Pods dos dois microsservicos ficam `Running` e `Ready` no cluster principal.
- Gateway retorna resposta baseada em dados recebidos do `data-service`.
- Prometheus mostra os dois targets `UP`.
- Prometheus exibe metricas custom de requisicoes, latencia e CPU.
- Jaeger exibe pelo menos um trace multi-servico completo.
- Durante a simulacao offline, o gateway de borda continua respondendo sem erro 500 bruto.
- Durante a simulacao de latencia, o gateway de borda responde em modo degradado sem reiniciar.
- Durante a simulacao offline, eventos sao gravados localmente.
- Apos restaurar conectividade, eventos sao sincronizados sem duplicacao.
- A documentacao etica apresenta decisoes praticas, nao apenas mencoes genericas.

## 12. Premissas Para Pontuacao Maxima

- Ambiente principal: Minikube com Calico ou K3s. Play with Kubernetes so entra se a aplicacao de `NetworkPolicy` for comprovada.
- Deploy automatico: usar self-hosted runner ou cluster acessivel pelo GitHub Actions. Nao depender de apply manual para a entrega principal.
- Imagens: preferir GHCR publico para simplificar pull no Kubernetes. Se privado, incluir `imagePullSecret` e evidencia.
- Tags: publicar `latest` e SHA curto, mas implantar SHA curto para rastreabilidade.
- Evidencias: salvar prints ou logs em `docs/evidencias/` por passo, com nomes claros e data quando possivel.
- Etica: documentar aplicacao pratica dos valores, nao apenas uma declaracao generica.

## 13. Checklist De Entrega Por Passo

### Passo 1

- [x] Codigo dos dois microsservicos.
- [x] Dockerfiles e `.dockerignore`.
- [x] Imagens publicadas no registry.
- [x] Deployments e Services Kubernetes.
- [x] Workflow `deploy.yml` com build, push, deploy automatico, update de imagem por SHA curto e `rollout status`.
- [x] Evidencias de pipeline, pods, services e chamada ao gateway.

### Passo 2

- [ ] Endpoints `/metrics`.
- [ ] Prometheus instalado e coletando targets.
- [ ] OpenTelemetry nos servicos.
- [ ] Sidecar ou agent de exportacao nos pods.
- [ ] Jaeger instalado e recebendo spans.
- [ ] Evidencias de metricas de requisicoes, latencia, CPU e trace completo.

### Passo 3

- [ ] Namespace `edge`.
- [ ] Gateway de borda.
- [ ] NetworkPolicy restritiva.
- [ ] Simulacao de latencia.
- [ ] Probes ajustadas.
- [ ] Buffer local.
- [ ] Pushgateway local ou log rotativo local.
- [ ] Scripts de offline, reconexao e sync.
- [ ] Evidencias de latencia, offline, probes, buffer e sincronizacao.

### Etica E Organizacao

- [x] README reproduzivel.
- [x] `docs/decisoes-tecnicas.md`.
- [x] `docs/etica-e-principios.md`.
- [~] Evidencias organizadas por passo (Passo 1 concluido; Passos 2 e 3 pendentes).
- [x] Nenhum secret, token ou kubeconfig versionado.
