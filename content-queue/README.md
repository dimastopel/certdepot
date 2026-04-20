# Content Queue

Each subdirectory is one piece of content to be deployed. Directories are processed
alphabetically, so name them `01-slug/`, `02-slug/`, etc.

## Structure

```
content-queue/
  01-pem-decoder/             # already deployed example
    metadata.json
    pem-decoder.html
  02-csr-generator/
    metadata.json
    csr-generator.html
    csr-generator.js          # optional per-tool JS
  03-self-signed-cert-nginx/
    metadata.json
    self-signed-cert-nginx.html
```

## metadata.json

```json
{
  "type": "tool",             // "tool" or "guide"
  "slug": "csr-generator",
  "title": "CSR Generator",
  "priority": "0.8"           // sitemap priority
}
```

## Deployment

The cron job at `scripts/deploy_content.sh` picks the lowest-numbered directory
each day, copies files into place, updates the sitemap, rebuilds the binary,
and restarts the service. Once deployed, the content-queue directory is renamed
with a `.deployed` suffix so it won't be picked up again.
