import itertools
from decimal import Decimal

import pytest

from catalog.inventory import receive_stock
from catalog.models import Inventory, Product, ProductVariant

_sku_counter = itertools.count(1)


@pytest.fixture
def make_variant(db):
    """
    Factory: make_variant(stock=10) creates a product, one variant and its inventory row.
    Initial stock goes through receive_stock, so the movement history starts correct.
    """
    def _make(stock=0, price="1990.00"):
        n = next(_sku_counter)
        product = Product.objects.create(name=f"Majica {n}", slug=f"majica-{n}")
        variant = ProductVariant.objects.create(product=product, sku=f"SKU-{n}", price=Decimal(price))
        Inventory.objects.create(variant=variant)
        if stock:
            receive_stock(variant, stock)
        return variant
    return _make


def inventory_of(variant):
    """Fresh inventory numbers from the database: (quantity, reserved_quantity)."""
    inv = Inventory.objects.get(variant=variant)
    return inv.quantity, inv.reserved_quantity
