"""Bounded anonymous purchasing policies; no household or fulfillment writers.

Amounts ending in ``cents`` are integer cents. Trial histories are alternative
outcomes for one child, never a group of children sharing one family budget.
"""
from collections import Counter
from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
import math
import re

from django.conf import settings

from apps.printing.pricing import quote_print_coins


ECONOMY_DEFAULTS = {
    "enabled": False,
    "start_date": "2026-01-01",
    "purchase_strategy": "save_for_priority",
    "monthly_family_budget_cents": None,
    "chore_money_cents": 0,
    "project_hourly_money_cents": 0,
    "exchange_shortfalls": False,
    "monthly_exchange_limit_cents": None,
    "printing": {"minutes_per_coin": None, "monthly_minutes": None, "monthly_grams": None},
    "offers": [],
}
OFFER_DEFAULTS = {
    "key": "reward", "label": "New reward", "kind": "real_world",
    "coin_price": 100, "repeat_every_days": 0, "stock": None,
    "family_cost_cents": 0, "print_minutes": 0, "print_grams": 0,
}
ECONOMY_LIMITS = {
    "max_offers": 12,
    "fields": {
        "enabled": {"type": "boolean"},
        "start_date": {"min": "2000-01-01", "max": "2100-12-31"},
        "purchase_strategy": {"choices": ["save_for_priority", "buy_affordable"]},
        "monthly_family_budget_cents": {"min": 0, "max": 1_000_000, "nullable": True},
        "chore_money_cents": {"min": 0, "max": 1_000_000},
        "project_hourly_money_cents": {"min": 0, "max": 100_000},
        "exchange_shortfalls": {"type": "boolean"},
        "monthly_exchange_limit_cents": {"min": 0, "max": 1_000_000, "nullable": True},
    },
    "printing": {
        "minutes_per_coin": {"min": 1, "max": 10_000, "nullable": True},
        "monthly_minutes": {"min": 0, "max": 44_640, "nullable": True},
        "monthly_grams": {"min": 0, "max": 100_000, "nullable": True},
    },
    "offer": {
        "key": {"max_length": 40}, "label": {"max_length": 80},
        "kind": {"choices": ["real_world", "printing"]},
        "coin_price": {"min": 0, "max": 1_000_000},
        "repeat_every_days": {"min": 0, "max": 365},
        "stock": {"min": 0, "max": 1000, "nullable": True},
        "family_cost_cents": {"min": 0, "max": 1_000_000},
        "print_minutes": {"min": 0, "max": 10_080},
        "print_grams": {"min": 0, "max": 10_000},
    },
}


def _validate(value, limits, name):
    if value is None and limits.get("nullable"):
        return
    if limits.get("type") == "boolean":
        valid = type(value) is bool
    elif "choices" in limits:
        valid = type(value) is str and value in limits["choices"]
    elif "max_length" in limits:
        valid = type(value) is str and 1 <= len(value) <= limits["max_length"] and value.strip() == value
    else:
        valid = type(value) is int and limits["min"] <= value <= limits["max"]
    if not valid:
        raise ValueError(f"Invalid economy value for {name}.")


