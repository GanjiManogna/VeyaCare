import re


_INDIAN_MOBILE = re.compile(r"[6-9][0-9]{9}", re.ASCII)


def is_valid_indian_mobile(value: object) -> bool:
    """Return whether value is exactly a ten digit Indian mobile number."""
    return isinstance(value, str) and _INDIAN_MOBILE.fullmatch(value) is not None
