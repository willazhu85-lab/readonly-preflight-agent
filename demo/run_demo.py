"""Run three synthetic candidates offline. Temporary traces are removed on exit."""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from preflight_agent.llm import ScriptedModel
from preflight_agent.runner import run


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="preflight-demo-") as directory:
        for name in ("clean", "blocked", "review"):
            trace = run("demo-" + name, ROOT / "examples" / name, Path(directory), model=ScriptedModel())
            print(f"\n{name.upper()} -> {trace['final_draft']['decision']}")
            for step in trace["steps"]:
                reasons = ", ".join(step["reason_codes"]) or "OK"
                print(f"  {step['tool']:10} {step['status']:10} {reasons}")
            advisory = trace["final_draft"]["advisory"]
            print("  Explanation:", advisory["explanation"])
            print("  Next step:  ", advisory["suggested_next_step"])
            print("  Human approval required; model authority: none.")
            assert run("demo-" + name, ROOT / "examples" / name, Path(directory), model=ScriptedModel()) == trace
            print("  Replay: identical trace, no second model call.")


if __name__ == "__main__":
    main()
