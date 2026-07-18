from __future__ import annotations


def _non_negative(**values: float) -> None:
    if any(float(value) < 0 for value in values.values()):
        raise ValueError("Deal inputs cannot be negative.")


def calculate_mao(arv: float, target_pct: float, repairs: float, closing_costs: float, holding_costs: float, wholesale_fee: float) -> float:
    _non_negative(arv=arv, target_pct=target_pct, repairs=repairs, closing_costs=closing_costs, holding_costs=holding_costs, wholesale_fee=wholesale_fee)
    if target_pct > 1:
        target_pct = target_pct / 100
    if target_pct > 1:
        raise ValueError("Target percentage cannot exceed 100%.")
    return round((arv * target_pct) - repairs - closing_costs - holding_costs - wholesale_fee, 2)


def analyze_deal(
    *,
    arv: float,
    purchase_price: float,
    repairs: float = 0,
    closing_costs: float = 0,
    holding_costs: float = 0,
    marketing_costs: float = 0,
    misc_costs: float = 0,
    wholesale_fee: float = 10000,
    target_pct: float = 0.70,
) -> dict[str, float | str]:
    """Return a complete wholesale deal summary.

    Projected profit assumes an end buyer pays ``ARV * target_pct``. The
    assignment fee is also reported separately as the wholesaler's target fee.
    """
    values = {
        "arv": arv, "purchase_price": purchase_price, "repairs": repairs,
        "closing_costs": closing_costs, "holding_costs": holding_costs,
        "marketing_costs": marketing_costs, "misc_costs": misc_costs,
        "wholesale_fee": wholesale_fee, "target_pct": target_pct,
    }
    _non_negative(**values)
    pct = target_pct / 100 if target_pct > 1 else target_pct
    if pct > 1:
        raise ValueError("Target percentage cannot exceed 100%.")

    mao = round((arv * pct) - repairs - closing_costs - holding_costs - marketing_costs - misc_costs - wholesale_fee, 2)
    total_costs = round(repairs + closing_costs + holding_costs + marketing_costs + misc_costs, 2)
    total_investment = round(purchase_price + total_costs, 2)
    buyer_price = round(arv * pct, 2)
    projected_profit = round(buyer_price - total_investment, 2)
    roi = round((projected_profit / total_investment) * 100, 2) if total_investment else 0.0

    if projected_profit >= max(wholesale_fee, 20000) and roi >= 15:
        score = "Excellent"
    elif projected_profit >= max(wholesale_fee, 10000) and roi >= 8:
        score = "Good"
    elif projected_profit > 0:
        score = "Marginal"
    else:
        score = "Bad"

    return {
        "mao": mao,
        "buyer_price": buyer_price,
        "total_costs": total_costs,
        "total_investment": total_investment,
        "projected_profit": projected_profit,
        "roi": roi,
        "deal_score": score,
    }
