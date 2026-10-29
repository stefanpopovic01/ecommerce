"""
Address book tests.

If your URL is different (e.g. /api/auth/me/addresses/), change ADDRESSES_URL below.
"""
import pytest

from accounts.models import Address

pytestmark = pytest.mark.django_db

ADDRESSES_URL = "/api/auth/addresses/"


def detail_url(address_id):
    return f"{ADDRESSES_URL}{address_id}/"


def address_payload(**overrides):
    data = {
        "label": "Kuća",
        "full_name": "Marko Petrović",
        "line1": "Kosovska 12",
        "city": "Kruševac",
        "postal_code": "37000",
        "country": "RS",
        "phone": "+381641234567",
    }
    data.update(overrides)
    return data


@pytest.fixture
def client(client_for, customer):
    return client_for(customer)


def create(client, **overrides):
    response = client.post(ADDRESSES_URL, address_payload(**overrides), format="json")
    assert response.status_code == 201, response.data
    return response.data["id"]


def defaults_of(user):
    """Return (shipping_ids, billing_ids) of the user's default addresses, as strings."""
    shipping = {str(pk) for pk in Address.objects.filter(user=user, is_default_shipping=True).values_list("pk", flat=True)}
    billing = {str(pk) for pk in Address.objects.filter(user=user, is_default_billing=True).values_list("pk", flat=True)}
    return shipping, billing


# --- Access ---------------------------------------------------------------

def test_requires_login(api_client):
    assert api_client.get(ADDRESSES_URL).status_code == 401


def test_user_never_sees_other_users_addresses(client_for, customer, make_user):
    other = make_user(email="drugi@example.com")
    other_id = create(client_for(other))

    client = client_for(customer)
    assert client.get(ADDRESSES_URL).data["count"] == 0
    assert client.get(detail_url(other_id)).status_code == 404
    assert client.patch(detail_url(other_id), {"city": "Hakovano"}, format="json").status_code == 404
    assert client.delete(detail_url(other_id)).status_code == 404
    assert Address.objects.get(pk=other_id).city == "Kruševac"


def test_address_is_saved_on_caller_even_if_user_field_is_sent(client, customer, make_user):
    other = make_user(email="drugi@example.com")
    address_id = create(client, user=str(other.pk))
    assert Address.objects.get(pk=address_id).user == customer


def test_put_is_not_allowed(client):
    address_id = create(client)
    assert client.put(detail_url(address_id), address_payload(), format="json").status_code == 405


# --- Create / edit / delete -------------------------------------------------

def test_create_and_read_back(client):
    address_id = create(client, line2="Stan 7")
    response = client.get(detail_url(address_id))

    assert response.status_code == 200
    assert response.data["line1"] == "Kosovska 12"
    assert response.data["line2"] == "Stan 7"
    assert response.data["country"] == "RS"
    assert "user" not in response.data


def test_invalid_country_is_rejected(client):
    response = client.post(ADDRESSES_URL, address_payload(country="XX"), format="json")
    assert response.status_code == 400
    assert "country" in response.data


def test_required_fields(client):
    response = client.post(ADDRESSES_URL, {"label": "Kuća"}, format="json")
    assert response.status_code == 400
    for field in ("full_name", "line1", "city", "postal_code"):
        assert field in response.data


def test_edit_address(client):
    address_id = create(client)
    response = client.patch(detail_url(address_id), {"city": "Beograd"}, format="json")

    assert response.status_code == 200
    assert Address.objects.get(pk=address_id).city == "Beograd"


def test_delete_address(client):
    address_id = create(client)
    assert client.delete(detail_url(address_id)).status_code == 204
    assert not Address.objects.filter(pk=address_id).exists()


def test_limit_of_ten_addresses(client):
    for i in range(10):
        create(client, label=f"Adresa {i}")
    response = client.post(ADDRESSES_URL, address_payload(), format="json")

    assert response.status_code == 400
    assert Address.objects.count() == 10


def test_editing_still_works_at_the_limit(client):
    ids = [create(client, label=f"Adresa {i}") for i in range(10)]
    response = client.patch(detail_url(ids[0]), {"city": "Niš"}, format="json")
    assert response.status_code == 200


# --- Defaults ---------------------------------------------------------------

def test_first_address_becomes_both_defaults(client, customer):
    address_id = create(client)
    assert defaults_of(customer) == ({address_id}, {address_id})


def test_first_address_is_default_even_if_client_sends_false(client, customer):
    address_id = create(client, is_default_shipping=False, is_default_billing=False)
    assert defaults_of(customer) == ({address_id}, {address_id})


def test_second_address_is_not_default_by_default(client, customer):
    first = create(client)
    create(client, label="Posao")
    assert defaults_of(customer) == ({first}, {first})


def test_create_new_default_shipping_moves_flag(client, customer):
    first = create(client)
    second = create(client, label="Posao", is_default_shipping=True)

    shipping, billing = defaults_of(customer)
    assert shipping == {second}
    assert billing == {first}          # billing untouched


def test_patch_sets_default_and_unsets_old_one(client, customer):
    first = create(client)
    second = create(client, label="Posao")

    response = client.patch(detail_url(second), {"is_default_billing": True}, format="json")

    assert response.status_code == 200
    shipping, billing = defaults_of(customer)
    assert shipping == {first}
    assert billing == {second}


def test_patch_both_defaults_at_once(client, customer):
    create(client)
    second = create(client, label="Posao")

    client.patch(detail_url(second), {"is_default_shipping": True, "is_default_billing": True}, format="json")
    assert defaults_of(customer) == ({second}, {second})


def test_patch_default_works_with_form_data(client, customer):
    """Form data sends "true" as a string; validated_data turns it into a real boolean."""
    create(client)
    second = create(client, label="Posao")

    response = client.patch(detail_url(second), {"is_default_shipping": "true"})  # multipart, not JSON

    assert response.status_code == 200
    assert defaults_of(customer)[0] == {second}


def test_setting_already_default_address_as_default_keeps_it(client, customer):
    first = create(client)
    response = client.patch(detail_url(first), {"is_default_shipping": True}, format="json")

    assert response.status_code == 200
    assert defaults_of(customer)[0] == {first}


def test_unsetting_default_leaves_no_default(client, customer):
    first = create(client)
    client.patch(detail_url(first), {"is_default_shipping": False}, format="json")
    assert defaults_of(customer)[0] == set()


def test_editing_other_fields_does_not_touch_defaults(client, customer):
    first = create(client)
    second = create(client, label="Posao")
    client.patch(detail_url(second), {"city": "Novi Sad"}, format="json")
    assert defaults_of(customer) == ({first}, {first})


def test_defaults_are_per_user(client_for, customer, make_user):
    other = make_user(email="drugi@example.com")
    mine = create(client_for(customer))
    theirs = create(client_for(other))

    # each user has their own default; setting one never affects the other user
    create(client_for(customer), label="Posao", is_default_shipping=True)
    assert defaults_of(other) == ({theirs}, {theirs})
    assert mine not in defaults_of(customer)[0]


# --- Account deletion -------------------------------------------------------

def test_addresses_deleted_with_account(client, customer):
    from conftest import PASSWORD
    create(client)
    client.delete("/api/auth/me/", {"password": PASSWORD}, format="json")
    assert not Address.objects.exists()
