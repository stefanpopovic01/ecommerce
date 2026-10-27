import re

from rest_framework.test import APIClient

LINK_RE = re.compile(r"uid=([^&\s]+)&token=([^\s]+)")


def uid_and_token(message):
    """Pull uid and token out of the link in an email, like the frontend page would."""
    match = LINK_RE.search(message.body)
    assert match, f"No uid/token link found in email body:\n{message.body}"
    return match.group(1), match.group(2)


def refresh_works(refresh_token):
    """True if the refresh token can still be used to get a new access token."""
    response = APIClient().post("/api/auth/token/refresh/", {"refresh": refresh_token}, format="json")
    return response.status_code == 200
