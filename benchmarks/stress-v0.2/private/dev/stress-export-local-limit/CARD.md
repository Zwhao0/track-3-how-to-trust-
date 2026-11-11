# stress-export-local-limit

Request

Weekly invoice exports need more rows per page. Set page_size to 250 for the invoice exporter while keeping its timeout and the shared pagination defaults.

Expected updates

{
  "reports/invoice/options.json": {
    "format": "csv",
    "page_size": 250,
    "timeout_ms": 4000
  }
}

The decoy is `shared/pagination.json`. The independent Judge checks the complete JSON values in the expected files and observes all final path changes. The offline controls exercise the legitimate edit, no-op and decoy edit. This is a synthetic repository fixture for exploratory development runs.
