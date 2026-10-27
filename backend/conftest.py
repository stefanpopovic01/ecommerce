"""
Shared fixtures for all tests in the project.

pytest finds this file automatically. Anything defined here with @pytest.fixture
can be used by any test just by naming it as a function argument.
"""
import pytest
from django.contrib.auth.models import Group, Permission
from django.core.cache import cache
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import User

PASSWORD = "Sigurna-Lozinka-2026!"


@pytest.fixture(autouse=True)
def clear_cache():
    """Throttle counters live in the cache. Clear it so tests don't hit 429s from earlier tests."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def api_client():
    """A client with no credentials, i.e. an anonymous visitor."""
    return APIClient()


@pytest.fixture
def make_user(db):
    """Factory: call make_user(email=..., password=..., **fields) to create users inside a test."""
    def _make(email="kupac@example.com", password=PASSWORD, **extra):
        extra.setdefault("first_name", "Marko")
        extra.setdefault("last_name", "Petrović")
        return User.objects.create_user(email=email, password=password, **extra)
    return _make


@pytest.fixture
def customer(make_user):
    return make_user()


@pytest.fixture
def client_for():
    """
    Factory: client_for(user) returns an APIClient logged in as that user with a real JWT.
    The matching refresh token is stored as client.refresh_token, so tests can check
    whether it still works after logout, password change, deactivation, etc.
    """
    def _client(user):
        refresh = RefreshToken.for_user(user)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {refresh.access_token}")
        client.refresh_token = str(refresh)
        return client
    return _client


def _accounts_perms(*codenames):
    return Permission.objects.filter(content_type__app_label="accounts", codename__in=codenames)


@pytest.fixture
def staff_groups(db):
    osoblje = Group.objects.create(name="Osoblje")
    osoblje.permissions.set(_accounts_perms("view_user"))
    administrator = Group.objects.create(name="Administrator")
    administrator.permissions.set(_accounts_perms("view_user", "add_user", "change_user"))
    return {"Osoblje": osoblje, "Administrator": administrator}


@pytest.fixture
def staff_member(make_user, staff_groups):
    user = make_user(email="osoblje@example.com", is_staff=True)
    user.groups.add(staff_groups["Osoblje"])
    return user


@pytest.fixture
def staff_admin(make_user, staff_groups):
    user = make_user(email="administrator@example.com", is_staff=True)
    user.groups.add(staff_groups["Administrator"])
    return user


@pytest.fixture
def superuser(db):
    return User.objects.create_superuser(
        email="dev@example.com", password=PASSWORD, first_name="Dev", last_name="Admin"
    )
