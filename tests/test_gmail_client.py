from apple_receipt_to_ynab.gmail_client import build_gmail_query


def test_build_gmail_query_uses_expected_default_shape() -> None:
    query = build_gmail_query(
        subject_filter="Your receipt from Apple.",
        sender_filter="no_reply@email.apple.com",
        max_age_days=7,
    )
    assert query == 'from:no_reply@email.apple.com subject:"Your receipt from Apple." newer_than:7d'


def test_build_gmail_query_appends_extra_fragment_when_present() -> None:
    query = build_gmail_query(
        subject_filter="Your receipt from Apple.",
        sender_filter="no_reply@email.apple.com",
        max_age_days=7,
        query_extra="in:inbox",
    )
    assert query.endswith("in:inbox")
