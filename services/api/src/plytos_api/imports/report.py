"""Renders an import result as Markdown, for the command line and for review."""

from plytos_api.imports.model import Finding, ImportResult

_SEVERITY_TITLES = {"fix": "Fix", "improve": "Improve", "note": "Notes"}


def to_markdown(result: ImportResult) -> str:
    counts = {s: sum(1 for f in result.findings if f.severity == s) for s in _SEVERITY_TITLES}
    out = [
        f"# Import audit: {result.facts.filename}",
        "",
        f"{len(result.roles)} roles and {len(result.cards)} proposed cards. "
        f"{counts['fix']} to fix, {counts['improve']} to improve, {counts['note']} notes.",
    ]
    for severity, title in _SEVERITY_TITLES.items():
        group = [f for f in result.findings if f.severity == severity]
        if not group:
            continue
        out += ["", f"## {title}"]
        for finding in group:
            out += _finding(finding)

    out += ["", "## Proposed cards"]
    by_role: dict[str | None, list[str]] = {}
    for card in result.cards:
        flags = f" _({', '.join(card.findings)})_" if card.findings else ""
        line = f"- **{card.kind}**: {card.content.framing.headline}{flags}"
        if card.needs_check:
            line += "\n  - Check: " + " ".join(card.needs_check)
        by_role.setdefault(card.role_ref, []).append(line)
    for role in result.roles:
        dates = role.dates.raw if role.dates else "no dates"
        if role.client:
            who = f"{role.title or '?'}, {role.client} (through {role.organization})"
        else:
            who = f"{role.title or '?'}, {role.organization or '?'}"
        out += ["", f"### {who} ({dates})"]
        out += by_role.pop(role.ref, [])
    if by_role.get(None):
        out += ["", "### Other cards", *by_role[None]]
    return "\n".join(out) + "\n"


def _finding(finding: Finding) -> list[str]:
    lines = ["", f"### {finding.title}", "", finding.detail]
    if finding.locations:
        lines.append("")
        lines += [f"- “{loc.excerpt}”" for loc in finding.locations]
    return lines
