# Evidencias - Passo 1 (deploy no cluster Kubernetes)

Cluster: Minikube com CNI Calico (`minikube start --driver=docker --cni=calico`), arm64.
Deploy executado pelo **pipeline** via self-hosted runner (label `k8s`).

## Run do deploy automatico
- Run: https://github.com/BorgersDev/devops-u4-cloudnative/actions/runs/28300121768
- Commit / tag implantada: `faee6e7`
- Build multi-arch (amd64+arm64) para rodar no cluster arm64.

## kubectl set image + rollout status (executado pelo workflow)
```text
deployment.apps/data-service image updated
deployment.apps/gateway-service image updated
deployment "data-service" successfully rolled out
deployment "gateway-service" successfully rolled out
```

## kubectl get pods -n cloudnative
```text
NAME                               READY   STATUS    RESTARTS   AGE   IP              NODE       NOMINATED NODE   READINESS GATES
data-service-6d8d896c67-tcx2r      1/1     Running   0          95s   10.244.120.74   minikube   <none>           <none>
gateway-service-6bd48bb78f-qgbsb   1/1     Running   0          95s   10.244.120.75   minikube   <none>           <none>
```

## kubectl get svc -n cloudnative (ClusterIP)
```text
NAME              TYPE        CLUSTER-IP      EXTERNAL-IP   PORT(S)    AGE
data-service      ClusterIP   10.96.172.109   <none>        8000/TCP   6m
gateway-service   ClusterIP   10.106.144.58   <none>        8000/TCP   5m59s
```

## Imagem implantada (tag por SHA curto)
```text
data-service: ghcr.io/borgersdev/devops-u4-cloudnative/data-service:faee6e7
gateway-service: ghcr.io/borgersdev/devops-u4-cloudnative/gateway-service:faee6e7
```

## Requisicao ao gateway no cluster (port-forward)
Gateway chama o data-service via DNS interno e retorna `degraded:false` com dados reais:
```json
{ "service": "gateway-service", "degraded": false,
  "upstream": "http://data-service.cloudnative.svc.cluster.local:8000/data",
  "data": { "service": "data-service", "items": [ {"name":"sensor-temperatura","value":21.5,"unit":"C"}, ... ] } }
```
