"""Plain-text rendering of a report for human review."""

from __future__ import annotations

from .models import Report


def render(report: Report) -> str:
    out = [f"REQUEST: {report.request}"]
    if report.task:
        out.append(f"TASK: service={report.task.service} metric={report.task.metric.value}")

    out.append("\nOBSERVATIONS (read by tools)")
    out += [f"  [{e.id}] {e.summary}" for e in report.observations] or ["  none"]

    out.append("\nDERIVED RESULTS (computed)")
    out += [f"  [{e.id}] {e.summary}" for e in report.derived] or ["  none"]

    out.append("\nHYPOTHESES (LLM proposals, not evidence)")
    for i, h in enumerate(report.hypotheses, 1):
        verdict = "passed checks" if h.passed_checks else "FAILED checks"
        out.append(f"  H{i} [{verdict}] {h.statement}")
        out.append(f"      cites: {', '.join(h.evidence_ids) or 'nothing'}")
        out += [f"      ! {issue}" for issue in h.verification_issues]
    if not report.hypotheses:
        out.append("  none")

    out.append("\nUNKNOWNS")
    out += [f"  - {u}" for u in report.unknowns] or ["  none"]

    out.append("\nPROPOSED ACTIONS (not executed; require human approval)")
    for i, a in enumerate(report.actions, 1):
        out.append(f"  A{i} {a.description}")
        if a.rationale:
            out.append(f"      why: {a.rationale}")
    if not report.actions:
        out.append("  none")

    out.append("\nTRACE (operation -> mechanism)")
    out += [f"  {s.operation:<20} {s.mechanism.value:<13} {s.detail}" for s in report.trace]

    if report.verification_issues:
        out.append("\nREPORT VERIFICATION ISSUES")
        out += [f"  ! {issue}" for issue in report.verification_issues]

    out.append(f"\nSTATUS: {report.status}")
    return "\n".join(out)
