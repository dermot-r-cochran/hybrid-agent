"""Command-line entry point: python -m hybrid_agent "<request>" --evidence DIR."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .controller import Controller
from .llm import LLM, FakeLLM, LLMOperation
from .report import render
from .tools import local_tools


def load_scripted_llm(path: Path) -> FakeLLM:
    raw = json.loads(path.read_text())
    return FakeLLM(
        responses={op: json.dumps(resp) for op, resp in raw.items()},
        name=f"scripted:{path.name}",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hybrid_agent", description=__doc__)
    parser.add_argument("request", help="natural-language engineering question")
    parser.add_argument("--evidence", type=Path, required=True, help="evidence directory")
    parser.add_argument(
        "--llm-script",
        type=Path,
        help="JSON file of scripted LLM responses per operation (no real provider is bundled)",
    )
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    args = parser.parse_args(argv)

    metrics, tools = local_tools(args.evidence)
    models: dict[LLMOperation, LLM] = {}
    if args.llm_script:
        scripted = load_scripted_llm(args.llm_script)
        models = {op: scripted for op in LLMOperation}
    report = Controller(tools, metrics.services(), models).investigate(args.request)
    print(json.dumps(report.to_dict(), indent=2) if args.json else render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
