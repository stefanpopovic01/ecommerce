import pytest

from accounts.models import User
from accounts.tests.helpers import refresh_works, uid_and_token
from conftest import PASSWORD

pytestmark = pytest.mark.django_db


# --- Password users: DELETE /me/ -----------------------------------------

def test_delete_with_correct_password(client_for, customer):
    client = client_for(customer)
    response = client.delete("/api/auth/me/", {"password": PASSWORD}, format="json")

    assert response.status_code == 204
    assert not User.objects.filter(pk=customer.pk).exists()
    assert refresh_works(client.refresh_token) is False


def test_delete_with_wrong_password_keeps_account(client_for, customer):
    response = client_for(customer).delete("/api/auth/me/", {"password": "wrong"}, format="json")

    assert response.status_code == 400
    assert User.objects.filter(pk=customer.pk).exists()


def test_staff_cannot_delete_own_account(client_for, staff_member):
    response = client_for(staff_member).delete("/api/auth/me/", {"password": PASSWORD}, format="json")

    assert response.status_code == 403
    assert User.objects.filter(pk=staff_member.pk).exists()


# --- Google-only users: email confirmation ---------------------------------

@pytest.fixture
def google_only_user(make_user):
    return make_user(email="google@gmail.com", password=None)


def test_google_only_user_cannot_use_password_delete(client_for, google_only_user):
    response = client_for(google_only_user).delete("/api/auth/me/", {"password": "anything"}, format="json")
    assert response.status_code == 400


def test_google_only_user_deletes_via_email_link(api_client, client_for, google_only_user, mailoutbox):
    client = client_for(google_only_user)
    response = client.post("/api/auth/me/delete/request/")
    assert response.status_code == 200

    uid, token = uid_and_token(mailoutbox[0])
    response = api_client.post("/api/auth/me/delete/confirm/", {"uid": uid, "token": token}, format="json")

    assert response.status_code == 204
    assert not User.objects.filter(pk=google_only_user.pk).exists()
    assert refresh_works(client.refresh_token) is False


def test_deletion_link_rejects_tampered_token(api_client, client_for, google_only_user, mailoutbox):
    client_for(google_only_user).post("/api/auth/me/delete/request/")
    uid, token = uid_and_token(mailoutbox[0])

    response = api_client.post("/api/auth/me/delete/confirm/", {"uid": uid, "token": token + "x"}, format="json")

    assert response.status_code == 400
    assert User.objects.filter(pk=google_only_user.pk).exists()


def test_password_user_cannot_request_deletion_email(client_for, customer, mailoutbox):
    response = client_for(customer).post("/api/auth/me/delete/request/")

    assert response.status_code == 400
    assert len(mailoutbox) == 0
