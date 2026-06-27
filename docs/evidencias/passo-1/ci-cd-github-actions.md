# Evidencias - Passo 1 (CI/CD e GHCR)

Execucao real do pipeline apos publicar o repositorio.

## Repositorio
- https://github.com/BorgersDev/devops-u4-cloudnative (publico)

## Run do GitHub Actions
- Run: https://github.com/BorgersDev/devops-u4-cloudnative/actions/runs/28299616528
- Commit (headSha): `5b497613cf2d5c99e2e59c52f76736ded5081ab9`
- SHA curto implantado: `5b49761`
- Workflow: `build-and-deploy` (push para `main`)

### Status dos jobs
| Job                                  | Status            |
|--------------------------------------|-------------------|
| Build e push das imagens (GHCR)      | completed/success |
| Deploy automatico no cluster         | queued (aguardando self-hosted runner com label `k8s`) |

> O job de deploy permanece `queued` ate o self-hosted runner conectado ao
> cluster ser registrado. Esse e o comportamento esperado: runners hospedados
> pelo GitHub nao alcancam o Minikube/K3s local.

## Imagens publicadas no GHCR (publicas)

Confirmadas via `docker manifest inspect` (sem autenticacao, pois sao publicas):

```text
OK  ghcr.io/borgersdev/devops-u4-cloudnative/data-service:latest
OK  ghcr.io/borgersdev/devops-u4-cloudnative/data-service:5b49761
OK  ghcr.io/borgersdev/devops-u4-cloudnative/gateway-service:latest
OK  ghcr.io/borgersdev/devops-u4-cloudnative/gateway-service:5b49761
```

Cada servico tem duas tags: `latest` e o SHA curto do commit. O deploy usa a tag
por SHA curto para rastreabilidade.

## Pendente (precisa do cluster + self-hosted runner)

- [ ] Job de deploy verde (apos registrar o runner `k8s`).
- [ ] `kubectl rollout status` dos dois Deployments (executado pelo workflow).
- [ ] `kubectl get pods -n cloudnative` (Running/Ready).
- [ ] `kubectl get svc -n cloudnative` (ClusterIP).
- [ ] Deployment usando a imagem com tag por SHA curto.
- [ ] Requisicao ao gateway no cluster retornando dados do data-service.
