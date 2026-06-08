"""Profile the real BenchRec train file before we build anything against it.

We don't want to design ingest or the scoring metric around an assumed schema, so this
reads the labelled training split and reports what's actually there: the columns, how
rows split into ledger (A) vs statement (B) sides, what the allocation-key label looks
like, the match cardinality (1:1 vs 1:many vs unmatched), and the amount/date conventions.

Run it once, read the output, then we build. It writes nothing and changes nothing.
"""

import sys
from collections import Counter

import pandas as pd

import config


def load_train():
    path = config.TRAIN_FILE
    if not path.exists():
        sys.exit(
            f"Could not find {path}. Download BenchRec from Kaggle into the data/ "
            f"folder first (see README)."
        )
    # Everything stays as string on load so we can see the raw formatting (date styles,
    # amount signs, stray whitespace) before pandas guesses types for us.
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def describe_columns(df):
    print(f"rows: {len(df):,}")
    print(f"columns ({len(df.columns)}): {', '.join(df.columns)}")
    print()


def describe_sides(df):
    """Each row carries either the A_ fields or the B_ fields. Work out the split by
    checking which id is populated, since that's the cleanest signal of which side a
    row belongs to."""
    has_a = df["A_id"].str.strip().ne("")
    has_b = df["B_id"].str.strip().ne("")

    a_only = (has_a & ~has_b).sum()
    b_only = (has_b & ~has_a).sum()
    both = (has_a & has_b).sum()
    neither = (~has_a & ~has_b).sum()

    print("row sides (by which id is populated):")
    print(f"  ledger side only (A):     {a_only:,}")
    print(f"  statement side only (B):  {b_only:,}")
    print(f"  both A and B populated:   {both:,}")
    print(f"  neither populated:        {neither:,}")
    print()


def describe_label(df):
    """The label is the allocation key. We want to know how often it's present, what it
    looks like, and whether blank means 'no match expected'."""
    label = df[config.LABEL_COLUMN].str.strip()
    present = label.ne("").sum()
    blank = label.eq("").sum()

    print(f"label column: {config.LABEL_COLUMN}")
    print(f"  present: {present:,}    blank: {blank:,}")
    print("  sample non-blank values:")
    for value in label[label.ne("")].head(3):
        print(f"    {value[:160]}")
    print()


def describe_cardinality(df):
    """How many B-statement rows map to one allocation, and how many allocations get
    several rows. This sizes the splits/subset-sum tier: if most matches are 1:1 it's a
    minor case, if many are 1:N it's central."""
    matched = df[df[config.LABEL_COLUMN].str.strip().ne("")]
    per_allocation = matched.groupby(config.LABEL_COLUMN).size()

    counts = Counter(per_allocation.values)
    print("rows sharing a single allocation key (match cardinality):")
    for size in sorted(counts):
        label = "one-to-one" if size == 1 else f"{size} rows to one allocation"
        print(f"  {label}: {counts[size]:,} allocation groups")
    print()


def describe_amounts(df):
    """Confirm sign and scale conventions before the matcher trusts them. Debits and
    credits may carry opposite signs, and split rows won't sum cleanly if we get this
    wrong."""
    for side in ("A", "B"):
        amounts = pd.to_numeric(df[f"{side}_amount"], errors="coerce").dropna()
        if amounts.empty:
            continue
        print(f"{side}_amount: count {len(amounts):,}, "
              f"min {amounts.min():,.2f}, max {amounts.max():,.2f}, "
              f"negative {(amounts < 0).sum():,}, positive {(amounts > 0).sum():,}")
    print()

    for side in ("A", "B"):
        col = f"{side}_debitOrCredit"
        if col in df.columns:
            values = df[col].str.strip()
            present = values[values.ne("")]
            print(f"{col}: {dict(present.value_counts())}")
    print()


def describe_dates(df):
    """Show raw date strings per side so we can see the format(s) before parsing. Mixed
    formats here are exactly what trips up naive date comparison."""
    for col in ("A_valueDate", "A_importDate", "B_valueDate", "B_importDate"):
        if col not in df.columns:
            continue
        values = df[col].str.strip()
        present = values[values.ne("")]
        if present.empty:
            continue
        print(f"{col}: {present.iloc[0]!r} ... {present.iloc[-1]!r} "
              f"({present.nunique():,} distinct)")
    print()


def describe_allocation_source(df):
    """The A-ledger rows carry their own A_allocation. If a matched B-row's
    targetAllocation is built from the A_allocation of the rows it matches, then we can
    construct a predicted key directly from a candidate ledger row. Check that link."""
    a_alloc = df["A_allocation"].str.strip()
    a_present = a_alloc[a_alloc.ne("")]
    print(f"A_allocation: present {len(a_present):,}")
    if not a_present.empty:
        print("  sample A_allocation values:")
        for value in a_present.head(2):
            print(f"    {value[:160]}")
    # Do any A_allocation strings show up verbatim inside a targetAllocation? If so, the
    # target is literally assembled from matched A rows' allocations.
    targets = set(df[config.LABEL_COLUMN].str.strip())
    direct_hits = sum(1 for v in a_present.head(2000) if v in targets)
    print(f"  of first 2000 A_allocations, appear verbatim as a targetAllocation: {direct_hits:,}")
    print()


def main():
    df = load_train()
    describe_columns(df)
    describe_sides(df)
    describe_label(df)
    describe_allocation_source(df)
    describe_cardinality(df)
    describe_amounts(df)
    describe_dates(df)


if __name__ == "__main__":
    main()