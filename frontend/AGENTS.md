# React instructions

Read [CLAUDE.md](CLAUDE.md) before editing this subtree. It is the canonical
frontend guidance for API access, authentication, privacy, PWA behavior,
components, styling, and testing. Read
[src/components/README.md](src/components/README.md) for design-system changes,
and [src/pages/CLAUDE.md](src/pages/CLAUDE.md) for page changes.

Use endpoint functions from `src/api/index.js`, and reuse the existing UI
primitives and test scaffolding. Preserve the same-origin journal/Unity
session and credential-bound account changes described in `CLAUDE.md`.

Read [../contracts/api/README.md](../contracts/api/README.md) for shared
responses. Keep affected fixtures and consumer checks aligned with the actual
backend response. Every clickable POST/PATCH/DELETE interaction requires the
request-spy coverage specified in `CLAUDE.md`.

From this directory, run the relevant colocated tests with
`npm run test:run -- <test-path>`, plus `npm run lint` and `npm run build` for
frontend changes. `npm run test:coverage` runs the CI suite and coverage gate.
