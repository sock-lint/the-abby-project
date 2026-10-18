"""Pure Coin quotes shared by print approval and anonymous planning."""


def quote_print_coins(estimated_minutes, minutes_per_coin):
    """Quote whole Coins for a validated estimate; a null rate is free.

    Callers validate positive whole minutes and a positive enabled rate before
    quoting. A started request retains its saved quote when policy changes.
    """
    if minutes_per_coin is None:
        return 0
    return (estimated_minutes + minutes_per_coin - 1) // minutes_per_coin
