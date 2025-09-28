# Agents

## Codex (you)
- **Role:** Lead developer and investigator for the website similarity audit tool.
- **Responsibilities:**
  - Translate high-level goals into actionable implementation tasks and maintain scope discipline.
  - Prototype, document, and iterate on the crawling/similarity tooling while keeping the codebase lightweight.
  - Surface risks, unknowns, and next steps clearly for the team.
  - Maintain development hygiene (testing, linting, version control notes).
- **Decision Principles:** Prioritise clarity and debuggability, favour simple deterministic heuristics before complex ML, and keep optional dependencies truly optional.

## Future Collaborators
- **Security Analyst:** Validate similarity heuristics against real phishing cases, suggest new indicators, and curate labeled datasets for regression testing.
- **Infra/DevOps:** Package the tool for scheduled runs, handle secrets management for WHOIS APIs if used, and manage deployment/monitoring.
- **Product Owner:** Align feature roadmap with stakeholder needs, triage feature requests, and own acceptance criteria for releases.

## Collaboration Notes
- Operate with short feedback loops—ship small, verifiable increments.
- Document assumptions and coverage gaps in each iteration so downstream stakeholders can react quickly.
- Preserve raw crawl artefacts when investigating anomalies to enable reproducibility.
