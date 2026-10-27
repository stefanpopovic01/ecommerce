import pytest

from accounts.models import User
from conftest import PASSWORD

pytestmark = pytest.mark.django_db

REGISTER_URL = "/api/auth/register/"
LOGIN_URL = "/api/auth/login/"


def register_payload(**overrides):
    data = {"email": "marko@example.com", "first_name": "Marko", "last_name": "Petrović", "password": PASSWORD}
    data.update(overrides)
    return data


# --- Registration ---------------------------------------------------------

def test_register_creates_customer_and_sends_verification_email(api_client, mailoutbox, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        response = api_client.post(REGISTER_URL, register_payload(), format="json")

    assert response.status_code == 201
    user = User.objects.get(email="marko@example.com")
    assert user.check_password(PASSWORD)          # stored hashed, and correct
    assert user.password != PASSWORD              # never stored as plain text
    assert user.email_verified_at is None
    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == ["marko@example.com"]


def test_register_response_never_contains_password(api_client):
    response = api_client.post(REGISTER_URL, register_payload(), format="json")
    assert "password" not in response.data


def test_register_ignores_privilege_fields(api_client):
    """Mass assignment: extra fields in the request must not reach the user."""
    payload = register_payload(is_staff=True, is_superuser=True, email_verified_at="2020-01-01T00:00:00Z")
    response = api_client.post(REGISTER_URL, payload, format="json")

    assert response.status_code == 201
    user = User.objects.get(email="marko@example.com")
    assert user.is_staff is False
    assert user.is_superuser is False
    assert user.email_verified_at is None


def test_register_lowercases_email(api_client):
    api_client.post(REGISTER_URL, register_payload(email="Marko@Example.COM"), format="json")
    assert User.objects.filter(email="marko@example.com").exists()


def test_register_rejects_duplicate_email_in_any_case(api_client, make_user):
    make_user(email="marko@example.com")
    response = api_client.post(REGISTER_URL, register_payload(email="MARKO@example.com"), format="json")

    assert response.status_code == 400
    assert "email" in response.data


@pytest.mark.parametrize("weak_password", ["short", "12345678901", "password123"])
def test_register_rejects_weak_passwords(api_client, weak_password):
    response = api_client.post(REGISTER_URL, register_payload(password=weak_password), format="json")

    assert response.status_code == 400
    assert "password" in response.data
    assert not User.objects.exists()


def test_register_is_throttled(api_client):
    for i in range(5):
        api_client.post(REGISTER_URL, register_payload(email=f"user{i}@example.com"), format="json")
    response = api_client.post(REGISTER_URL, register_payload(email="sixth@example.com"), format="json")
    assert response.status_code == 429


# --- Login ----------------------------------------------------------------

def test_login_returns_tokens_and_user(api_client, customer):
    response = api_client.post(LOGIN_URL, {"email": customer.email, "password": PASSWORD}, format="json")

    assert response.status_code == 200
    assert "access" in response.data
    assert "refresh" in response.data
    assert response.data["user"]["email"] == customer.email


def test_login_is_case_insensitive(api_client, customer):
    response = api_client.post(LOGIN_URL, {"email": "KUPAC@Example.com", "password": PASSWORD}, format="json")
    assert response.status_code == 200


def test_login_wrong_password(api_client, customer):
    response = api_client.post(LOGIN_URL, {"email": customer.email, "password": "wrong-password"}, format="json")
    assert response.status_code == 401


def test_login_inactive_user_fails(api_client, make_user):
    user = make_user(is_active=False)
    response = api_client.post(LOGIN_URL, {"email": user.email, "password": PASSWORD}, format="json")
    assert response.status_code == 401


def test_unverified_user_can_log_in(api_client, customer):
    """Decision from design: verification is not required to log in."""
    assert customer.email_verified_at is None
    response = api_client.post(LOGIN_URL, {"email": customer.email, "password": PASSWORD}, format="json")
    assert response.status_code == 200


# --- Logout and refresh ---------------------------------------------------

def test_logout_blacklists_refresh_token(client_for, customer):
    client = client_for(customer)
    response = client.post("/api/auth/logout/", {"refresh": client.refresh_token}, format="json")
    assert response.status_code == 200

    from accounts.tests.helpers import refresh_works
    assert refresh_works(client.refresh_token) is False


# --- Profile (/me/) ---------------------------------------------------------

def test_me_requires_authentication(api_client):
    assert api_client.get("/api/auth/me/").status_code == 401


def test_me_returns_own_profile(client_for, customer):
    response = client_for(customer).get("/api/auth/me/")
    assert response.status_code == 200
    assert response.data["email"] == customer.email
    assert response.data["has_password"] is True


def test_me_patch_updates_name_but_not_protected_fields(client_for, customer):
    response = client_for(customer).patch(
        "/api/auth/me/",
        {"first_name": "Novo", "email": "hacker@example.com", "is_staff": True},
        format="json",
    )
    assert response.status_code == 200
    customer.refresh_from_db()
    assert customer.first_name == "Novo"
    assert customer.email == "kupac@example.com"
    assert customer.is_staff is False


def test_me_put_is_not_allowed(client_for, customer):
    response = client_for(customer).put("/api/auth/me/", {"first_name": "X", "last_name": "Y"}, format="json")
    assert response.status_code == 405
