#!/usr/bin/env python3
"""scripts/sync.py - sincroniza o buffer local da borda com o data-service central.

Le os eventos bufferizados pelo gateway de borda no modo offline (arquivo JSONL com
eventos {event_id, timestamp, path, payload}), envia em lote para o `POST /sync` do
data-service e, somente APOS resposta de sucesso, reescreve o buffer removendo os
eventos ja reconhecidos pelo central.

Idempotencia (US-014): o data-service deduplica por `event_id`, entao rodadas
repetidas nao duplicam eventos. Tanto os eventos `accepted` (novos) quanto os
`ignored` (ja conhecidos) sao tratados como reconhecidos e removidos do buffer, o que
torna o script seguro para reexecucao mesmo apos uma sincronizacao parcial.

Usa apenas a biblioteca padrao (urllib) para rodar no host sem dependencias extras.

Uso:
  python scripts/sync.py [--url URL] [--buffer CAMINHO] [--timeout SEG] [--keep] [--dry-run]

Padroes:
  --url     env DATA_SERVICE_URL ou http://localhost:8000
  --buffer  env EDGE_BUFFER_PATH ou ./buffer.jsonl
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request


def read_events(path):
    """Le o buffer JSONL. Retorna (eventos_validos, total_linhas, linhas_invalidas)."""
    events = []
    invalid = 0
    total = 0
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            total += 1
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                invalid += 1
                continue
            if isinstance(event, dict) and "event_id" in event:
                events.append(event)
            else:
                invalid += 1
    return events, total, invalid


def post_sync(url, events, timeout):
    """Envia os eventos ao POST /sync e retorna o JSON de resposta."""
    endpoint = f"{url.rstrip('/')}/sync"
    body = json.dumps({"events": events}).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def rewrite_buffer(path, events):
    """Reescreve o buffer apenas com os eventos restantes (nao reconhecidos)."""
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def main():
    parser = argparse.ArgumentParser(description="Sincroniza o buffer da borda com o central.")
    parser.add_argument(
        "--url",
        default=os.environ.get("DATA_SERVICE_URL", "http://localhost:8000"),
        help="URL base do data-service (default: env DATA_SERVICE_URL ou http://localhost:8000)",
    )
    parser.add_argument(
        "--buffer",
        default=os.environ.get("EDGE_BUFFER_PATH", "./buffer.jsonl"),
        help="Caminho do buffer JSONL (default: env EDGE_BUFFER_PATH ou ./buffer.jsonl)",
    )
    parser.add_argument("--timeout", type=float, default=10.0, help="Timeout HTTP em segundos.")
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Nao remove os eventos reconhecidos do buffer (util para testar idempotencia).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Apenas le e mostra quantos eventos seriam enviados, sem chamar o central.",
    )
    args = parser.parse_args()

    if not os.path.exists(args.buffer):
        print(f"buffer inexistente: {args.buffer} (nada a sincronizar)")
        return 0

    events, total, invalid = read_events(args.buffer)
    print(f"buffer {args.buffer}: {total} linhas, {len(events)} eventos validos, {invalid} invalidas")

    if not events:
        print("nada a sincronizar.")
        return 0

    if args.dry_run:
        print(f"[dry-run] {len(events)} eventos seriam enviados a {args.url}/sync")
        return 0

    try:
        result = post_sync(args.url, events, args.timeout)
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"falha ao sincronizar com {args.url}/sync: {exc}", file=sys.stderr)
        return 1

    accepted = result.get("accepted", [])
    ignored = result.get("ignored", [])
    acknowledged = set(accepted) | set(ignored)
    print(
        f"resposta do central: recebidos={result.get('received')} "
        f"aceitos={len(accepted)} ignorados={len(ignored)} "
        f"invalidos={result.get('invalid')} total_conhecidos={result.get('total_known')}"
    )

    if args.keep:
        print("--keep: buffer preservado (eventos nao removidos).")
        return 0

    remaining = [e for e in events if str(e.get("event_id")) not in acknowledged]
    rewrite_buffer(args.buffer, remaining)
    print(f"buffer atualizado: {len(acknowledged)} reconhecidos removidos, {len(remaining)} restantes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
