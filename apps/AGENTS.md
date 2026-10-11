# Django app instructions

Read [../CLAUDE.md](../CLAUDE.md), then the owning app's `CLAUDE.md` when it
exists. The root document indexes the app-specific instructions; read the
guidance for every subsystem involved in a cross-app change.

Reuse the existing permission, family-scoping, ledger, and approval helpers.
Use `config.tests.factories.make_family` when tests need several users so
family-boundary mistakes remain visible. Progression remains server-owned.

For responses used by both clients, read
[../contracts/api/README.md](../contracts/api/README.md) and update the shared
fixtures with the producing endpoint and affected consumers. Run the relevant
backend tests using the environment described in the root document.
