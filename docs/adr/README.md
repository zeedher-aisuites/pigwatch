# Architecture Decision Records

ADRs capture decisions that materially affect component boundaries, contracts, data semantics, security, operations, or technology choices.

## Process

1. Copy `0000-template.md` to the next four-digit number and a short kebab-case title.
2. Set status to `Proposed` while the decision is under review.
3. Describe context, decision, consequences, and alternatives without rewriting history.
4. Link the ADR from the pull request and relevant architecture/specification documents.
5. Keep the ADR `Proposed` while its implementation pull request is under review.
6. After explicit Product Owner approval, change it to `Accepted` in the approved pull request before merge; merging that pull request adopts the decision. A merged ADR without explicit approval remains `Proposed`.
7. To reverse an accepted decision, add a new ADR and mark the old one `Superseded by ADR-NNNN`.

Accepted ADRs are immutable except for status and links. Proposed ADRs may be revised in response to review. Small implementation details that do not affect architecture do not require an ADR.
