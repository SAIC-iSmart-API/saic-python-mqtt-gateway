def value_in_range(value, min_incl, max_excl) -> bool:
    return value is not None and min_incl <= value < max_excl


def is_valid_temperature(value) -> bool:
    return value_in_range(value, -127, 127) and value != 87
