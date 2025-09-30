# Clone Audit Roadmap

## Purpose
Establish a lightweight foundation for the clone audit tooling so future feature teams (cert monitoring, proactive discovery, reporting) can build cleanly on top of the shared library without immediate implementation pressure.

## Guiding Principles
- Prioritise core crawler/extractor/comparer refactor before adding new surfaces.
- Keep adapters optional and injectable to support experimentation without breaking the CLI.
- Preserve artefacts and configs to enable reproducible investigations.
- Document assumptions, decisions, and open questions at each milestone.

## Milestones

### Milestone 1 – Core Library Refactor (Weeks 1–2) 
**Goal:** Restructure existing code into shared, side-effect-free modules that other teams can consume.

**Scope:**
- Move crawl/extract/compare logic into `clone_audit.core` with clear input/output dataclasses.
- Formalise adapter protocols for HTTP fetching, WHOIS, hosting lookups, and screenshot/cert tooling.
- Consolidate configuration handling into shared dataclasses with serde helpers and defaults.
- Maintain current CLI functionality by re-wiring it to the refactored library.

**Deliverables:** Updated module tree, interface reference doc, regression tests proving CLI parity, short design note listing follow-up questions.

### Milestone 2 – Core Validation & Tooling (Week 3)
**Goal:** Harden the refactored library with tests, documentation, and developer ergonomics before expanding scope.

**Scope:**
- Expand unit/integration test coverage for crawler, extractor, comparator, and adapters.
- Introduce structured logging hooks and timing metrics surfaced via the library (no background services yet).
- Provide developer utilities for capturing/replaying crawls and seeding fixtures.
- Draft contributor guide outlining module boundaries and coding standards.

**Deliverables:** Test suite report, logging/metrics guidelines, developer tooling README, updated contributor guide.

### Milestone 3 – Extended Services Discovery (Weeks 4–5)
**Goal:** Produce design artefacts for cert monitoring, proactive crawl, and reporting without implementing production services.

**Scope:**
- High-level architecture docs for each service describing workflows, data requirements, and open issues.
- Define data contracts and storage needs leveraging the refactored core library.
- Identify external dependencies, security/privacy considerations, and success criteria for MVP implementations.
- Prioritise backlog tickets and research spikes for future teams.

**Deliverables:** Three service design briefs, consolidated dependency matrix, prioritised backlog.

### Milestone 4 – Implementation Readiness Gate (Week 6)
**Goal:** Confirm the platform is stable and that discovery outputs are actionable before green-lighting new feature builds.

**Scope:**
- Run final review of core library stability (bug triage, performance checks, observability baseline).
- Validate storage/schema proposals with Infra and Security; finalize versioning/migration approach.
- Approve backlog and staffing plan for cert monitoring, proactive crawl, and reporting implementations.

**Deliverables:** Readiness report, signed-off storage schema, staffed roadmap for subsequent execution.

## Cross-Team Alignment
- **Security Analyst:** Review adapter interfaces and discovery briefs for threat coverage; supply labeled datasets when milestones 3–4 begin.
- **Infra/DevOps:** Engage during Milestones 2–4 to validate storage, deployment, and observability assumptions.
- **Product Owner:** Own acceptance criteria for milestone deliverables, manage backlog grooming ahead of implementation phase.

## Immediate Next Steps
1. Break down Milestone 1 into specific tickets (core module extraction, adapter interfaces, config consolidation).
2. Schedule review session to walk stakeholders through the refactor plan and capture risks.
3. Set up baseline regression tests to guard current CLI behaviour during refactor.

## Open Questions
- Which certificate transparency sources and rate limits will we target once discovery begins?
- What artefact retention requirements will Legal/Security mandate for post-incident auditing?
- Do we need tenant-aware configuration before Milestone 4, or can it wait for post-readiness implementation?
