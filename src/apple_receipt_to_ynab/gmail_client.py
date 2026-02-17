from __future__ import annotations

import base64
from dataclasses import dataclass

from apple_receipt_to_ynab.models import EmailConfig

GMAIL_READ_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"


class GmailApiError(RuntimeError):
    pass


@dataclass(frozen=True)
class GmailMessage:
    message_id: str
    raw_bytes: bytes


def build_gmail_query(
    subject_filter: str,
    sender_filter: str,
    max_age_days: int,
    query_extra: str | None = None,
) -> str:
    parts = [
        f"from:{sender_filter}",
        f'subject:"{subject_filter}"',
        f"newer_than:{max_age_days}d",
    ]
    if query_extra:
        parts.append(query_extra.strip())
    return " ".join(parts)


def fetch_gmail_messages(config: EmailConfig) -> list[GmailMessage]:
    if config.service_account_key_path is None or config.delegated_user_email is None:
        raise GmailApiError(
            "Email mode requires 'email.service_account_key_path' and 'email.delegated_user_email'."
        )

    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError
    except ModuleNotFoundError as exc:
        raise GmailApiError(
            "Gmail mode requires 'google-api-python-client'. Install dependencies with `pip install -e .`."
        ) from exc

    query = build_gmail_query(
        subject_filter=config.subject_filter,
        sender_filter=config.sender_filter,
        max_age_days=config.max_age_days,
        query_extra=config.query_extra,
    )
    try:
        credentials = service_account.Credentials.from_service_account_file(
            str(config.service_account_key_path),
            scopes=[GMAIL_READ_SCOPE],
        )
        delegated_credentials = credentials.with_subject(config.delegated_user_email)
        service = build("gmail", "v1", credentials=delegated_credentials, cache_discovery=False)
    except FileNotFoundError as exc:
        raise GmailApiError(
            f"Gmail service account key file not found: {config.service_account_key_path}"
        ) from exc
    except Exception as exc:
        raise GmailApiError(f"Failed to initialize Gmail API client: {exc}") from exc

    messages: list[GmailMessage] = []
    next_page_token: str | None = None
    while True:
        try:
            response = (
                service.users()
                .messages()
                .list(
                    userId="me",
                    q=query,
                    maxResults=config.max_results,
                    pageToken=next_page_token,
                )
                .execute()
            )
        except HttpError as exc:
            raise GmailApiError(f"Gmail API list failed: {exc}") from exc

        for item in response.get("messages", []):
            message_id = item.get("id")
            if not isinstance(message_id, str) or not message_id:
                continue
            try:
                raw_response = (
                    service.users()
                    .messages()
                    .get(userId="me", id=message_id, format="raw")
                    .execute()
                )
            except HttpError as exc:
                raise GmailApiError(f"Gmail API get failed for message {message_id}: {exc}") from exc

            raw_value = raw_response.get("raw")
            if not isinstance(raw_value, str) or not raw_value:
                raise GmailApiError(f"Gmail message {message_id} did not contain raw RFC822 content.")
            messages.append(GmailMessage(message_id=message_id, raw_bytes=_decode_base64url(raw_value)))

        next_page_token = response.get("nextPageToken")
        if not isinstance(next_page_token, str) or not next_page_token:
            break

    return messages


def _decode_base64url(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))
