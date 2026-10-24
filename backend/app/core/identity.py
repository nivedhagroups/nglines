import re


def normalize_phone(value: str) -> str:
    raw = value.strip()
    digits = re.sub(r"[\s()-]", "", raw)
    if digits.startswith("00"):
        digits = "+" + digits[2:]
    if not digits.startswith("+"):
        if len(digits) == 10 and digits[0] in "6789":
            digits = "+91" + digits
        elif len(digits) == 12 and digits.startswith("91"):
            digits = "+" + digits
    if not re.fullmatch(r"\+[1-9]\d{7,14}", digits):
        raise ValueError("Enter a valid phone number in international or 10-digit Indian format")
    return digits