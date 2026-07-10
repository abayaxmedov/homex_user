def normalize_phone(value):
    """Canonicalize a phone number to a single ``+<digits>`` form.

    OTP throttling/cooldown and the OTPRecord lookup key off the phone, but the
    actual SMS recipient is derived by stripping to digits. Without a single
    canonical form, ``+998901234567``, ``998901234567`` and ``+998-90-123-45-67``
    all reach the same handset yet map to DISTINCT cooldown keys — which lets an
    attacker bypass the per-phone cooldown and SMS-bomb one number. Normalizing
    once, up front, collapses every format variant to one key.
    """
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    return f"+{digits}" if digits else ""
