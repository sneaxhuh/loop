"""Ranks are relative indices, never probabilities of personal satisfaction."""

import math
from itertools import combinations

from .fixture import require


def validate_groups(groups, allowed, complete=False):
    require(isinstance(groups, list) and groups, "A ranking needs nonempty ordered tie groups.")
    require(all(isinstance(group, list) and group for group in groups), "Tie groups must be nonempty lists.")
    values = [value for group in groups for value in group]
    require(all(isinstance(value, str) for value in values), "Ranking ids must be strings.")
    require(len(values) == len(set(values)), "A ranking repeats a candidate.")
    require(set(values) <= set(allowed), "Ranking contains candidates outside the frozen pool.")
    if complete:
        require(set(values) == set(allowed), "Gemini must rank every supplied candidate exactly once.")
    return groups


def ranks(groups, pool=None):
    filtered = [[value for value in group if pool is None or value in pool] for group in groups]
    filtered = [group for group in filtered if group]
    result = {}
    position = 1
    for group in filtered:
        rank = position + (len(group) - 1) / 2
        result.update({value: rank for value in group})
        position += len(group)
    return result


def utilities(groups, pool, method="ordinal"):
    values = ranks(groups, pool)
    require(len(values) >= 2 and set(values) == set(pool), "Insufficient complete comparative evidence.")
    require(method in ("ordinal", "reciprocal"), "Unknown utility method.")
    if method == "reciprocal":
        return {value: 1 / rank for value, rank in values.items()}
    return {value: (len(values) - rank) / (len(values) - 1) for value, rank in values.items()}


def spearman(first, second, pool):
    """Exclude tied candidates; require at least eight remaining comparisons."""
    tied = {value for groups in (first, second) for group in groups if len(group) > 1 for value in group}
    usable = set(pool) - tied
    if len(usable) < 8:
        return None
    a, b = ranks(first, usable), ranks(second, usable)
    if set(a) != usable or set(b) != usable:
        return None
    ids = sorted(usable)
    mean_a, mean_b = sum(a.values()) / len(ids), sum(b.values()) / len(ids)
    numerator = sum((a[value] - mean_a) * (b[value] - mean_b) for value in ids)
    denominator = math.sqrt(sum((a[value] - mean_a) ** 2 for value in ids) * sum((b[value] - mean_b) ** 2 for value in ids))
    return {"rho": numerator / denominator, "compared": len(ids)} if denominator else None


def pairwise_agreement(groups, human_order):
    predicted = ranks(groups)
    pairs = [(a, b) for a, b in combinations(human_order, 2) if a in predicted and b in predicted and predicted[a] != predicted[b]]
    if not pairs:
        return None
    correct = sum(predicted[a] < predicted[b] for a, b in pairs)
    return {"agreement": correct / len(pairs), "correct": correct, "compared": len(pairs),
            "excluded_ties_or_missing": len(human_order) * (len(human_order) - 1) // 2 - len(pairs)}


def matched_agreement(first, second, human_order):
    """Compare both systems on identical pairs; neither wins by abstaining."""
    a, b = ranks(first), ranks(second)
    pairs = [(x, y) for x, y in combinations(human_order, 2)
             if x in a and y in a and x in b and y in b and a[x] != a[y] and b[x] != b[y]]
    if not pairs:
        return None
    return {"qloo": sum(a[x] < a[y] for x, y in pairs) / len(pairs),
            "gemini": sum(b[x] < b[y] for x, y in pairs) / len(pairs), "compared": len(pairs)}
