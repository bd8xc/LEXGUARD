"""
LEXGUARD — Litigation Exposure Agent
Step 2: Local LLM Synthetic Dataset Generation

Model  : LLaMA 3.1 8B Instruct (Q4_K_M GGUF)
Runtime: llama-cpp-python with CUDA backend (8GB VRAM)
Feature: Grammar-constrained JSON generation — zero parsing failures

Setup (one-time):
    # 1. Install llama-cpp-python with CUDA support
    CMAKE_ARGS="-DGGML_CUDA=on" pip install llama-cpp-python --force-reinstall --no-cache-dir

    # 2. Download the model (4.9 GB)
    huggingface-cli download \
        bartowski/Meta-Llama-3.1-8B-Instruct-GGUF \
        Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf \
        --local-dir ./models/llm

Usage:
    python generate_synthetic_data_local.py
    python generate_synthetic_data_local.py --model-path /path/to/your.gguf
    python generate_synthetic_data_local.py --rows 7500 --batch-size 30
"""

import argparse
import json
import random
import time
from pathlib import Path

import numpy as np
import pandas as pd
from tqdm import tqdm


# ──────────────────────────────────────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────────────────────────────────────

DEFAULT_MODEL_PATH = Path("models/llm/Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf")
OUTPUT_PATH        = Path("data/litigation_training_data.csv")

TOTAL_RECORDS  = 7_500
BATCH_SIZE     = 30       # Smaller batches = more reliable JSON from 8B model
MAX_RETRIES    = 4

STANDARD_RATIO  = 0.70
AMBIGUOUS_RATIO = 0.20
EDGE_RATIO      = 0.10

FEATURES = [
    "deal_size",
    "liability_cap",
    "auto_renewal",
    "jurisdiction_risk",
    "conflict_flag",
    "clause_deviation_score",
    "indemnification_clause",
    "dispute_history",
    "governing_law_clarity",
    "litigated",
]


# ──────────────────────────────────────────────────────────────────────────────
# JSON Grammar Schema
# Enforced by llama-cpp-python's grammar engine — guarantees valid JSON output
# ──────────────────────────────────────────────────────────────────────────────

# We build the schema once; llama.cpp converts it to a GBNF grammar internally
RECORD_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "deal_size":              {"type": "integer", "minimum": 50000,  "maximum": 5000000},
            "liability_cap":          {"type": "integer", "enum": [0, 1]},
            "auto_renewal":           {"type": "integer", "enum": [0, 1]},
            "jurisdiction_risk":      {"type": "integer", "minimum": 1, "maximum": 10},
            "conflict_flag":          {"type": "integer", "enum": [0, 1]},
            "clause_deviation_score": {"type": "number",  "minimum": 0.0, "maximum": 1.0},
            "indemnification_clause": {"type": "integer", "enum": [0, 1]},
            "dispute_history":        {"type": "integer", "enum": [0, 1]},
            "governing_law_clarity":  {"type": "integer", "minimum": 1, "maximum": 5},
            "litigated":              {"type": "integer", "enum": [0, 1]},
        },
        "required": [
            "deal_size", "liability_cap", "auto_renewal", "jurisdiction_risk",
            "conflict_flag", "clause_deviation_score", "indemnification_clause",
            "dispute_history", "governing_law_clarity", "litigated"
        ],
    },
}


# ──────────────────────────────────────────────────────────────────────────────
# Prompts
# ──────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a senior legal risk analyst with 25+ years of experience reviewing commercial contracts, litigation outcomes, procurement disputes, cross-border agreements, and corporate governance matters.

Generate synthetic commercial contract records for training a litigation risk prediction model.

CRITICAL RULES:
- No single feature should deterministically predict litigation.
- Litigation arises from the INTERACTION of multiple factors.
- Real legal disputes are messy — contradictory signals are expected and required.
- Generate combinations a senior lawyer would consider plausible.

