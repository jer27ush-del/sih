from datetime import date


def days_to_maturity(maturity_date: date, today: date | None = None) -> int:
    """Whole calendar days; negative once the maturity date has passed."""
    today = today or date.today()
    return (maturity_date - today).days


def reminder_window(days: int, thresholds: list[int]) -> int | None:
    """The tightest configured threshold the FDR has crossed (e.g. 30 when 25 days remain).
    Returning only the tightest window means one reminder per window, not one per threshold."""
    crossed = [t for t in thresholds if days <= t]
    return min(crossed) if crossed else None
