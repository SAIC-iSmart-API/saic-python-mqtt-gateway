def value_in_range(value, min_incl, max_excl) -> bool:
    return value is not None and min_incl <= value < max_excl