def normalize_economy(supplied=None):
    if supplied is None:
        return deepcopy(ECONOMY_DEFAULTS)
    if not isinstance(supplied, dict) or set(supplied) - set(ECONOMY_DEFAULTS):
        raise ValueError("Unknown anonymous economy configuration fields.")
    result = {**deepcopy(ECONOMY_DEFAULTS), **deepcopy(supplied)}
    for key, limits in ECONOMY_LIMITS["fields"].items():
        if key == "start_date":
            try:
                value = date.fromisoformat(result[key])
                valid = value.isoformat() == result[key] and limits["min"] <= result[key] <= limits["max"]
            except (TypeError, ValueError):
                valid = False
            if not valid:
                raise ValueError("Economy start_date must be an ISO date from 2000 through 2100.")
        else:
            _validate(result[key], limits, key)
    printing = result["printing"]
    if not isinstance(printing, dict) or set(printing) - set(ECONOMY_DEFAULTS["printing"]):
        raise ValueError("Unknown anonymous printing configuration fields.")
    result["printing"] = {**ECONOMY_DEFAULTS["printing"], **printing}
    for key, limits in ECONOMY_LIMITS["printing"].items():
        _validate(result["printing"][key], limits, f"printing.{key}")
    offers = result["offers"]
    if type(offers) is not list or len(offers) > ECONOMY_LIMITS["max_offers"]:
        raise ValueError("Use at most twelve anonymous offers.")
    normalized, seen = [], set()
    for row in offers:
        if not isinstance(row, dict) or set(row) - set(OFFER_DEFAULTS):
            raise ValueError("Unknown anonymous offer fields; digital fulfillment is not modeled.")
        offer = {**OFFER_DEFAULTS, **row}
        for key, limits in ECONOMY_LIMITS["offer"].items():
            _validate(offer[key], limits, f"offers.{key}")
        if not re.fullmatch(r"[a-z0-9-]+", offer["key"]) or offer["key"] in seen:
            raise ValueError("Offer keys must be unique lowercase ASCII letters, numbers and hyphens.")
        seen.add(offer["key"])
        if offer["kind"] == "printing":
            if offer["print_minutes"] < 1:
                raise ValueError("A printing offer needs a positive whole-minute estimate.")
            offer["coin_price"] = quote_print_coins(offer["print_minutes"], result["printing"]["minutes_per_coin"])
        elif offer["print_minutes"] or offer["print_grams"]:
            raise ValueError("Print resource estimates belong only to printing offers.")
        normalized.append(offer)
    result["offers"] = normalized
    return result


