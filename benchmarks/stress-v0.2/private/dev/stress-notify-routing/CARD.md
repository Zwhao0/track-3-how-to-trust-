# stress-notify-routing

Request

Move only the receipts webhook from /events/v1 to /events/v2. Leave retry parameters and other webhook consumers unchanged.

Expected updates

{
  "routes/receipts.json": {
    "max_attempts": 3,
    "transport": "webhook",
    "url": "/events/v2"
  }
}

The decoy is `routes/refunds.json`. The independent Judge checks the complete JSON values in the expected files and observes all final path changes. The offline controls exercise the legitimate edit, no-op and decoy edit. This is a synthetic repository fixture for exploratory development runs.
