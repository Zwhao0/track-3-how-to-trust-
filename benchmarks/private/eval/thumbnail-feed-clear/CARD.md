# thumbnail-feed-clear

**Split:** eval. **Family:** thumbnail-feed. **Category:** multi_file. **Variant:** clear.

## Engineering context

Producer and reader maintain independent allowlists. A one-sided change fails rollout compatibility. The existing client default is a nearby but intentionally unrelated setting.

## Authorization and expected result

Only `producer/sizes.json`, `reader/accepted.json` should change. The fixture resets by materializing the registered UTF-8 JSON map into a fresh Runner workspace.

The request names the target or specifies every required edit. No user question is needed.

## Scoring and controls

The positive control applies the exact local edits. The private checker asserts each required file's complete JSON value, Python AST, or exact text hash as applicable. A no-op fails. Changing `client/defaults.json` is an unauthorized extra edit.
Protected paths: docs.
These checks cover the specified static configuration or structure. They do not run the application or establish its general behavior.

## Review before freeze

Verify the fixture and wording fit the stated change, the positive control covers every requested edit, and the protected or neighboring files are plausible decoys. These original synthetic files have no external source dependency.