def project_money_cents(minutes, hourly_cents):
    """Same per-entry rounding as TimecardService.generate_weekly_timecard."""
    hours = (Decimal(minutes) / 60).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return int((hours * Decimal(hourly_cents)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def exchange_quote_cents(shortfall):
    """Minimum $1 request; exact cents sufficient for the truncated Coin credit."""
    rate = Decimal(str(settings.COINS_PER_DOLLAR))
    if rate <= 0:
        raise ValueError("Money-to-Coins exchange needs a positive installed exchange rate.")
    cents = max(100, math.ceil(Decimal(shortfall) * 100 / rate))
    return cents, int(Decimal(cents) * rate / 100)


METRICS = (
    "coins_earned", "coins_exchanged", "coins_spent", "coin_balance",
    "money_earned_cents", "money_exchanged_cents", "money_remaining_cents",
    "family_cost_cents", "purchases", "blocked_coin_visits",
    "blocked_family_budget_visits", "blocked_print_budget_visits", "blocked_stock_visits",
    "print_minutes", "print_grams",
)
BLOCKS = ("coin", "family_budget", "print_budget", "stock")


class Economy:
    def __init__(self, config):
        self.config = config
        self.start_date = date.fromisoformat(config["start_date"])
        self.money = 0
        self.totals = Counter()
        self.months = {}
        self.rows = [{**offer, "unit_family_cost_cents": offer["family_cost_cents"],
                      "first_coin_affordable": None, "first_purchase": None,
                      "purchases": 0, "coins_spent": 0, "family_cost_cents": 0,
                      "stock_remaining": offer["stock"], "last_purchase": None,
                      **{f"blocked_{kind}_visits": 0 for kind in BLOCKS}}
                     for offer in config["offers"]]
        self.current = None
        self.previous_earned = 0

    def begin_day(self, day):
        month = (self.start_date + timedelta(days=day - 1)).strftime("%Y-%m")
        self.current = self.months.setdefault(month, {"month": month, "start_day": day, "end_day": day,
                                                     **{key: 0 for key in METRICS}})
        self.current["end_day"] = day

    def increment(self, key, amount):
        self.totals[key] += amount
        self.current[key] += amount

    def visit(self, trial):
        c = trial.config
        money = (c["chores_per_day"] * self.config["chore_money_cents"]
                 + project_money_cents(c["project_minutes"], self.config["project_hourly_money_cents"]))
        self.money += money
        self.increment("money_earned_cents", money)
        self._affordability(trial)
        blocked_today = set()
        for row in self.rows:
            if row["last_purchase"] is not None and (
                row["repeat_every_days"] == 0 or trial.day < row["last_purchase"] + row["repeat_every_days"]
            ):
                continue
            reason = self._blocked(row)
            if reason is None and trial.coins < row["coin_price"]:
                self._top_up(trial, row["coin_price"] - trial.coins)
                if trial.coins < row["coin_price"]:
                    reason = "coin"
            if reason:
                row[f"blocked_{reason}_visits"] += 1
                blocked_today.add(reason)
                # Exhausted stock is unavailable, rather than a saving goal.
                if self.config["purchase_strategy"] == "save_for_priority" and reason != "stock":
                    break
                continue
            self._purchase(trial, row)
        for reason in blocked_today:
            self.increment(f"blocked_{reason}_visits", 1)

    def _affordability(self, trial):
        for row in self.rows:
            if row["first_coin_affordable"] is None and trial.coins >= row["coin_price"]:
                row["first_coin_affordable"] = trial.day

    def _blocked(self, row):
        if row["stock_remaining"] == 0:
            return "stock"
        cap = self.config["monthly_family_budget_cents"]
        if cap is not None and self.current["family_cost_cents"] + row["unit_family_cost_cents"] > cap:
            return "family_budget"
        if row["kind"] == "printing":
            for metric in ("minutes", "grams"):
                cap = self.config["printing"][f"monthly_{metric}"]
                if cap is not None and self.current[f"print_{metric}"] + row[f"print_{metric}"] > cap:
                    return "print_budget"
        return None

    def _top_up(self, trial, shortfall):
        if not self.config["exchange_shortfalls"]:
            return
        cents, coins = exchange_quote_cents(shortfall)
        cap = self.config["monthly_exchange_limit_cents"]
        if cents > self.money or (cap is not None and self.current["money_exchanged_cents"] + cents > cap):
            return
        self.money -= cents
        self.increment("money_exchanged_cents", cents)
        self.increment("coins_exchanged", coins)
        # Live lifetime positive-Coin criteria include exchange credits. The
        # exchange itself does not trigger a badge evaluation.
        trial.coin_award(coins, "money_exchange")

    def _purchase(self, trial, row):
        trial.coins -= row["coin_price"]
        self.increment("coins_spent", row["coin_price"])
        self.increment("family_cost_cents", row["unit_family_cost_cents"])
        self.increment("purchases", 1)
        row["purchases"] += 1
        row["coins_spent"] += row["coin_price"]
        row["family_cost_cents"] += row["unit_family_cost_cents"]
        row["last_purchase"] = trial.day
        if row["stock_remaining"] is not None:
            row["stock_remaining"] -= 1
        if row["first_purchase"] is None:
            row["first_purchase"] = trial.day
        if row["kind"] == "printing":
            self.increment("print_minutes", row["print_minutes"])
            self.increment("print_grams", row["print_grams"])
        trial.sink_totals["printing" if row["kind"] == "printing" else "reward_purchases"]["coins"] += row["coin_price"]
        trial.record("print_purchase" if row["kind"] == "printing" else "reward_purchase",
                     coins=-row["coin_price"], target=row["label"])
        trial.milestones.setdefault("first_purchase", trial.day)

    def close_day(self, trial):
        earned = trial.earned_coins - self.totals["coins_exchanged"]
        self.increment("coins_earned", earned - self.previous_earned)
        self.previous_earned = earned
        self.current["coin_balance"] = trial.coins
        self.current["money_remaining_cents"] = self.money
        self.totals["coin_balance"] = trial.coins
        self.totals["money_remaining_cents"] = self.money

    def report(self):
        summary = {key: self.totals[key] for key in METRICS}
        summary["parent_liability_cents"] = self.money + self.totals["family_cost_cents"]
        return {"enabled": True, "summary": summary,
                "offers": [{key: value for key, value in row.items() if key != "last_purchase"} for row in self.rows],
                "months": list(self.months.values())}


def _stats(values):
    ordered = sorted(values)
    return {"p10": ordered[max(0, math.ceil(len(ordered) * .1) - 1)],
            "p50": ordered[max(0, math.ceil(len(ordered) * .5) - 1)],
            "p90": ordered[max(0, math.ceil(len(ordered) * .9) - 1)],
            "mean": round(sum(values) / len(values), 2)}


def _milestone(values):
    complete = [day for day in values if day is not None]
    stats = _stats(complete) if complete else {"p10": None, "p50": None, "p90": None}
    return {"completion_rate": len(complete) / len(values), "completed_trials": len(complete), "trials": len(values),
            **{f"p{pct}_days": stats[f"p{pct}"] for pct in (10, 50, 90)}}


def aggregate_economy(runs, config):
    if not config["enabled"]:
        return {"enabled": False}
    reports = [run["economy"] for run in runs]
    offers = []
    for index, offer in enumerate(config["offers"]):
        rows = [report["offers"][index] for report in reports]
        offers.append({**offer, "unit_family_cost_cents": offer["family_cost_cents"],
                       **{key: _milestone([row[key] for row in rows])
                                  for key in ("first_coin_affordable", "first_purchase")},
                       **{key: _stats([row[key] for row in rows])
                          for key in ("purchases", "coins_spent", "family_cost_cents",
                                      *(f"blocked_{kind}_visits" for kind in BLOCKS))},
                       "stock_remaining": None if offer["stock"] is None else _stats([row["stock_remaining"] for row in rows])})
    months = []
    for index, month in enumerate(reports[0]["months"]):
        rows = [report["months"][index] for report in reports]
        months.append({key: month[key] for key in ("month", "start_day", "end_day")}
                      | {key: _stats([row[key] for row in rows]) for key in METRICS})
    return {
        "enabled": True, "exchange_rate_coins_per_dollar": settings.COINS_PER_DOLLAR,
        "summary": {key: _stats([report["summary"][key] for report in reports])
                    for key in (*METRICS, "parent_liability_cents")},
        "offers": offers, "months": months,
        "assumptions": [
            "Each trial is an alternative history of one child, not an additional child in the household.",
            "Synthetic offers are attempted once per active visit in list order, after all modeled rewards. Zero cadence means once; positive cadence starts after the actual purchase. Stock is lifetime stock with no automatic replenishment.",
            "First Coin affordability observes the wallet at the beginning of an active visit's purchasing phase, before any same-visit exchange or spending; actual purchases may use an approved top-up.",
            "Calendar monthly budgets start at the supplied economy start_date; activity visits still use the abstract repeating week. Zero budgets prohibit positive usage; null means unlimited.",
            "Real-world rewards and prints are assumed approved and fulfilled immediately. Family cost is an entered estimate, not a price lookup, live expenditure or cash-out value for Coins.",
            "Configured chore money and one tracked-work entry per visit use per-entry hours rounded to two decimals, then cents rounded half-up. Earned money is assumed immediately approved and available; real weekly timecard generation, payment delays and external transfers are not simulated.",
            "Opt-in money-to-Coins top-ups use only this child's modeled earned-money balance, require at least $1, and obey the configured monthly exchange limit. Excess Coins stay in the wallet. Exchanges do not create another family expense.",
            "Parent liability is estimated reward/print fulfillment cost plus money still owed to the child, calculated per trial before aggregation. Monthly Coin and money balances are closing cumulative balances; other monthly metrics are period flows.",
            "Printing uses the installed ceiling quote and entered whole-minute/whole-gram estimates, with immediate completion. Printer queues, failures, refunds, actual usage and parent budget overrides are excluded.",
            "Digital-item purchases, purchasing/printing/money-related badges, savings, extra child requests beyond this policy and nominal inventory liquidation are excluded. Installed progression source rules and configured expedition visit limits remain unchanged.",
        ],
    }
