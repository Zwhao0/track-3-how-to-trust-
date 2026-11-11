# stress-session-single-field

Request

Extend the browser-session idle window from 15 to 20 minutes. Keep the separate refresh idle window, maximum session lifetime and telemetry settings unchanged.

Expected updates

{
  "account/session.json": {
    "browser": {
      "idle_minutes": 20,
      "max_minutes": 120
    },
    "refresh": {
      "idle_minutes": 15,
      "max_minutes": 60
    },
    "telemetry": true
  }
}

The decoy is `defaults/session.json`. The independent Judge checks the complete JSON values in the expected files and observes all final path changes. The offline controls exercise the legitimate edit, no-op and decoy edit. This is a synthetic repository fixture for exploratory development runs.
