"""Decision logic — compare the cheapest fare to the target and to last time.

Returns a small Decision describing whether the price is below target and
whether it dropped since the last recorded check. An alert is warranted when
the price is below target.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Decision:
    below_target: bool
    dropped: bool
    drop_amount: float
    alert: bool


def decide(total_price: float, last_price: float | None, target_price: float) -> Decision:
    below_target = total_price < target_price
    dropped = last_price is not None and total_price < last_price
    drop_amount = round(last_price - total_price, 2) if dropped else 0.0
    return Decision(
        below_target=below_target,
        dropped=dropped,
        drop_amount=drop_amount,
        alert=below_target,
    )


def should_send_alert(
    decision: Decision, total_price: float, last_alert_price: float | None
) -> bool:
    """Whether a below-target price is worth a fresh alert.

    Send when the fare is below target and either we have never alerted for it
    before, or the price is now lower than the last alerted price. This stops the
    same below-target fare from re-alerting on every run while still notifying
    when it gets cheaper.
    """
    if not decision.alert:
        return False
    if last_alert_price is None:
        return True
    return total_price < last_alert_price
