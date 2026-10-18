import pandas as pd

# Load training data
df = pd.read_csv("data/train.csv")

print("=" * 80)
print("DATASET INSPECTION")
print("=" * 80)

print("\nColumns:")
print(df.columns.tolist())

print("\nDataset size:")
print(len(df))

# ---------------------------------------------------------
# Risk distribution
# ---------------------------------------------------------

print("\n" + "=" * 80)
print("RISK DISTRIBUTION")
print("=" * 80)

print(df["risk"].value_counts(dropna=False))

# ---------------------------------------------------------
# Numeric label distribution
# ---------------------------------------------------------

print("\n" + "=" * 80)
print("LABEL DISTRIBUTION")
print("=" * 80)

print(df["label"].value_counts(dropna=False).sort_index())

# ---------------------------------------------------------
# Verify risk -> label mapping
# ---------------------------------------------------------

print("\n" + "=" * 80)
print("RISK -> LABEL MAPPING")
print("=" * 80)

mapping = (
    df[["risk", "label"]]
    .drop_duplicates()
    .sort_values("label")
)

print(mapping.to_string(index=False))

# ---------------------------------------------------------
# Distribution by category and risk
# ---------------------------------------------------------

print("\n" + "=" * 80)
print("CATEGORY x RISK DISTRIBUTION")
print("=" * 80)

print(
    pd.crosstab(
        df["category"],
        df["risk"]
    )
)

# ---------------------------------------------------------
# Show random examples from each risk class
# ---------------------------------------------------------

for risk in df["risk"].dropna().unique():

    subset = df[df["risk"] == risk]

    print("\n\n" + "=" * 100)
    print(f"RISK CLASS: {risk}")
    print(f"TOTAL TRAINING EXAMPLES: {len(subset)}")
    print("=" * 100)

    samples = subset.sample(
        n=min(10, len(subset)),
        random_state=42
    )

    for number, (_, row) in enumerate(samples.iterrows(), start=1):

        print("\n" + "-" * 100)
        print(f"EXAMPLE {number}")
        print("-" * 100)

        print(f"Category        : {row['category']}")
        print(f"Contract family : {row['contract_family']}")
        print(f"Variant type    : {row['variant_type']}")
        print(f"Risk            : {row['risk']}")
        print(f"Numeric label   : {row['label']}")

        print("\nTEXT:")
        print(row["text"])


print("\n\n" + "=" * 100)
print("INSPECTION COMPLETE")
print("=" * 100)