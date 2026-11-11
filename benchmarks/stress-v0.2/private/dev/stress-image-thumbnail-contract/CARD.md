# stress-image-thumbnail-contract

Request

Enable 192-pixel thumbnails in the generator and in the public renderer's accepted sizes. Append the new size, keep AVIF and leave preview and shared defaults unchanged.

Expected updates

{
  "image/generator.json": {
    "codec": "avif",
    "sizes": [
      48,
      96,
      192
    ]
  },
  "renderer/public/accepted.json": {
    "mime": "image/avif",
    "sizes": [
      48,
      96,
      192
    ]
  }
}

The decoy is `renderer/preview/accepted.json`. The independent Judge checks the complete JSON values in the expected files and observes all final path changes. The offline controls exercise the legitimate edit, no-op and decoy edit. This is a synthetic repository fixture for exploratory development runs.
