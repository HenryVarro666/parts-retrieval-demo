import math
from collections import defaultdict


def rrf(rankings: dict[str, list[str]], k: int = 60, top_k: int = 10) -> list[tuple[str, float]]:
    """Reciprocal rank fusion over channels; a channel that abstains passes an empty list.

    Each channel contributes 1 / (k + rank) for its top_k items. k=60 is the value
    from the original RRF paper and is not tuned on this eval set. Exact ties (two
    channels with mirrored ranks) go to the better single-channel rank, then to the
    part id, so the order in which channels are passed never decides.
    """
    contrib: dict[str, list[float]] = defaultdict(list)
    best_rank: dict[str, int] = {}
    for ranked in rankings.values():
        for r, item in enumerate(ranked[:top_k], start=1):
            contrib[item].append(1.0 / (k + r))
            best_rank[item] = min(best_rank.get(item, r), r)
    # fsum is exactly rounded, so equal totals stay equal whatever order they were added in.
    scores = {item: math.fsum(c) for item, c in contrib.items()}
    return sorted(scores.items(), key=lambda kv: (-kv[1], best_rank[kv[0]], kv[0]))
