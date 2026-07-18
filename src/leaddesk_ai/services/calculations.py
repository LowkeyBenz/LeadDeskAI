def calculate_mao(arv: float, target_pct: float, repairs: float, closing_costs: float, holding_costs: float, wholesale_fee: float) -> float:
    values = [arv, target_pct, repairs, closing_costs, holding_costs, wholesale_fee]
    if any(float(v) < 0 for v in values):
        raise ValueError("Deal inputs cannot be negative.")
    if target_pct > 1:
        target_pct = target_pct / 100
    return round((arv * target_pct) - repairs - closing_costs - holding_costs - wholesale_fee, 2)
