"""
Concurrency tests: many checkouts hitting the same stock at the same moment.

These only mean something on PostgreSQL. SQLite ignores select_for_update(),
so run them against the same database engine you use in production.

How they work:
- Each test starts several threads. Django gives every thread its own database
  connection, so each thread is a separate "request" with its own transaction.
- A Barrier makes all threads wait until everyone is ready, then releases them
  at once, so they really do collide.
- transaction=True: normal tests wrap everything in one transaction that's rolled
  back at the end. Threads can't see data inside another connection's open
  transaction, so these tests commit for real and pytest-django empties the
  tables afterwards instead.
"""
import threading

import pytest
from django.db import connection

from catalog.inventory import InsufficientStock, reserve_stock
from catalog.models import StockMovement
from catalog.tests.conftest import inventory_of

pytestmark = pytest.mark.django_db(transaction=True)


def run_at_once(workers):
    """Run each callable in its own thread, all starting at the same moment.
    Returns (results, errors): what each worker returned, and unexpected exceptions."""
    barrier = threading.Barrier(len(workers))
    results, errors = [], []
    lock = threading.Lock()

    def wrapper(fn):
        try:
            barrier.wait(timeout=10)
            outcome = fn()
            with lock:
                results.append(outcome)
        except Exception as exc:  # anything unexpected, e.g. a deadlock error
            with lock:
                errors.append(exc)
        finally:
            connection.close()  # each thread closes its own DB connection

    threads = [threading.Thread(target=wrapper, args=(w,)) for w in workers]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    return results, errors


def try_reserve(items):
    """One customer's checkout: True if reserved, False if sold out."""
    def _attempt():
        try:
            reserve_stock(items)
            return True
        except InsufficientStock:
            return False
    return _attempt


def test_last_unit_is_sold_only_once(make_variant):
    """10 customers try to buy the last unit at the same moment. Exactly one gets it."""
    variant = make_variant(stock=1)

    results, errors = run_at_once([try_reserve({variant.id: 1}) for _ in range(10)])

    assert errors == []
    assert results.count(True) == 1
    assert results.count(False) == 9
    assert inventory_of(variant) == (1, 1)
    assert StockMovement.objects.filter(variant=variant, reason="reservation").count() == 1


def test_never_reserves_more_than_stock(make_variant):
    """20 customers, 5 units: exactly 5 succeed, never 6."""
    variant = make_variant(stock=5)

    results, errors = run_at_once([try_reserve({variant.id: 1}) for _ in range(20)])

    assert errors == []
    assert results.count(True) == 5
    assert inventory_of(variant) == (5, 5)


def test_opposite_cart_orders_do_not_deadlock(make_variant):
    """
    Half the customers have [shirt, pants] in their cart, half have [pants, shirt].
    If locks were taken in cart order, they would deadlock. Sorted locking prevents it.
    """
    shirt, pants = make_variant(stock=100), make_variant(stock=100)

    workers = []
    for i in range(20):
        cart = {shirt.id: 1, pants.id: 1} if i % 2 == 0 else {pants.id: 1, shirt.id: 1}
        workers.append(try_reserve(cart))

    results, errors = run_at_once(workers)

    assert errors == [], f"Unexpected errors (deadlock?): {errors}"
    assert results.count(True) == 20
    assert inventory_of(shirt) == (100, 20)
    assert inventory_of(pants) == (100, 20)
