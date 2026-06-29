# Passo 3 no cluster - guia de reproducao e captura de evidencias

Este guia descreve os comandos para reproduzir a simulacao de borda em Kubernetes e
quais saidas capturar (prints/logs) em `docs/evidencias/passo-3/`. O nucleo do fluxo
(buffer, sync e idempotencia) ja esta comprovado de forma reproduzivel em
[`validacao-local.md`](validacao-local.md); aqui ficam as evidencias que dependem do
cluster: namespace `edge`, `NetworkPolicy` bloqueando o trafego, probes tolerantes e
Pushgateway local.

> Pre-requisito critico: o cluster precisa de um CNI que **aplica** `NetworkPolicy`
> (Calico no Minikube ou K3s). O CNI padrao do Minikube aceita a policy mas nao a
> aplica, e o bloqueio do offline nao aconteceria.
>
> ```bash
> minikube start --cni=calico    # ou K3s
> ```

## 0. Pre-condicao: aplicacao central no ar (Passos 1 e 2)

```bash
./scripts/deploy-local.sh <owner> latest          # data-service + gateway no namespace cloudnative
kubectl -n cloudnative get pods
```

## 1. Subir a borda

Os manifestos usam o placeholder `ghcr.io/OWNER/...`. Substitua `OWNER` (minusculo)
antes de aplicar o Deployment de borda:

```bash
kubectl apply -f k8s/edge/namespace.yaml
kubectl apply -f k8s/edge/pushgateway.yaml
sed "s#ghcr.io/OWNER/#ghcr.io/<owner>/#g" k8s/edge/gateway-edge-deployment.yaml | kubectl apply -f -
kubectl apply -f k8s/edge/gateway-edge-service.yaml

kubectl -n edge rollout status deployment/gateway-edge
kubectl -n edge get pods           # >>> EVIDENCIA: gateway de borda Ready
```

## 2. Caminho feliz (borda alcanca o central)

```bash
kubectl -n edge port-forward svc/gateway-edge 8200:8000 &
curl localhost:8200/               # degraded:false, dados do data-service central
```

## 3. Latencia: produtor lento acima do timeout do gateway de borda (FR-17)

Demonstrada SEPARADAMENTE da desconexao. Aplique delay no produtor central acima do
`DATA_SERVICE_TIMEOUT_SECONDS=1.0` do gateway de borda:

```bash
kubectl -n cloudnative set env deployment/data-service RESPONSE_DELAY_MS=1500
kubectl -n cloudnative rollout status deployment/data-service
curl localhost:8200/               # >>> EVIDENCIA: degraded:true, reason "timeout ao chamar data-service"
kubectl -n cloudnative set env deployment/data-service RESPONSE_DELAY_MS=0   # restaura
```

## 4. Offline: NetworkPolicy bloqueando o central (US-010, FR-20)

```bash
./scripts/simulate-offline.sh      # >>> EVIDENCIA: conectividade antes (OK) e policy aplicada
kubectl -n edge get networkpolicy edge-offline -o yaml | head -40   # >>> EVIDENCIA da policy ativa

curl localhost:8200/               # >>> EVIDENCIA: degraded:true, buffered_event_id
# Obs.: sob NetworkPolicy os pacotes sao descartados, entao o reason aparece como
# "timeout ao chamar data-service". A prova de que e bloqueio de REDE (e nao apenas
# lentidao) e a chamada direta acima dar timeout; sem a policy ela responde na hora.
kubectl -n edge logs deploy/gateway-edge | grep "modo degradado"     # >>> EVIDENCIA: modo degradado no log
```

Inspecionar o buffer no volume `hostPath` da VM do Minikube:

```bash
minikube ssh -- cat /mnt/edge-buffer/buffer.jsonl    # >>> EVIDENCIA: eventos {event_id,timestamp,path,payload}
```

## 5. Probes durante a instabilidade (US-011)

```bash
kubectl -n edge describe pod -l app=gateway-edge | sed -n '/Liveness/,/Events/p'
kubectl -n edge get pods -l app=gateway-edge        # >>> EVIDENCIA: Ready mesmo offline, sem restarts
```

A readiness continua `Ready` em modo degradado (o gateway atende localmente e
bufferiza); a liveness so checa o processo local, sem reiniciar por causa do central.

## 6. Observabilidade offline: Pushgateway local (US-013)

```bash
kubectl -n edge port-forward svc/pushgateway 9091:9091 &
curl -s localhost:9091/metrics | grep edge_buffered_events_total   # >>> EVIDENCIA: metrica retida offline
```

## 7. Reconexao e sincronizacao idempotente (US-014)

```bash
./scripts/restore-connection.sh    # remove a policy; >>> EVIDENCIA: conectividade restaurada

# Sincroniza o buffer da borda com o central. Rode de dentro do pod (le o hostPath)
# ou copie o buffer e use port-forward do data-service.
kubectl -n cloudnative port-forward svc/data-service 8000:8000 &
minikube ssh -- cat /mnt/edge-buffer/buffer.jsonl > ./buffer.jsonl
python scripts/sync.py --url http://localhost:8000 --buffer ./buffer.jsonl   # >>> EVIDENCIA: aceitos
python scripts/sync.py --url http://localhost:8000 --buffer ./buffer.jsonl   # >>> EVIDENCIA: nada a sincronizar

kubectl -n cloudnative logs deploy/data-service | grep "evento sincronizado"  # >>> EVIDENCIA no central
```

A idempotencia ja esta demonstrada de ponta a ponta em
[`validacao-local.md`](validacao-local.md) (reenvio cai em `ignorados`, sem duplicar).
