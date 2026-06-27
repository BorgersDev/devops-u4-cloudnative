# Etica e Principios Aplicados ao DevOps

Esta secao conecta valores a decisoes tecnicas concretas do projeto, nao apenas
declaracoes genericas. Cada principio aponta para onde aparece no codigo ou nos
manifestos.

## Responsabilidade e mordomia de recursos
- Todos os Deployments declaram `resources.requests` e `resources.limits`
  (`k8s/*/deployment.yaml`), evitando que um servico monopolize o cluster
  compartilhado.
- Imagens base leves (`python:3.12-slim`) e `replicas: 1` no laboratorio reduzem
  consumo de CPU, memoria e armazenamento.
- `gunicorn --workers 1` dimensiona o servidor para o exercicio, sem
  superprovisionar processos.

## Transparencia e honestidade academica
- Comandos, variaveis de ambiente, trade-offs e validacoes estao documentados em
  `README.md` e `docs/decisoes-tecnicas.md`, permitindo reproducao por terceiros.
- As evidencias em `docs/evidencias/` refletem execucoes reais (build de imagens,
  `docker run`, testes de idempotencia e modo degradado), nao mockups.

## Colaboracao
- Repositorio organizado por dominio (`services/`, `k8s/`, `scripts/`, `docs/`),
  nomes claros e README completo facilitam revisao e aprendizado por colegas.

## Respeito ao bem comum
- Falhas, latencia e cenarios de borda sao simulados em ambiente controlado
  (delay no produtor, namespace isolado, `NetworkPolicy` local). Nada afeta
  sistemas de terceiros ou redes externas.

## Seguranca e integridade
- Nenhum secret, token ou kubeconfig e versionado (`.gitignore`). O pipeline usa
  o `GITHUB_TOKEN` nativo com escopo minimo (`packages: write`).
- Quando imagens privadas exigirem `imagePullSecret`, ele fica no cluster, fora
  do repositorio.

## Privacidade
- Os dados do `data-service` e os `payload` de eventos sao simulados. Nenhum dado
  pessoal e registrado em logs, metricas ou eventos bufferizados.

## Resiliencia com proposito
- O modo degradado do gateway e o buffer local (Passo 3) evitam perda de dados e
  preservam a continuidade do servico em conectividade limitada, refletindo
  cuidado com usuarios em contextos de borda.

> Os principios acima orientam decisoes praticas ao longo dos tres passos. Itens
> referentes aos Passos 2 e 3 (observabilidade, buffer, sincronizacao) serao
> reforcados com evidencias conforme implementados.
