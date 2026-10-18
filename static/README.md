# Integrated browser interface

The FastAPI app serves these pages from this directory: `/`, `/review`,
`/results`, `/workspaces`, the four `/tools/...` workspaces, and `/advanced`.
Assets are served at `/static/...`; Swagger is at `/docs`.

`app.js` handles the guided review, specialist forms, file preview, status,
and tab-local result storage. `advanced.js` drives the JSON console. Both use
the browser compatibility routes in `api.py`, which call the existing agents.
The original `/analyze-contract` API remains available.

Uploading a file to `/api/extract` only previews its extracted text. Submitting
the review or a text specialist analysis ingests the contract and updates the
Neo4j knowledge graph. The results page stores its report in browser
`sessionStorage`; there is no server-side report history or authentication.