FIELD DEFINITIONS:
deal_size              : integer, USD 50000–5000000
liability_cap          : 0=absent, 1=present (protective)
auto_renewal           : 0=absent, 1=present (minor risk)
jurisdiction_risk      : 1=stable to 10=highly adversarial
conflict_flag          : 0=none, 1=conflict of interest detected
clause_deviation_score : 0.0=standard clauses to 1.0=max deviation
indemnification_clause : 0=weak/absent, 1=strong and clearly scoped
dispute_history        : 0=none, 1=prior disputes with same counterparty
governing_law_clarity  : 1=vague/contested to 5=clear and predictable
litigated              : 0=no dispute, 1=formal litigation occurred (TARGET)

FEATURE INTERACTION GUIDANCE:
- High clause_deviation_score + strong indemnification_clause can cancel out
- High jurisdiction_risk + low governing_law_clarity = elevated compound risk
- dispute_history=1 raises risk but counterparties do reform behaviour
- conflict_flag matters but many conflict situations are remediated quietly
- Large deal_size attracts more scrutiny but also more motivation to settle
- liability_cap=1 is protective but disputes over its scope still happen

Target litigation rate across all records: 40–55%.
Output ONLY a valid JSON array. No markdown, no explanation, no comments."""


def user_prompt_standard(n: int) -> str:
    return f"""Generate {n} standard commercial contract records.
Represent typical agreements across industries — varied outcomes.
Approximately 40–50% should result in litigation.
Vary all features realistically across the full range.
Output a JSON array of {n} objects."""


def user_prompt_ambiguous(n: int) -> str:
    return f"""Generate {n} AMBIGUOUS commercial contract records.
Each record must have at least two features pulling in opposite risk directions.
Examples of contradictions to include:
- High clause_deviation_score (0.7+) BUT strong indemnification_clause=1
- conflict_flag=1 BUT governing_law_clarity=4 or 5
- dispute_history=1 BUT liability_cap=1 AND low jurisdiction_risk
- High deal_size BUT clear governing law and strong indemnification
Approximately 45–55% should result in litigation — close to a coin flip.
Output a JSON array of {n} objects."""


def user_prompt_edge(n: int) -> str:
    # Distribute edge case patterns across the batch
    patterns = [
        "conflict_flag=1 but litigated=0 (conflict was remediated before escalation)",
        "conflict_flag=0 but litigated=1 (no conflict but operational dispute emerged)",
        "deal_size above 2000000 but litigated=0 (large deal, parties chose arbitration or settled)",
        "deal_size below 150000 but litigated=1 (small deal, principle at stake or bad-faith party)",
        "jurisdiction_risk=8 or higher but litigated=0 (strong contract protections held)",
        "jurisdiction_risk=2 or lower but litigated=1 (stable jurisdiction, internal factors drove dispute)",
        "liability_cap=1 but litigated=1 (dispute over scope or interpretation of the cap)",
        "liability_cap=0 but litigated=0 (no cap, but relationship managed without escalation)",
        "dispute_history=1 but litigated=0 (prior disputes but remediation worked this time)",
        "indemnification_clause=1 but litigated=1 (strong indemnification but scope disputed)",
        "clause_deviation_score above 0.75 but litigated=0 (deviations accepted by both parties)",
        "governing_law_clarity=1 but litigated=0 (vague law, parties settled informally)",
    ]
    # Rotate patterns across batches for diversity
    selected = (patterns * ((n // len(patterns)) + 1))[:n]
    random.shuffle(selected)
    pattern_str = "\n".join(f"- Record {i+1}: {p}" for i, p in enumerate(selected))

    return f"""Generate {n} DIFFICULT EDGE CASE commercial contract records.
These are hard real-world situations where intuition fails.
Each record has a specific pattern to follow:

{pattern_str}

