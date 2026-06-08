"""Central settings. Paths, column names, and matching tolerances live here so the
rest of the pipeline never hardcodes them. Adjust here, not in the logic."""

from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
OUTPUT_DIR = Path(__file__).parent / "report" / "output"

# BenchRec ships three splits. We build and measure on train (it has the labels);
# eval and solution are held back as an untouched final test.
TRAIN_FILE = DATA_DIR / "BenchRec_cash_v1.0_train.csv"
EVAL_FILE = DATA_DIR / "BenchRec_cash_v1.0_eval.csv"
SOLUTION_FILE = DATA_DIR / "BenchRec_cash_v1.0_solution.csv"

# Each row in BenchRec is one side of a potential match. A-rows are internal ledger
# entries, B-rows are external bank statement entries. The fields come in A_/B_ pairs.
SIDE_COLUMN = "A_transactionType"  # presence of A_ fields vs B_ fields tells us the side
LABEL_COLUMN = "targetAllocation"  # the ground-truth allocation key we predict against

# The fields that actually drive matching, named without the A_/B_ prefix.
# ingest will pull A_<field> or B_<field> depending on the row's side.
MATCH_FIELDS = [
    "id",
    "amount",
    "valueDate",
    "importDate",
    "currencyCode",
    "account",
    "debitOrCredit",
    "transactionReferences",
    "transactionAttributes",
]

# The allocation key is a composite the benchmark scores against. Inspection showed it
# is built as currency_valueDate_account_attributes, and a single statement row can map
# to several allocations, written as a bracketed comma-separated list.
ALLOCATION_LIST_OPEN = "["
ALLOCATION_LIST_CLOSE = "]"
ALLOCATION_LIST_SEP = ","

# 150k rows is slow to iterate on. Build and test on a slice; set to None for the full
# run that produces the final measured number.
SAMPLE_ROWS = 5000

# Matching tolerances. Dates in BenchRec are clean ISO, but bank vs ledger still differ
# by settlement lag, so we allow a window. Amounts reach billions and real matches differ
# by small relative deltas (fees, rounding, FX), so amount tolerance is proportional, not
# a fixed cent value. A match also expects opposite debit/credit signs between the two
# sides, so the matcher compares absolute amounts and treats the sign as a consistency check.
DATE_WINDOW_DAYS = 4
AMOUNT_RELATIVE_TOLERANCE = 0.001   # 0.1% of the larger amount
AMOUNT_ABSOLUTE_FLOOR = 0.01        # but never tighter than a cent, for tiny amounts

# A transaction is identified by distinctive reference codes, not just its amount. The
# exact tier requires a shared code of at least this length, to avoid matching on short
# fragments that recur across unrelated rows.
MIN_TOKEN_LENGTH = 5

# Candidate scoring blends amount and date (the signals that actually join the two sides)
# with a reference-token bonus that lifts pairs whose codes align. Amount and date form a
# base in 0..1; the token bonus adds on top to break ties between coincidental amount-twins.
WEIGHT_AMOUNT = 0.6
WEIGHT_DATE = 0.4
WEIGHT_TOKEN = 0.4    # added on top of the amount+date base, then clamped to 1.0
TOKEN_BONUS_SATURATION = 8.0   # rarity-weight at which the token bonus is effectively full

# The scored tier only commits a match at or above this confidence. Below it, the row is
# left for the split tier or routed to review rather than matched on weak evidence, in
# line with the benchmark's preference to skip rather than mismatch.
MATCH_ACCEPT_THRESHOLD = 0.75