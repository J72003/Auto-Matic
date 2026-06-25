# DealerLot — Product Docs

Every feature follows the same lightweight process (this is how scrum teams at Cox work):

```
PRD  →  validate decisions  →  SPEC (flows · diagrams · roadmap)  →  build  →  tests
```

- **PRD** = *what* and *why* (problem, users, goals, requirements, decisions to sign off).
- **SPEC** = *how* (architecture, algorithms, API, diagrams, test plan, milestone roadmap).

## Index

| # | Feature | PRD | Spec | Status |
|---|---|---|---|---|
| 01 | Aging & Holding-Cost Intelligence (Days-on-Lot) | [PRD-01](./PRD-01-days-on-lot.md) | [SPEC-01](./SPEC-01-days-on-lot.md) | 🟢 Approved · ready to build |

## Diagram types used in each spec
- **Context flow** — where the feature sits in the Cox ecosystem (and what it consumes/produces).
- **Architecture flow** — components and their dependencies (client → routes → services → DB).
- **Process flow** — the request/compute pipeline, step by step.
- **User flow** — what the person does, decision points included.

## The product thesis (carry into every feature)
> KBB tells a shopper what a car is worth. **DealerLot tells a dealer what to do with their
> whole lot — and watches it for them.** Each feature should push further onto the *operations /
> decisions* side of that line, where KBB structurally can't follow.
