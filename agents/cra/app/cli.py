"""Interactive terminal interface for clause-level LEXGUARD analysis."""

from __future__ import annotations

from orchestration.clause_pipeline import ClauseAnalysisPipeline


def get_contract_input() -> str:
    print()
    print("=" * 70)
    print("LEXGUARD - COMBINED CONTRACT AND LITIGATION RISK ANALYSIS")
    print("=" * 70)
    print("Paste one clause for analysis. Type 'quit' to exit.")
    return input("Clause: ").strip()


def main() -> None:
    print("\n" + "=" * 70)
    print("INITIALIZING LEXGUARD")
    print("=" * 70)

    try:
        pipeline = ClauseAnalysisPipeline()
    except Exception as exc:
        print("\nLEXGUARD INITIALIZATION FAILED")
        print(f"{type(exc).__name__}: {exc}")
        return

    print("\nLEXGUARD READY")

    while True:
        user_input = get_contract_input()
        if user_input.lower() in {"quit", "exit", "q"}:
            print("\nExiting LEXGUARD.")
            break
        if not user_input:
            print("Please enter a clause.")
            continue

        try:
            result = pipeline.analyze(user_input)
            pipeline.print_result(result)
        except KeyboardInterrupt:
            print("\nAnalysis interrupted.")
        except Exception as exc:
            print("\nLEXGUARD ANALYSIS FAILED")
            print(f"{type(exc).__name__}: {exc}")
            print("Correct the clause or intake and try again.")


if __name__ == "__main__":
    main()
