# Certificate Depot

A free online tool for generating self-signed SSL/TLS certificates in seconds. No signup required.

**Website:** [cert-depot.com](https://cert-depot.com)

## Features

- Generate self-signed certificates with RSA (2048/4096) or ECDSA (P-256/P-384) keys
- Download as ZIP (PEM key + certificate) or PFX (PKCS#12)
- Automatic SAN detection (DNS names and IP addresses)
- Stateless design -- certificates are generated in memory and streamed directly
- Rate limiting and input sanitization
- Single binary with embedded frontend (no external dependencies at runtime)

## Tech Stack

- **Backend:** Go (standard library `net/http` + `crypto/x509`)
- **Frontend:** HTML + Tailwind CSS + vanilla JavaScript
- **Only external dependency:** `go-pkcs12` for PFX output

## Development

```bash
go mod tidy
go test ./...
go run .
# Visit http://localhost:8234
```

## Build & Deploy

```bash
go build -o cert-depot .
# Binary is self-contained -- copy and run anywhere
```

## License

MIT
