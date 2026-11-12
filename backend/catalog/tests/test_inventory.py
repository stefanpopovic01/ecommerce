"""
Inventory service tests: the rules of each stock operation.
Concurrency (several requests at the same moment) is tested in test_inventory_concurrency.py.
"""
import pytest
from django.db import IntegrityError, transaction
from django.db.models import Sum

from catalog.inventory import (
    InsufficientStock,
    InventoryError,
    adjust_stock,
    commit_sale,
    receive_stock,
    release_stock,
    reserve_stock,
)
from catalog.models import Inventory, StockMovement
from catalog.tests.conftest import inventory_of

pytestmark = pytest.mark.django_db


def movements(variant, reason=None):
    qs = StockMovement.objects.filter(variant=variant)
    if reason:
        qs = qs.filter(reason=reason)
    return qs


# --- receive_stock ----------------------------------------------------------

def test_receive_adds_to_shelf_and_logs(make_variant, customer):
    variant = make_variant(stock=10)
    receive_stock(variant, 5, user=customer, note="Isporuka 12")

    assert inventory_of(variant) == (15, 0)
    move = movements(variant).first()  # newest first
    assert move.reason == StockMovement.Reason.RECEIVED
    assert (move.quantity_change, move.reserved_change) == (5, 0)
    assert (move.quantity_after, move.reserved_after) == (15, 0)
    assert move.created_by == customer
    assert move.note == "Isporuka 12"


@pytest.mark.parametrize("bad", [0, -3])
def test_receive_rejects_non_positive(make_variant, bad):
    variant = make_variant(stock=10)
    with pytest.raises(ValueError):
        receive_stock(variant, bad)
    assert inventory_of(variant) == (10, 0)
    assert movements(variant).count() == 1  # only the initial receipt


# --- adjust_stock -----------------------------------------------------------

def test_adjust_down_logs_negative_difference(make_variant):
    variant = make_variant(stock=20)
    adjust_stock(variant, 15, note="Popis")

    assert inventory_of(variant) == (15, 0)
    move = movements(variant, StockMovement.Reason.CORRECTION).get()
    assert move.quantity_change == -5          # the change, not the new total
    assert move.quantity_after == 15


def test_adjust_up_logs_positive_difference(make_variant):
    variant = make_variant(stock=10)
    adjust_stock(variant, 12)
    assert movements(variant, StockMovement.Reason.CORRECTION).get().quantity_change == 2


def test_adjust_to_zero_with_nothing_reserved(make_variant):
    """Marking an item sold out must always work."""
    variant = make_variant(stock=3)
    adjust_stock(variant, 0)
    assert inventory_of(variant) == (0, 0)


def test_adjust_down_to_exactly_reserved_is_allowed(make_variant):
    variant = make_variant(stock=10)
    reserve_stock({variant.id: 4})
    adjust_stock(variant, 4)
    assert inventory_of(variant) == (4, 4)


def test_adjust_below_reserved_is_refused(make_variant):
    variant = make_variant(stock=10)
    reserve_stock({variant.id: 4})

    with pytest.raises(InsufficientStock):
        adjust_stock(variant, 3)
    assert inventory_of(variant) == (10, 4)
    assert not movements(variant, StockMovement.Reason.CORRECTION).exists()


def test_adjust_same_value_logs_nothing(make_variant):
    variant = make_variant(stock=10)
    adjust_stock(variant, 10)
    assert not movements(variant, StockMovement.Reason.CORRECTION).exists()


def test_adjust_negative_is_refused(make_variant):
    variant = make_variant(stock=10)
    with pytest.raises(ValueError):
        adjust_stock(variant, -1)


# --- reserve_stock ----------------------------------------------------------

def test_reserve_whole_cart(make_variant):
    shirt, pants = make_variant(stock=10), make_variant(stock=3)
    reserve_stock({shirt.id: 2, pants.id: 1})

    assert inventory_of(shirt) == (10, 2)
    assert inventory_of(pants) == (3, 1)
    move = movements(shirt, StockMovement.Reason.RESERVATION).get()
    assert (move.quantity_change, move.reserved_change) == (0, 2)
    assert (move.quantity_after, move.reserved_after) == (10, 2)


def test_reserve_exactly_what_is_available(make_variant):
    variant = make_variant(stock=5)
    reserve_stock({variant.id: 3})
    reserve_stock({variant.id: 2})
    assert inventory_of(variant) == (5, 5)


def test_reserve_more_than_available_is_refused(make_variant):
    variant = make_variant(stock=5)
    reserve_stock({variant.id: 3})

    with pytest.raises(InsufficientStock):
        reserve_stock({variant.id: 3})  # only 2 left
    assert inventory_of(variant) == (5, 3)


