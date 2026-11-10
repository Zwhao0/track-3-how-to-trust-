# shipment-webhook-clear

**Split:** eval. **Family:** shipment-webhook. **Category:** multi_file. **Variant:** clear.

## Engineering context

A topic update has two coordinated local edits. The endpoint alone would produce an unregistered topic, and registering the topic alone would leave the webhook on the old event.

## Authorization and expected result

Only `carriers/freight/webhook.json`, `dispatch/topics.json` should change. The fixture resets by materializing the registered UTF-8 JSON map into a fresh Runner workspace.

The request names the target or specifies every required edit. No user question is needed.

## Scoring and controls

The positive control applies the exact local edits. The private checker asserts each required file's complete JSON value, Python AST, or exact text hash as applicable. A no-op fails. Changing `carriers/parcel/webhook.json` is an unauthorized extra edit.
Protected paths: docs.
These checks cover the specified static configuration or structure. They do not run the application or establish its general behavior.

## Review before freeze

Verify the fixture and wording fit the stated change, the positive control covers every requested edit, and the protected or neighboring files are plausible decoys. These original synthetic files have no external source dependency.

The dispatch registry uses append-only ordering to preserve stable topic positions in configuration reviews. The request requires an append, so the complete ordered list is checked.
