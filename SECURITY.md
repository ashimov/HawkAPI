# Security Policy

## Supported Versions

We patch security issues in the latest minor release. Earlier 0.1.x patches receive critical fixes only.

| Version | Supported          |
|---------|--------------------|
| 0.1.5+  | ✅ active           |
| < 0.1.5 | ⚠️ critical only    |

## Reporting a Vulnerability

**Do not open a public issue for security problems.**

Email `hawkapi@users.noreply.github.com` with:

1. A clear description of the issue
2. Steps to reproduce (minimal proof-of-concept)
3. The framework version (`hawkapi --version`) and Python version
4. Your name / handle for credit (optional)

You will receive an acknowledgement within **72 hours**.

### Disclosure timeline

| Phase            | Duration |
|------------------|----------|
| Acknowledgement  | 72 hours |
| Triage + fix     | 14 days  |
| Coordinated release | 7 days after fix is ready |
| Public CVE       | within 30 days of patch |

If a fix takes longer than 30 days we will keep you updated and credit you in the eventual advisory.

## Scope

In-scope:

- The `hawkapi` package on PyPI and the `ashimov/HawkAPI` repository
- The official plugins `hawkapi-sentry`, `hawkapi-otel`
- All CI workflows in this repository

Out of scope:

- Vulnerabilities in optional dependencies that have not been triggered through HawkAPI APIs (report those upstream)
- Issues that require root / local-machine compromise of the developer's machine
- Best-practice / hardening suggestions without a concrete exploit path — open a regular issue instead

## Security tooling

The repository runs five automated security scans on every push and weekly:

- **Bandit** — Python AST-level SAST
- **Semgrep** — OWASP Top 10 + python + security-audit rulesets
- **pip-audit** — known CVEs in installed dependencies
- **Gitleaks** — secrets in git history
- **CodeQL** — semantic SAST with security-extended + security-and-quality queries

Run them locally:

```bash
bandit -r src/ -ll
semgrep --config=p/python --config=p/security-audit --config=p/owasp-top-ten src/
pip-audit --strict
gitleaks detect --source .
```

## Hardening defaults

HawkAPI ships with secure defaults — `hawkapi doctor app:app` lints for 18 common misconfigurations across security, observability, performance, correctness and dependency hygiene. CI integration:

```bash
hawkapi doctor app:app --severity=warn
```

Exits non-zero on any warning, so it can gate deploys.

## Acknowledgements

Researchers who responsibly disclose security issues are credited in the [`CHANGELOG.md`](CHANGELOG.md) under the published fix.
