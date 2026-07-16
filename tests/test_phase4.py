"""Offline verification for Phase 4 (no GCP).

    python tests/test_phase4.py
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from vigil.sql_guard import validate_readonly
from vigil.contracts import GeneratedSQL, SignalNarration, SignalOutput
from vigil.llm import LLMMeta
from vigil.signal_agent import SignalAgent

passed = 0
def check(name, cond):
    global passed
    assert cond, f"FAILED: {name}"
    passed += 1
    print(f"  ok  {name}")

ALLOWED = {"vw_signal_metrics"}


# ---- 1. SQL guard ----
print("sql_guard:")
ok, reason, safe = validate_readonly("SELECT * FROM `p.pv_vigil.vw_signal_metrics`", ALLOWED)
check("accepts SELECT on allowed view", ok)
check("appends a LIMIT", safe is not None and "LIMIT" in safe.upper())

ok, _, _ = validate_readonly("SELECT event_pt, prr FROM vw_signal_metrics WHERE signal_flag LIMIT 10", ALLOWED)
check("accepts qualified-or-not + existing LIMIT", ok)

ok, reason, _ = validate_readonly("DROP TABLE vw_signal_metrics", ALLOWED)
check("rejects DROP", not ok)

ok, reason, _ = validate_readonly("DELETE FROM vw_signal_metrics WHERE TRUE", ALLOWED)
check("rejects DELETE", not ok)

ok, reason, _ = validate_readonly("SELECT * FROM agt_case_output", ALLOWED)
check("rejects disallowed table", not ok and "disallowed" in reason)

ok, reason, _ = validate_readonly("SELECT 1 FROM vw_signal_metrics; DROP TABLE x", ALLOWED)
check("rejects multi-statement", not ok)

ok, _, _ = validate_readonly(
    "WITH t AS (SELECT event_pt, prr FROM vw_signal_metrics) SELECT * FROM t ORDER BY prr DESC", ALLOWED)
check("accepts CTE over allowed view", ok)


# ---- 2. signal agent (fake llm + fake runner) ----
print("signal agent:")
ROWS = [
    {"event_pt": "Myocarditis", "a": 12, "b": 300, "c": 40, "d": 9000, "n_total": 9352, "prr": 3.4, "ror": 3.6, "signal_flag": True},
    {"event_pt": "Headache", "a": 200, "b": 112, "c": 5000, "d": 4040, "n_total": 9352, "prr": 0.9, "ror": 0.8, "signal_flag": False},
]

class FakeLLM:
    model = "gemini-3-pro"
    def __init__(self, sql): self._sql = sql
    def generate(self, *, system, user, schema, temperature=0.0):
        if schema is GeneratedSQL:
            return GeneratedSQL(sql=self._sql), LLMMeta(self.model, 30, 10, 100)
        return SignalNarration(summary="Myocarditis shows an elevated PRR (3.4).",
                               caveats=["small cell counts"]), LLMMeta(self.model, 40, 20, 200)

calls = {"n": 0}
def fake_run(sql):
    calls["n"] += 1
    calls["last_sql"] = sql
    return ROWS

view = "p.pv_vigil.vw_signal_metrics"

# valid generated SQL path
agent = SignalAgent(FakeLLM("SELECT * FROM `p.pv_vigil.vw_signal_metrics` ORDER BY prr DESC"), fake_run, view)
out, metas = agent.answer("strongest signals?")
check("returns SignalOutput", isinstance(out, SignalOutput))
check("two LLM calls (sql + narration)", len(metas) == 2)
check("results coerced to SignalRow", out.results[0].event_pt == "Myocarditis" and out.results[0].prr == 3.4)
check("generated_sql is the validated SQL with LIMIT", "LIMIT" in out.generated_sql.upper())
check("summary populated", "Myocarditis" in out.summary)

# malicious generated SQL -> guard falls back to default + caveat
agent2 = SignalAgent(FakeLLM("DELETE FROM vw_signal_metrics WHERE TRUE"), fake_run, view)
out2, _ = agent2.answer("delete stuff")
check("rejected SQL falls back to safe default", "ORDER BY prr DESC" in out2.generated_sql)
check("fallback recorded as a caveat", any("rejected" in c for c in out2.caveats))
check("default query still executed", calls["n"] >= 2)

# SignalRow drops unknown columns gracefully
def fake_run_extra(sql):
    return [{"event_pt": "Pyrexia", "prr": 2.1, "unknown_col": "x"}]
agent3 = SignalAgent(FakeLLM("SELECT event_pt, prr FROM vw_signal_metrics"), fake_run_extra, view)
out3, _ = agent3.answer("q")
check("unknown columns ignored, defaults applied",
      out3.results[0].event_pt == "Pyrexia" and out3.results[0].a == 0)

print(f"\nALL {passed} CHECKS PASSED")
