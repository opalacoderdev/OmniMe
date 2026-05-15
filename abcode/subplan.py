"""Subplan data model and topological sort."""

from dataclasses import dataclass, field


@dataclass
class Subplan:
    id: str
    phase: str
    objective: str
    prerequisites: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    completion_criterion: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "phase": self.phase,
            "objective": self.objective,
            "prerequisites": self.prerequisites,
            "steps": self.steps,
            "completion_criterion": self.completion_criterion,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Subplan":
        return cls(**d)


# ─── Topological sort ─────────────────────────────────────────────────────────

def topological_sort(subplans: list[Subplan]) -> list[Subplan]:
    index = {sp.id: sp for sp in subplans}
    visited: set[str] = set()
    visiting: set[str] = set()
    order: list[Subplan] = []

    def visit(sp: Subplan) -> None:
        if sp.id in visited:
            return
        if sp.id in visiting:
            return  # break cycle
        visiting.add(sp.id)
        for prereq_id in sp.prerequisites:
            if prereq_id in index and prereq_id != sp.id:
                visit(index[prereq_id])
        visiting.discard(sp.id)
        visited.add(sp.id)
        order.append(sp)

    for sp in subplans:
        visit(sp)
    return order
