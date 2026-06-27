"""Configuracao do gunicorn.

O OpenTelemetry e inicializado no hook post_fork, ja dentro do worker. Inicializar
no master quebraria o tracing: o BatchSpanProcessor sobe uma thread exportadora que
nao e herdada pelo processo filho apos o fork. Com --workers 1 ha um unico worker e
um unico registro de spans, alinhado ao mesmo motivo de manter o prometheus_client
em worker unico.
"""


def post_fork(server, worker):
    import app

    app.setup_tracing()
