def outreach_allowed(channel: str, preference: dict) -> tuple[bool, str]:
    if preference.get("internal_dnc"):
        return False, "Internal do-not-contact restriction"
    if preference.get("opt_out"):
        return False, "Recipient opted out"
    key = {"call": "call_allowed", "text": "text_allowed", "email": "email_allowed", "mail": "mail_allowed"}.get(channel.lower())
    if not key:
        return False, "Unknown channel"
    if not preference.get(key):
        return False, f"{channel.title()} permission is not recorded"
    return True, "Allowed by recorded preference"
