"""Weight reference tokens by how rare they are.

The token diagnostic showed a few codes (like '66912' on most rows) are standing prefixes
that identify nothing, while thousands of codes appear once and pin a transaction exactly.
Inverse document frequency captures that: a token's weight falls as the number of rows it
appears on rises. Two rows sharing a rare code is strong evidence; sharing a ubiquitous
one is almost none.

We build the model once from all rows up front, then scoring reads weights from it.
"""

import math
from collections import Counter

from matching.compare import _distinctive_tokens


class TokenWeights:
    def __init__(self, rows):
        document_frequency = Counter()
        for row in rows:
            for token in _distinctive_tokens(row):
                document_frequency[token] += 1
        self._df = document_frequency
        self._total = max(1, len(rows))

    def weight(self, token):
        """Standard smoothed IDF. A token on every row tends to zero; a token on one row
        is near the maximum. Unseen tokens get the maximum, treated as maximally rare."""
        df = self._df.get(token, 0)
        return math.log((self._total + 1) / (df + 1))

    def shared_weight(self, ledger_row, statement_row):
        """Total rarity-weighted evidence from the tokens two rows share. This is the core
        identity signal: high when they share rare codes, near zero when they only share
        boilerplate."""
        shared = _distinctive_tokens(ledger_row) & _distinctive_tokens(statement_row)
        return sum(self.weight(token) for token in shared)

    def self_weight(self, row):
        """The total rarity weight a row carries, used to normalize shared evidence into a
        0..1 similarity rather than an unbounded sum."""
        return sum(self.weight(token) for token in _distinctive_tokens(row)) or 1.0