def test_reserve_is_all_or_nothing(make_variant):
    """If one item in the cart is short, nothing in the cart is reserved."""
    shirt, pants = make_variant(stock=10), make_variant(stock=1)

    with pytest.raises(InsufficientStock):
        reserve_stock({shirt.id: 2, pants.id: 5})
    assert inventory_of(shirt) == (10, 0)
    assert inventory_of(pants) == (1, 0)
    assert not StockMovement.objects.filter(reason=StockMovement.Reason.RESERVATION).exists()


def test_reserve_variant_without_inventory_row(make_variant):
    variant = make_variant(stock=5)
    Inventory.objects.filter(variant=variant).delete()
    with pytest.raises(InsufficientStock):
        reserve_stock({variant.id: 1})


@pytest.mark.parametrize("bad", [0, -1])
def test_reserve_rejects_non_positive(make_variant, bad):
    variant = make_variant(stock=5)
    with pytest.raises(ValueError):
        reserve_stock({variant.id: bad})
    assert inventory_of(variant) == (5, 0)


# --- release_stock ----------------------------------------------------------

def test_release_returns_reserved_units(make_variant):
    variant = make_variant(stock=10)
    reserve_stock({variant.id: 3})
    release_stock({variant.id: 3})

    assert inventory_of(variant) == (10, 0)
    move = movements(variant, StockMovement.Reason.RELEASE).get()
    assert (move.quantity_change, move.reserved_change) == (0, -3)
    assert move.reserved_after == 0


def test_release_more_than_reserved_is_a_bug(make_variant):
    variant = make_variant(stock=10)
    reserve_stock({variant.id: 1})

    with pytest.raises(InventoryError):
        release_stock({variant.id: 2})
    assert inventory_of(variant) == (10, 1)


def test_release_twice_is_caught(make_variant):
    """Releasing the same reservation twice (e.g. expiry job + failed payment) must not go unnoticed."""
    variant = make_variant(stock=10)
    reserve_stock({variant.id: 2})
    release_stock({variant.id: 2})
    with pytest.raises(InventoryError):
        release_stock({variant.id: 2})


# --- commit_sale ------------------------------------------------------------

def test_sale_removes_units_from_shelf_and_reservation(make_variant):
    variant = make_variant(stock=10)
    reserve_stock({variant.id: 2})
    commit_sale({variant.id: 2})

    assert inventory_of(variant) == (8, 0)
    move = movements(variant, StockMovement.Reason.SALE).get()
    assert (move.quantity_change, move.reserved_change) == (-2, -2)
    assert (move.quantity_after, move.reserved_after) == (8, 0)


def test_sale_without_reservation_is_a_bug(make_variant):
    variant = make_variant(stock=10)
    with pytest.raises(InventoryError):
        commit_sale({variant.id: 1})
    assert inventory_of(variant) == (10, 0)


def test_sale_of_last_unit(make_variant):
    variant = make_variant(stock=1)
    reserve_stock({variant.id: 1})
    commit_sale({variant.id: 1})
    assert inventory_of(variant) == (0, 0)


@pytest.mark.parametrize("bad", [0, -2])
def test_sale_rejects_non_positive(make_variant, bad):
    variant = make_variant(stock=10)
    reserve_stock({variant.id: 2})
    with pytest.raises(ValueError):
        commit_sale({variant.id: bad})
    assert inventory_of(variant) == (10, 2)


# --- History always matches the current numbers ---------------------------

def test_history_adds_up_to_current_numbers(make_variant):
    """
    Summing every change in the log must give exactly the current inventory.
    If a function ever logged the wrong sign or amount, this breaks.
    """
    variant = make_variant(stock=20)
    reserve_stock({variant.id: 5})
    commit_sale({variant.id: 3})
    release_stock({variant.id: 2})
    adjust_stock(variant, 15)
    receive_stock(variant, 4)
    reserve_stock({variant.id: 1})

    totals = movements(variant).aggregate(q=Sum("quantity_change"), r=Sum("reserved_change"))
    assert (totals["q"], totals["r"]) == inventory_of(variant)

    latest = movements(variant).first()
    assert (latest.quantity_after, latest.reserved_after) == inventory_of(variant)


# --- Database constraints (the last line of defense) ----------------------

def test_db_refuses_reserved_above_quantity(make_variant):
    variant = make_variant(stock=2)
    with pytest.raises(IntegrityError), transaction.atomic():
        Inventory.objects.filter(variant=variant).update(reserved_quantity=3)


def test_db_refuses_negative_quantity(make_variant):
    variant = make_variant(stock=2)
    with pytest.raises(IntegrityError), transaction.atomic():
        Inventory.objects.filter(variant=variant).update(quantity=-1)


def test_variant_with_history_cannot_be_deleted(make_variant):
    from django.db.models import ProtectedError
    variant = make_variant(stock=2)
    with pytest.raises(ProtectedError):
        variant.delete()
