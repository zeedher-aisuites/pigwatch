# Architecture Decision Records

ADRs capture decisions that materially affect component boundaries, contracts, data semantics, security, operations, or technology choices.

## Process

1. Copy `0000-template.md` to the next four-digit number and a short kebab-case title.
2. Set status to `Proposed` while the decision is under review.
3. Describe context, decision, consequences, and alternatives without rewriting history.
4. Link the ADR from the pull request and relevant architecture/specification documents.
5. Change status to `Accepted` when approved. To reverse it, add a new ADR and mark the old one `Superseded by ADR-NNNN`.

Accepted ADRs are immutable except for status and links. Small implementation details that do not affect architecture do not require an ADR.
