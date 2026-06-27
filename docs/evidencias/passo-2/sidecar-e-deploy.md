# Evidencias - Passo 2 (padrao sidecar e deploy pelo pipeline)

Cluster: Minikube com CNI **Calico**, arm64. Namespace `cloudnative`.
Deploy executado pelo **pipeline** (GitHub Actions, self-hosted runner label `k8s`).
Imagens **multi-arch** (amd64+arm64) no GHCR. Data: 2026-06-27.

## Run do pipeline (build + deploy automatico)

- Run: https://github.com/BorgersDev/devops-u4-cloudnative/actions/runs/28301660010
- Conclusao: `success`
- Commit / tag implantada: `9bbd924`

## kubectl set image + rollout status (executado pelo workflow)

```text
deployment.apps/data-service image updated
deployment.apps/gateway-service image updated
deployment "data-service" successfully rolled out
deployment "gateway-service" successfully rolled out
```

## Imagens implantadas (tag por SHA curto)

```text
data-service:    ghcr.io/borgersdev/devops-u4-cloudnative/data-service:9bbd924
gateway-service: ghcr.io/borgersdev/devops-u4-cloudnative/gateway-service:9bbd924
```

## Padrao sidecar: cada pod da app tem 2 containers (app + otel-collector)

```text
data-service-776d68f75-qk6gv       -> data-service     otel-collector
gateway-service-5b988b6f97-lp9d6   -> gateway-service  otel-collector
```

## kubectl get pods -n cloudnative (app 2/2 READY: app + sidecar)

```text
NAME                               READY   STATUS    RESTARTS   AGE
data-service-776d68f75-qk6gv       2/2     Running   0          5m30s
gateway-service-5b988b6f97-lp9d6   2/2     Running   0          5m30s
jaeger-bbd69697d-k6mm5             1/1     Running   0          10m
prometheus-65ddf8f5cb-6xnvq        1/1     Running   0          10m
```

## kubectl get svc -n cloudnative

```text
NAME              TYPE        CLUSTER-IP      EXTERNAL-IP   PORT(S)                       AGE
data-service      ClusterIP   10.96.172.109   <none>        8000/TCP                      74m
gateway-service   ClusterIP   10.106.144.58   <none>        8000/TCP                      74m
jaeger            ClusterIP   10.100.136.71   <none>        16686/TCP,4317/TCP,4318/TCP   10m
prometheus        ClusterIP   10.106.167.49   <none>        9090/TCP                      10m
```

## Observacao sobre o gunicorn e o OpenTelemetry

O OpenTelemetry e inicializado no hook `post_fork` do gunicorn
(`services/*/gunicorn.conf.py`), ja dentro do worker. Inicializar no master
quebraria o tracing porque a thread do `BatchSpanProcessor` nao sobrevive ao
fork. Com `--workers 1` ha um unico worker, alinhado tambem a consistencia do
`prometheus_client`. Os logs do sidecar (ver `tracing-jaeger.md`) confirmam que
os spans realmente chegam ao collector e seguem para o Jaeger.

## Print de UI/console que falta (tirar manualmente)

1. **Pod com 2 containers**: terminal com
   `kubectl -n cloudnative get pods` mostrando `2/2` para os dois apps, ou
   `kubectl -n cloudnative describe pod <gateway-pod>` listando os containers
   `gateway-service` e `otel-collector`.
