"""
Staff API tests: the permission matrix you checked by hand in Postman, written down
so it's re-checked automatically every time you run the tests.
"""
import pytest
from django.utils import timezone

from accounts.models import User
from accounts.tests.helpers import refresh_works, uid_and_token
from conftest import PASSWORD

pytestmark = pytest.mark.django_db

USERS_URL = "/api/staff/users/"


def detail_url(user):
    return f"{USERS_URL}{user.pk}/"


def action_url(user, name):
    return f"{USERS_URL}{user.pk}/{name}/"


def emails_in(response):
    return {row["email"] for row in response.data["results"]}


# --- staff/me ---------------------------------------------------------------

def test_staff_me_forbidden_for_customer(client_for, customer):
    assert client_for(customer).get("/api/staff/me/").status_code == 403


def test_staff_me_returns_groups_and_permissions(client_for, staff_member):
    response = client_for(staff_member).get("/api/staff/me/")

    assert response.status_code == 200
    assert response.data["groups"] == ["Osoblje"]
    assert response.data["permissions"] == ["accounts.view_user"]


def test_staff_me_administrator_permissions(client_for, staff_admin):
    response = client_for(staff_admin).get("/api/staff/me/")
    assert set(response.data["permissions"]) == {
        "accounts.view_user", "accounts.add_user", "accounts.change_user",
    }


# --- Listing and viewing ----------------------------------------------------

def test_customer_cannot_list_users(client_for, customer):
    assert client_for(customer).get(USERS_URL).status_code == 403


def test_staff_can_list_users_but_not_superusers(client_for, staff_member, customer, superuser):
    response = client_for(staff_member).get(USERS_URL)

    assert response.status_code == 200
    assert customer.email in emails_in(response)
    assert superuser.email not in emails_in(response)


def test_superuser_sees_everyone(client_for, superuser, customer):
    response = client_for(superuser).get(USERS_URL)
    assert {customer.email, superuser.email} <= emails_in(response)


def test_superuser_detail_is_404_for_staff(client_for, staff_admin, superuser):
    assert client_for(staff_admin).get(detail_url(superuser)).status_code == 404


def test_search_and_filter(client_for, staff_member, make_user):
    make_user(email="ana@example.com", first_name="Ana")
    make_user(email="inactive@example.com", is_active=False)
    client = client_for(staff_member)

    assert emails_in(client.get(USERS_URL, {"search": "ana"})) == {"ana@example.com"}
    assert emails_in(client.get(USERS_URL, {"is_active": "false"})) == {"inactive@example.com"}


def test_staff_without_group_cannot_list(client_for, make_user):
    """is_staff alone opens nothing: permissions come from groups."""
    no_group = make_user(email="nogroup@example.com", is_staff=True)
    assert client_for(no_group).get(USERS_URL).status_code == 403


# --- Editing ----------------------------------------------------------------

def test_staff_cannot_edit_users(client_for, staff_member, customer):
    response = client_for(staff_member).patch(detail_url(customer), {"first_name": "X"}, format="json")
    assert response.status_code == 403


def test_administrator_can_edit_name(client_for, staff_admin, customer):
    response = client_for(staff_admin).patch(detail_url(customer), {"first_name": "Promenjeno"}, format="json")

    assert response.status_code == 200
    customer.refresh_from_db()
    assert customer.first_name == "Promenjeno"


def test_administrator_cannot_make_anyone_staff_or_superuser_via_patch(client_for, staff_admin, customer):
    client_for(staff_admin).patch(
        detail_url(customer), {"is_staff": True, "is_superuser": True, "is_active": False}, format="json"
    )
    customer.refresh_from_db()
    assert customer.is_staff is False
    assert customer.is_superuser is False
    assert customer.is_active is True


def test_plain_post_create_is_not_allowed(client_for, staff_admin):
    response = client_for(staff_admin).post(USERS_URL, {"email": "x@example.com"}, format="json")
    assert response.status_code == 405


# --- Deactivate / activate --------------------------------------------------

def test_administrator_deactivates_customer_and_logs_them_out(client_for, staff_admin, customer):
    customer_session = client_for(customer)
    response = client_for(staff_admin).post(action_url(customer, "deactivate"))

    assert response.status_code == 200
    customer.refresh_from_db()
    assert customer.is_active is False
    assert refresh_works(customer_session.refresh_token) is False


def test_administrator_reactivates(client_for, staff_admin, make_user):
    user = make_user(is_active=False)
    client_for(staff_admin).post(action_url(user, "activate"))
    user.refresh_from_db()
    assert user.is_active is True


