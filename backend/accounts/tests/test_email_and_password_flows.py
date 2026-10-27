import pytest

from accounts.models import User
from accounts.tests.helpers import refresh_works, uid_and_token
from conftest import PASSWORD

pytestmark = pytest.mark.django_db

NEW_PASSWORD = "Nova-Jaka-Lozinka-77"


# --- Email verification -----------------------------------------------------

def test_verify_email_with_link_from_email(api_client, client_for, customer, mailoutbox):
    client_for(customer).post("/api/auth/verify-email/resend/")
    uid, token = uid_and_token(mailoutbox[0])

    response = api_client.post("/api/auth/verify-email/", {"uid": uid, "token": token}, format="json")

    assert response.status_code == 200
    customer.refresh_from_db()
    assert customer.email_verified_at is not None


def test_verify_email_link_clicked_twice_still_succeeds(api_client, client_for, customer, mailoutbox):
    client_for(customer).post("/api/auth/verify-email/resend/")
    uid, token = uid_and_token(mailoutbox[0])

    api_client.post("/api/auth/verify-email/", {"uid": uid, "token": token}, format="json")
    second = api_client.post("/api/auth/verify-email/", {"uid": uid, "token": token}, format="json")
    assert second.status_code == 200


def test_verify_email_rejects_tampered_token(api_client, client_for, customer, mailoutbox):
    client_for(customer).post("/api/auth/verify-email/resend/")
    uid, token = uid_and_token(mailoutbox[0])

    response = api_client.post("/api/auth/verify-email/", {"uid": uid, "token": token + "x"}, format="json")

    assert response.status_code == 400
    customer.refresh_from_db()
    assert customer.email_verified_at is None


def test_verify_email_rejects_garbage_uid(api_client):
    response = api_client.post("/api/auth/verify-email/", {"uid": "not-base64!!", "token": "abc"}, format="json")
    assert response.status_code == 400


def test_resend_verification_refused_when_already_verified(client_for, make_user, mailoutbox):
    from django.utils import timezone
    user = make_user(email_verified_at=timezone.now())
    response = client_for(user).post("/api/auth/verify-email/resend/")
    assert response.status_code == 400
    assert len(mailoutbox) == 0


# --- Password reset ---------------------------------------------------------

def test_password_reset_unknown_email_gives_same_response(api_client, customer, mailoutbox):
    known = api_client.post("/api/auth/password-reset/", {"email": customer.email}, format="json")
    unknown = api_client.post("/api/auth/password-reset/", {"email": "nobody@example.com"}, format="json")

    assert known.status_code == unknown.status_code == 200
    assert known.data == unknown.data           # no way to tell which emails have accounts
    assert len(mailoutbox) == 1                  # only the real account got an email


def test_password_reset_full_flow(api_client, client_for, customer, mailoutbox):
    old_session = client_for(customer)
    api_client.post("/api/auth/password-reset/", {"email": customer.email}, format="json")
    uid, token = uid_and_token(mailoutbox[0])

    response = api_client.post(
        "/api/auth/password-reset/confirm/",
        {"uid": uid, "token": token, "password": NEW_PASSWORD},
        format="json",
    )

    assert response.status_code == 200
    customer.refresh_from_db()
    assert customer.check_password(NEW_PASSWORD)
    assert not customer.check_password(PASSWORD)
    assert customer.email_verified_at is not None          # clicking the email link proves inbox ownership
    assert refresh_works(old_session.refresh_token) is False  # old sessions are logged out


def test_password_reset_link_works_only_once(api_client, customer, mailoutbox):
    api_client.post("/api/auth/password-reset/", {"email": customer.email}, format="json")
    uid, token = uid_and_token(mailoutbox[0])
    payload = {"uid": uid, "token": token, "password": NEW_PASSWORD}

    assert api_client.post("/api/auth/password-reset/confirm/", payload, format="json").status_code == 200
    payload["password"] = "Jos-Jedna-Lozinka-99"
    assert api_client.post("/api/auth/password-reset/confirm/", payload, format="json").status_code == 400


def test_password_reset_rejects_weak_password(api_client, customer, mailoutbox):
    api_client.post("/api/auth/password-reset/", {"email": customer.email}, format="json")
    uid, token = uid_and_token(mailoutbox[0])

    response = api_client.post(
        "/api/auth/password-reset/confirm/", {"uid": uid, "token": token, "password": "123"}, format="json"
    )

    assert response.status_code == 400
    customer.refresh_from_db()
    assert customer.check_password(PASSWORD)


def test_password_reset_not_sent_to_inactive_user(api_client, make_user, mailoutbox):
    user = make_user(is_active=False)
    api_client.post("/api/auth/password-reset/", {"email": user.email}, format="json")
    assert len(mailoutbox) == 0


# --- Change password --------------------------------------------------------

def test_change_password_logs_out_other_sessions_and_returns_new_tokens(client_for, customer):
    other_device = client_for(customer)
    this_device = client_for(customer)

    response = this_device.post(
        "/api/auth/password-change/",
        {"old_password": PASSWORD, "new_password": NEW_PASSWORD},
        format="json",
    )

    assert response.status_code == 200
    customer.refresh_from_db()
    assert customer.check_password(NEW_PASSWORD)
    assert refresh_works(other_device.refresh_token) is False
    assert refresh_works(this_device.refresh_token) is False
    assert refresh_works(response.data["refresh"]) is True     # the new token pair works


def test_change_password_wrong_old_password(client_for, customer):
    response = client_for(customer).post(
        "/api/auth/password-change/", {"old_password": "wrong", "new_password": NEW_PASSWORD}, format="json"
    )
    assert response.status_code == 400
    assert "old_password" in response.data


def test_change_password_same_as_old_is_rejected(client_for, customer):
    response = client_for(customer).post(
        "/api/auth/password-change/", {"old_password": PASSWORD, "new_password": PASSWORD}, format="json"
    )
    assert response.status_code == 400
    assert "new_password" in response.data


def test_change_password_refused_for_google_only_user(client_for, make_user):
    user = make_user(password=None)
    response = client_for(user).post(
        "/api/auth/password-change/", {"old_password": "x", "new_password": NEW_PASSWORD}, format="json"
    )
    assert response.status_code == 400
