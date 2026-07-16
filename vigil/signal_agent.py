"""Signal agent.

Answers aggregate safety questions by generating a read-only SELECT against
vw_signal_metrics, validating it (sql_guard), executing it, and summarizing
the disproportionality results. Two LLM calls (SQL, then narration); SQL
execution is injected (`run_sql`) so the agent is testable without BigQuery.
"""

from __future__ import annotations
import json
from typing import Callable, List, Tuple

from .contracts import GeneratedSQL, SignalNarration, SignalOutput, SignalRow
from .config import SIGNAL_AGENT_VERSION, SIGNAL_PROMPT_VERSION
from .llm import StructuredLLM, LLMMeta
from .sql_guard import validate_readonly

RunSQL = Callable[[str], List[dict]]

SQLGEN_SYSTEM = """You generate ONE read-only BigQuery SELECT to answer a pharmacovigilance
signal question, querying only the view {view}.
Columns: event_pt, a, b, c, d, n_total, prr, ror, signal_flag
(a 2x2 disproportionality table per adverse-event MedDRA PT for the in-scope product;
prr = proportional reporting ratio, ror = reporting odds ratio, signal_flag = PRR>=2 and a>=3).
Rules: SELECT only; query ONLY {view}; select the full column set unless asked otherwise;
order by the metric implied by the question (usually prr DESC); always include a LIMIT.
Never write DML or DDL.
"""

NARRATE_SYSTEM = """Summarize the disproportionality results for the user's question in 2-4 sentences.
Be precise and cautious: PRR/ROR are screening signals from spontaneous, unverified reports,
not confirmed risks. List caveats (small cell counts, reporting/confounding bias, no denominator
of exposure). Do not overstate causation.
"""


class SignalAgent:
    name = "signal"
    version = SIGNAL_AGENT_VERSION
    prompt_version = SIGNAL_PROMPT_VERSION

    def __init__(self, llm: StructuredLLM, run_sql: RunSQL, view_fqn: str):
        self._llm = llm
        self._run = run_sql
        self._view_fqn = view_fqn  # e.g. proj.pv_vigil.vw_signal_metrics
        self._view_name = view_fqn.split(".")[-1]  # vw_signal_metrics

    def _default_sql(self) -> str:
        return (
            f"SELECT event_pt, a, b, c, d, n_total, prr, ror, signal_flag "
            f"FROM `{self._view_fqn}` ORDER BY prr DESC LIMIT 25"
        )

    def answer(self, question: str) -> Tuple[SignalOutput, List[LLMMeta]]:
        # 1) generate SQL
        gen, meta1 = self._llm.generate(
            system=SQLGEN_SYSTEM.format(view=f"`{self._view_fqn}`"),
            user=question,
            schema=GeneratedSQL,
            temperature=0.0,
        )
        caveats: List[str] = []
        ok, reason, safe_sql = validate_readonly(gen.sql, {self._view_name})
        if not ok:
            safe_sql = self._default_sql()
            caveats.append(
                f"generated SQL rejected ({reason}); used a safe default query"
            )

        # 2) execute (injected)
        rows = self._run(safe_sql)
        fields = set(SignalRow.model_fields)
        results = [
            SignalRow(**{k: v for k, v in r.items() if k in fields}) for r in rows
        ]

        # 3) summarize
        narr, meta2 = self._llm.generate(
            system=NARRATE_SYSTEM,
            user=_render(question, results),
            schema=SignalNarration,
            temperature=0.2,
        )
        caveats.extend(narr.caveats)

        return SignalOutput(
            generated_sql=safe_sql,
            results=results,
            summary=narr.summary,
            caveats=caveats,
        ), [meta1, meta2]


def _render(question: str, rows: List[SignalRow]) -> str:
    top = [r.model_dump() for r in rows[:25]]
    return (
        f"Question: {question}\n\nResults (top {len(top)} rows):\n"
        f"{json.dumps(top, indent=2)}"
    )
