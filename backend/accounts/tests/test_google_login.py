"""
Google login tests.

We never call Google in tests. Instead we replace (monkeypatch) the function that
verifies the token with a fake that returns whatever payload the test wants.
That lets us test our own logic, the three find/link/create cases, quickly and offline.
"""
import pytest

from accounts.models import OAuthAccount, User
from conftest import PASSWORD

pytestmark = pytest.mark.django_db

URL = "/api/auth/google/"
VERIFY_PATH = "accounts.serializers.id_token.verify_oauth2_token"


def google_payload(**overrides):
    payload = {
        "sub": "google-user-123",
        "email": "marko@gmail.com",
        "email_verified": True,
        "given_name": "Marko",
        "family_name": "Petrović",
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def fake_google(monkeypatch):
    """Call fake_google(payload) to decide what 'Google' returns for the next login."""
    def _set(payload):
        monkeypatch.setattr(VERIFY_PATH, lambda token, request, client_id: payload)
    return _set


def test_new_user_is_created(api_client, fake_google):
    fake_google(google_payload())
    response = api_client.post(URL, {"credential": "fake"}, format="json")

    assert response.status_code == 200
    assert "access" in response.data
    user = User.objects.get(email="marko@gmail.com")
    assert user.email_verified_at is not None
    assert user.has_usable_password() is False
    assert OAuthAccount.objects.filter(user=user, provider_user_id="google-user-123").exists()


def test_returning_user_does_not_create_duplicates(api_client, fake_google):
    fake_google(google_payload())
    api_client.post(URL, {"credential": "fake"}, format="json")
    api_client.post(URL, {"credential": "fake"}, format="json")

    assert User.objects.count() == 1
    assert OAuthAccount.objects.count() == 1


def test_returning_user_matched_by_sub_even_if_google_email_changed(api_client, fake_google):
    fake_google(google_payload())
    api_client.post(URL, {"credential": "fake"}, format="json")

    fake_google(google_payload(email="new-address@gmail.com"))
    response = api_client.post(URL, {"credential": "fake"}, format="json")

    assert response.data["user"]["email"] == "marko@gmail.com"
    assert User.objects.count() == 1


def test_links_to_existing_verified_account_and_keeps_password(api_client, fake_google, make_user):
    from django.utils import timezone
    existing = make_user(email="marko@gmail.com", email_verified_at=timezone.now())

    fake_google(google_payload())
    response = api_client.post(URL, {"credential": "fake"}, format="json")

    assert response.status_code == 200
    assert User.objects.count() == 1
    existing.refresh_from_db()
    assert existing.check_password(PASSWORD)           # both login methods keep working
    assert OAuthAccount.objects.filter(user=existing).exists()


def test_pre_hijacking_unverified_account_loses_its_password(api_client, fake_google, make_user):
    """
    Attacker registered the victim's email with their own password but never verified it.
    When the real owner signs in with Google, the attacker's password must stop working.
    """
    hijacked = make_user(email="marko@gmail.com", password="Napadac-Lozinka-123")
    assert hijacked.email_verified_at is None

    fake_google(google_payload())
    api_client.post(URL, {"credential": "fake"}, format="json")

    hijacked.refresh_from_db()
    assert hijacked.has_usable_password() is False
    assert hijacked.email_verified_at is not None


def test_invalid_google_token_is_rejected(api_client, monkeypatch):
    def raise_invalid(token, request, client_id):
        raise ValueError("bad token")
    monkeypatch.setattr(VERIFY_PATH, raise_invalid)

    response = api_client.post(URL, {"credential": "fake"}, format="json")

    assert response.status_code == 400
    assert not User.objects.exists()


def test_unverified_google_email_is_rejected(api_client, fake_google):
    fake_google(google_payload(email_verified=False))
    response = api_client.post(URL, {"credential": "fake"}, format="json")

    assert response.status_code == 400
    assert not User.objects.exists()


def test_deactivated_user_cannot_log_in_with_google(api_client, fake_google, make_user):
    from django.utils import timezone
    make_user(email="marko@gmail.com", email_verified_at=timezone.now(), is_active=False)

    fake_google(google_payload())
    response = api_client.post(URL, {"credential": "fake"}, format="json")

    assert response.status_code == 403
