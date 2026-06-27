# Evidencias - Passo 2 (tracing distribuido com OpenTelemetry + Jaeger)

Cluster: Minikube com CNI **Calico**, arm64. Namespace `cloudnative`.
OpenTelemetry SDK nos dois servicos (Flask + requests instrumentados), exportando
spans via OTLP/gRPC para o **sidecar otel-collector** em `localhost:4317`, que
encaminha ao **Jaeger all-in-one**. Data: 2026-06-27.

## Como reproduzir

```bash
kubectl apply -f k8s/observability/jaeger.yaml
kubectl -n cloudnative port-forward svc/jaeger 16686:16686
kubectl -n cloudnative port-forward svc/gateway-service 8100:8000
./scripts/generate-traffic.sh http://localhost:8100/ 60
# UI: http://localhost:16686
```

## OTEL_SERVICE_NAME distinto por servico

Definido nos Deployments (`k8s/*/deployment.yaml`):

```text
data-service     -> OTEL_SERVICE_NAME=data-service
gateway-service  -> OTEL_SERVICE_NAME=gateway-service
```

## Servicos registrados no Jaeger (API /api/services)

```text
['data-service', 'gateway-service']
```

## Sidecar otel-collector recebendo e exportando spans (logs)

`kubectl -n cloudnative logs -l app=gateway-service -c otel-collector`:

```text
info  TracesExporter  {"kind": "exporter", "data_type": "traces", "name": "debug", "resource spans": 1, "spans": 2}
info  TracesExporter  {"kind": "exporter", "data_type": "traces", "name": "debug", "resource spans": 1, "spans": 3}
info  TracesExporter  {"kind": "exporter", "data_type": "traces", "name": "debug", "resource spans": 1, "spans": 1}
```

## Trace multi-servico (1 requisicao ao gateway -> 1 trace com os 2 servicos)

Dos 40 traces recentes consultados, 18 sao multi-servico (gateway + data).
Exemplo (`traceID: caf8a7ca04e808cdf8b9b52ba66de522`, 3 spans):

```text
gateway-service | GET /      | 7.70 ms  (root)     <- entrada no gateway
gateway-service | GET        | 5.78 ms  (child)    <- cliente requests (propaga traceparent)
data-service    | GET /data  | 0.99 ms  (child)    <- producer, mesmo trace
```

O contexto W3C `traceparent` propagado pela instrumentacao de `requests` liga os
spans dos dois servicos em um unico trace, mostrando tempo por etapa e a relacao
pai/filho entre eles.

## Prints de UI que faltam (tirar manualmente)

1. **Jaeger - busca**: `http://localhost:16686`, Service = `gateway-service`,
   operacao `GET /`, clicar em **Find Traces** e capturar a lista.
2. **Jaeger - trace completo**: abrir um trace de `GET /` e capturar a timeline
   mostrando os spans `gateway-service GET /`, `gateway-service GET` e
   `data-service GET /data` (dois servicos no mesmo trace).