def test_staff_cannot_deactivate(client_for, staff_member, customer):
    assert client_for(staff_member).post(action_url(customer, "deactivate")).status_code == 403


def test_cannot_deactivate_yourself(client_for, staff_admin):
    response = client_for(staff_admin).post(action_url(staff_admin, "deactivate"))
    assert response.status_code == 400
    staff_admin.refresh_from_db()
    assert staff_admin.is_active is True


def test_cannot_deactivate_superuser(client_for, staff_admin, superuser):
    assert client_for(staff_admin).post(action_url(superuser, "deactivate")).status_code == 404


# --- Emails triggered by an administrator ----------------------------------

def test_administrator_sends_password_reset(client_for, staff_admin, customer, mailoutbox):
    response = client_for(staff_admin).post(action_url(customer, "send-password-reset"))
    assert response.status_code == 200
    assert mailoutbox[0].to == [customer.email]


def test_administrator_resend_verification_refused_if_verified(client_for, staff_admin, make_user, mailoutbox):
    user = make_user(email_verified_at=timezone.now())
    response = client_for(staff_admin).post(action_url(user, "resend-verification"))
    assert response.status_code == 400
    assert len(mailoutbox) == 0


# --- Inviting staff ---------------------------------------------------------

INVITE_URL = f"{USERS_URL}invite-staff/"


def invite_payload(**overrides):
    data = {"email": "novi@example.com", "first_name": "Novi", "last_name": "Radnik", "groups": ["Osoblje"]}
    data.update(overrides)
    return data


def test_invite_creates_staff_and_emails_set_password_link(
    api_client, client_for, staff_admin, mailoutbox, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        response = client_for(staff_admin).post(INVITE_URL, invite_payload(), format="json")

    assert response.status_code == 201
    invited = User.objects.get(email="novi@example.com")
    assert invited.is_staff is True
    assert invited.is_superuser is False
    assert invited.has_usable_password() is False
    assert list(invited.groups.values_list("name", flat=True)) == ["Osoblje"]

    # The invite link works with the normal password reset confirmation endpoint.
    uid, token = uid_and_token(mailoutbox[0])
    response = api_client.post(
        "/api/auth/password-reset/confirm/",
        {"uid": uid, "token": token, "password": "Moja-Nova-Lozinka-1"},
        format="json",
    )
    assert response.status_code == 200
    login = api_client.post(
        "/api/auth/login/", {"email": "novi@example.com", "password": "Moja-Nova-Lozinka-1"}, format="json"
    )
    assert login.status_code == 200


def test_staff_cannot_invite(client_for, staff_member):
    response = client_for(staff_member).post(INVITE_URL, invite_payload(), format="json")
    assert response.status_code == 403
    assert not User.objects.filter(email="novi@example.com").exists()


def test_invite_rejects_unassignable_group(client_for, staff_admin):
    response = client_for(staff_admin).post(INVITE_URL, invite_payload(groups=["Superadmin"]), format="json")
    assert response.status_code == 400


def test_invite_rejects_existing_email(client_for, staff_admin, customer):
    response = client_for(staff_admin).post(INVITE_URL, invite_payload(email="KUPAC@example.com"), format="json")
    assert response.status_code == 400


# --- Changing groups --------------------------------------------------------

def test_administrator_promotes_staff_and_forces_relogin(client_for, staff_admin, staff_member):
    staff_session = client_for(staff_member)
    response = client_for(staff_admin).post(
        action_url(staff_member, "set-groups"), {"groups": ["Administrator"]}, format="json"
    )

    assert response.status_code == 200
    assert response.data["groups"] == ["Administrator"]   # replaced, not added
    assert refresh_works(staff_session.refresh_token) is False


def test_cannot_change_own_groups(client_for, staff_admin):
    response = client_for(staff_admin).post(
        action_url(staff_admin, "set-groups"), {"groups": ["Osoblje"]}, format="json"
    )
    assert response.status_code == 400


def test_set_groups_only_for_staff(client_for, staff_admin, customer):
    response = client_for(staff_admin).post(
        action_url(customer, "set-groups"), {"groups": ["Osoblje"]}, format="json"
    )
    assert response.status_code == 400
    assert customer.groups.count() == 0


def test_staff_cannot_set_groups(client_for, staff_member, staff_admin):
    response = client_for(staff_member).post(
        action_url(staff_admin, "set-groups"), {"groups": ["Osoblje"]}, format="json"
    )
    assert response.status_code == 403
