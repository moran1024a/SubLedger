"""Calendar cycles anchored to the original due date; legacy API inputs remain readable."""

LIMITS = {"day": 36500, "week": 5214, "month": 1200, "year": 100, "once": 1}
LEGACY = {"monthly": ("month", 1), "quarterly": ("month", 3), "yearly": ("year", 1)}


def normalize_cycle(kind, days=None, interval=1, *, validate=False):
    if kind == "custom_days":
        kind, interval = "day", days
    elif kind in LEGACY:
        kind, interval = LEGACY[kind]
    if kind not in LIMITS or type(interval) is not int or interval < 1:
        raise ValueError("invalid cycle")
    if validate and interval > LIMITS[kind]:
        raise ValueError(f"{kind} interval must be between 1 and {LIMITS[kind]}")
    if kind == "once" and interval != 1:
        raise ValueError("single bills must use interval 1")
    return kind, interval


def plan_cycle(plan, *, validate=False):
    return normalize_cycle(plan.cycle_type, plan.cycle_days, getattr(plan, "cycle_interval", None) or 1, validate=validate)


def cycle_step(kind, interval):
    """Return (days, months). Exactly one is nonzero for recurring cycles."""
    if kind in {"day", "week"}:
        return interval * (7 if kind == "week" else 1), 0
    return 0, interval * (12 if kind == "year" else 1)