All other features should be set to realistic values that support the described scenario.
Output a JSON array of {n} objects."""


# ──────────────────────────────────────────────────────────────────────────────
# Model loader
# ──────────────────────────────────────────────────────────────────────────────

def load_model(model_path: Path):
    """Load LLaMA GGUF model with CUDA offload."""
    try:
        from llama_cpp import Llama
    except ImportError:
        raise ImportError(
            "\nllama-cpp-python is not installed.\n"
            "Install with CUDA support:\n"
            "  CMAKE_ARGS=\"-DGGML_CUDA=on\" "
            "pip install llama-cpp-python --force-reinstall --no-cache-dir\n"
        )

    if not model_path.exists():
        raise FileNotFoundError(
            f"\nModel not found at: {model_path}\n"
            "Download with:\n"
            "  huggingface-cli download \\\n"
            "      bartowski/Meta-Llama-3.1-8B-Instruct-GGUF \\\n"
            "      Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf \\\n"
            "      --local-dir ./models/llm\n"
        )

    print(f"[model] Loading {model_path.name}...")
    print("[model] Offloading all layers to GPU (n_gpu_layers=-1)...")

    llm = Llama(
        model_path    = str(model_path),
        n_ctx         = 8192,      # LLaMA 3.1 supports 128k but 8k is enough here
        n_gpu_layers  = -1,        # Offload everything to CUDA
        n_batch       = 512,       # Prompt processing batch size
        n_threads     = 4,         # CPU threads for non-GPU ops
        verbose       = False,     # Suppress llama.cpp log spam
        flash_attn    = True,      # Flash attention — faster on RTX series
    )

    print("[model] Model loaded and ready.\n")
    return llm


# ──────────────────────────────────────────────────────────────────────────────
# Generation
# ──────────────────────────────────────────────────────────────────────────────

def generate_batch(
    llm,
    system: str,
    user: str,
    batch_type: str,
    attempt: int = 0,
) -> list[dict]:
    """Generate one batch with JSON schema enforcement."""
    from llama_cpp import LlamaGrammar

    try:
        # Build LLaMA 3.1 chat format
        prompt = (
            "<|begin_of_text|>"
            "<|start_header_id|>system<|end_header_id|>\n\n"
            f"{system}"
            "<|eot_id|>"
            "<|start_header_id|>user<|end_header_id|>\n\n"
            f"{user}"
            "<|eot_id|>"
            "<|start_header_id|>assistant<|end_header_id|>\n\n"
        )

        # JSON schema grammar — guarantees structurally valid output
        grammar = LlamaGrammar.from_json_schema(json.dumps(RECORD_SCHEMA))

        response = llm(
            prompt,
            max_tokens  = 6000,
            temperature = 0.85,    # Enough variance for realistic diversity
            top_p       = 0.92,
            repeat_penalty = 1.1,
            grammar     = grammar,
            echo        = False,
        )

        raw = response["choices"][0]["text"].strip()

        # Grammar guarantees valid JSON — but clean defensively anyway
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        records = json.loads(raw)

        if not isinstance(records, list):
            raise ValueError("Response is not a JSON array")

        valid = [clean_record(r) for r in records if validate_record(r)]
        return valid

    except Exception as e:
        if attempt < MAX_RETRIES:
            wait = 2 * (attempt + 1)
            print(f"\n  [retry {attempt+1}/{MAX_RETRIES}] {batch_type}: {e}. Retrying in {wait}s...")
            time.sleep(wait)
            return generate_batch(llm, system, user, batch_type, attempt + 1)
        else:
            print(f"\n  [SKIP] {batch_type} batch failed after {MAX_RETRIES} retries: {e}")
            return []


# ──────────────────────────────────────────────────────────────────────────────
# Validation & cleaning
# ──────────────────────────────────────────────────────────────────────────────

def validate_record(r: dict) -> bool:
    try:
        assert isinstance(r.get("deal_size"), (int, float)) and 50_000 <= r["deal_size"] <= 5_000_000
        assert r.get("liability_cap") in (0, 1)
        assert r.get("auto_renewal") in (0, 1)
        assert isinstance(r.get("jurisdiction_risk"), (int, float)) and 1 <= r["jurisdiction_risk"] <= 10
        assert r.get("conflict_flag") in (0, 1)
        assert isinstance(r.get("clause_deviation_score"), (int, float)) and 0.0 <= r["clause_deviation_score"] <= 1.0
        assert r.get("indemnification_clause") in (0, 1)
        assert r.get("dispute_history") in (0, 1)
        assert isinstance(r.get("governing_law_clarity"), (int, float)) and 1 <= r["governing_law_clarity"] <= 5
        assert r.get("litigated") in (0, 1)
        return True
    except (AssertionError, TypeError):
        return False


def clean_record(r: dict) -> dict:
    return {
        "deal_size":              int(round(r["deal_size"])),
        "liability_cap":          int(r["liability_cap"]),
        "auto_renewal":           int(r["auto_renewal"]),
        "jurisdiction_risk":      int(round(r["jurisdiction_risk"])),
        "conflict_flag":          int(r["conflict_flag"]),
        "clause_deviation_score": round(float(r["clause_deviation_score"]), 4),
        "indemnification_clause": int(r["indemnification_clause"]),
        "dispute_history":        int(r["dispute_history"]),
        "governing_law_clarity":  int(round(r["governing_law_clarity"])),
        "litigated":              int(r["litigated"]),
    }


def assign_litigation_labels(df: pd.DataFrame, seed: int = 42) -> pd.DataFrame:
    """Assign reproducible, domain-directed synthetic labels.

    The LLM generates plausible feature combinations, but it must not be the
    source of truth for outcomes: otherwise protective features can acquire the
    wrong relationship with litigation.  A calibrated logistic process retains
    realistic noise while enforcing the intended feature directions.
    """
    required = set(FEATURES) - {"litigated"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"Cannot label data; missing columns: {', '.join(missing)}")

    deal_scale = np.log(df["deal_size"].clip(lower=50_000) / 50_000) / np.log(100)
    log_odds = (
        -1.00
        + 0.40 * deal_scale
        - 0.90 * df["liability_cap"]
        + 0.25 * df["auto_renewal"]
        + 0.20 * (df["jurisdiction_risk"] - 5.5)
        + 1.00 * df["conflict_flag"]
        + 1.20 * df["clause_deviation_score"]
        - 0.80 * df["indemnification_clause"]
        + 0.80 * df["dispute_history"]
        + 0.35 * (3.0 - df["governing_law_clarity"])
        + 0.35 * (df["jurisdiction_risk"] >= 7) * (df["governing_law_clarity"] <= 2)
        - 0.30 * (df["clause_deviation_score"] >= 0.7) * df["indemnification_clause"]
    )
    probability = 1.0 / (1.0 + np.exp(-(log_odds + np.random.default_rng(seed).normal(0, 0.45, len(df)))))
    labelled = df.copy()
    labelled["litigated"] = np.random.default_rng(seed + 1).binomial(1, probability)
    return labelled


# ──────────────────────────────────────────────────────────────────────────────
# Plan
# ──────────────────────────────────────────────────────────────────────────────

def build_plan(total: int, batch_size: int) -> list[tuple[str, int]]:
    std = int(total * STANDARD_RATIO)
    amb = int(total * AMBIGUOUS_RATIO)
    edg = total - std - amb

    plan = []
    plan += [("standard",  batch_size)] * (std // batch_size)
    plan += [("ambiguous", batch_size)] * (amb // batch_size)
    plan += [("edge_case", batch_size)] * (edg // batch_size)

    rem_s, rem_a, rem_e = std % batch_size, amb % batch_size, edg % batch_size
    if rem_s: plan.append(("standard",  rem_s))
    if rem_a: plan.append(("ambiguous", rem_a))
    if rem_e: plan.append(("edge_case", rem_e))

    random.seed(42)
    random.shuffle(plan)
    return plan


def user_prompt_for(batch_type: str, n: int) -> str:
    if batch_type == "standard":  return user_prompt_standard(n)
    if batch_type == "ambiguous": return user_prompt_ambiguous(n)
    return user_prompt_edge(n)


# ──────────────────────────────────────────────────────────────────────────────
# Stats
# ──────────────────────────────────────────────────────────────────────────────

def print_stats(df: pd.DataFrame):
    rate = df["litigated"].mean()
    print(f"\n{'='*70}")
    print("Dataset Statistics")
    print(f"  Rows              : {len(df):,}")
    print(f"  Litigation rate   : {rate:.1%}  (target: 40–55%)")
    print(f"  Dispute records   : {df['litigated'].sum():,}")
    print(f"  No-dispute records: {(df['litigated']==0).sum():,}")

    print("\nFeature–Target Correlations (Pearson |r|)")
    for feat in FEATURES[:-1]:
        corr = df[feat].corr(df["litigated"])
        bar  = "█" * int(abs(corr) * 40)
        sign = "+" if corr >= 0 else "-"
        print(f"  {feat:<28} {sign}{abs(corr):.3f} {bar}")

    max_corr = max(abs(df[f].corr(df["litigated"])) for f in FEATURES[:-1])
    if max_corr > 0.65:
        print(f"\n[WARN] Max correlation {max_corr:.3f} is high — one feature may dominate.")
    else:
        print(f"\n[OK]   Max correlation {max_corr:.3f} — no single feature dominates.")

    if not (0.35 <= rate <= 0.60):
        print(f"[WARN] Litigation rate {rate:.1%} outside 40–55% target.")
    else:
        print("[OK]   Litigation rate within target.")


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="LEXGUARD Local Data Generator")
    parser.add_argument("--model-path", type=Path, default=DEFAULT_MODEL_PATH,
                        help="Path to GGUF model file")
    parser.add_argument("--rows",       type=int,  default=TOTAL_RECORDS,
                        help="Total records to generate")
    parser.add_argument("--batch-size", type=int,  default=BATCH_SIZE,
                        help="Records per LLM call (default 30 for 8B model)")
    parser.add_argument("--relabel-existing", type=Path,
                        help="Relabel an existing CSV using the calibrated synthetic policy")
    args = parser.parse_args()

    if args.relabel_existing:
        input_path = args.relabel_existing
        relabelled = assign_litigation_labels(pd.read_csv(input_path))
        relabelled.to_csv(input_path, index=False)
        print(f"Relabelled -> {input_path} ({len(relabelled):,} rows; litigation rate {relabelled['litigated'].mean():.1%})")
        return

    print("=" * 70)
    print("LEXGUARD — Local Synthetic Data Generator")
    print("Model      : LLaMA 3.1 8B Instruct Q4_K_M")
    print(f"Target rows: {args.rows:,}")
    print(f"Batch size : {args.batch_size}")
    print(f"Features   : {len(FEATURES)-1} + 1 target")
    print("=" * 70)

    # Load model
    llm = load_model(args.model_path)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    plan           = build_plan(args.rows, args.batch_size)
    all_records    = []
    failed_batches = 0

    # Type counts for info
    type_counts = {}
    for t, n in plan:
        type_counts[t] = type_counts.get(t, 0) + n
    print(f"\nGeneration plan: {len(plan)} batches")
    for t, n in sorted(type_counts.items()):
        print(f"  {t:<12}: {n:,} records")
    print()

    pbar = tqdm(plan, desc="Generating", unit="batch")

    for batch_type, n in pbar:
        pbar.set_postfix({
            "type":      batch_type[:3],
            "collected": len(all_records),
            "failed":    failed_batches,
        })

        records = generate_batch(
            llm,
            SYSTEM_PROMPT,
            user_prompt_for(batch_type, n),
            batch_type,
        )

        if records:
            all_records.extend(records)
        else:
            failed_batches += 1

    pbar.close()

    if not all_records:
        print("\n[ERROR] No records generated. Check GPU memory and model path.")
        return

    df = pd.DataFrame(all_records, columns=FEATURES)
    df["deal_size"]             = df["deal_size"].astype(int)
    df["jurisdiction_risk"]     = df["jurisdiction_risk"].astype(int)
    df["governing_law_clarity"] = df["governing_law_clarity"].astype(int)
    df["clause_deviation_score"]= df["clause_deviation_score"].round(4)
    df = assign_litigation_labels(df)

    print_stats(df)

    df.to_csv(OUTPUT_PATH, index=False)
    print(f"\nSaved -> {OUTPUT_PATH}  ({len(df):,} rows)")


if __name__ == "__main__":
    main()
