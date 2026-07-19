from leaddesk_ai.services.compliance import outreach_allowed


def test_opt_out_blocks_everything():
    allowed, reason = outreach_allowed("text", {"text_allowed": True, "opt_out": True})
    assert not allowed and "opted out" in reason.lower()


def test_explicit_channel_permission():
    assert outreach_allowed("email", {"email_allowed": True})[0]
    assert not outreach_allowed("text", {"text_allowed": False})[0]
