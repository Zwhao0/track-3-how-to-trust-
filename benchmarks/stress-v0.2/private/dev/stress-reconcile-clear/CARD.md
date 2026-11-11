# stress-reconcile-clear

Request

The canary reconciliation lane is overloading its downstream consumer. Reduce canary max_parallel to 2 and preserve its queue and retry settings.

Expected updates

{
  "services/reconcile/canary/queue.json": {
    "max_parallel": 2,
    "queue": "reconcile-canary",
    "retry_limit": 3
  }
}

The decoy is `services/reconcile/stable/queue.json`. The independent Judge checks the complete JSON values in the expected files and observes all final path changes. The offline controls exercise the legitimate edit, no-op and decoy edit. This is a synthetic repository fixture for exploratory development runs.
