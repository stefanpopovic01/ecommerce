from django.db import transaction

from .models import Inventory, StockMovement



class InsufficientStock(Exception):
    """Raised when there isn't enough available stock for an operation."""


class InventoryError(Exception):
    """Inconsistent stock operation; indicates a bug, not a normal business outcome."""



@transaction.atomic
def receive_stock(variant, quantity, user=None, note=""):
    """A delivery arrived: add `quantity` units to the shelf."""
    if quantity <= 0:
        raise ValueError("Received quantity must be positive.")

    inv = Inventory.objects.select_for_update().get(variant=variant) # select_for_update() locks the database row
    inv.quantity += quantity
    inv.save(update_fields=["quantity", "updated_at"])

    StockMovement.objects.create(
        variant=variant,
        quantity_change=quantity,
        reserved_change=0,
        quantity_after=inv.quantity,
        reserved_after=inv.reserved_quantity,
        reason=StockMovement.Reason.RECEIVED,
        created_by=user,
        note=note,
    )
    return inv



@transaction.atomic
def adjust_stock(variant, new_quantity, user=None, note=""):
    """Stock count correction: set the shelf quantity to what was actually counted."""
    if new_quantity < 0:
        raise ValueError("Quantity cannot be negative.")

    inv = Inventory.objects.select_for_update().get(variant=variant)

    if new_quantity == inv.quantity:
        return inv
    if new_quantity < inv.reserved_quantity:
        raise InsufficientStock(
            f"Cannot set quantity to {new_quantity}: {inv.reserved_quantity} units are reserved."
        )

    old_quantity = inv.quantity
    inv.quantity = new_quantity
    inv.save(update_fields=["quantity", "updated_at"])

    StockMovement.objects.create(
        variant=variant,
        quantity_change=new_quantity - old_quantity,
        reserved_change=0,
        quantity_after=inv.quantity,
        reserved_after=inv.reserved_quantity,
        reason=StockMovement.Reason.CORRECTION,
        created_by=user,
        note=note,
    )
    return inv



@transaction.atomic
def reserve_stock(items, user=None, note=""):

    """Reserve stock for a whole cart. items = {variant_id: quantity}"""

    for quantity in items.values():
        if quantity <= 0:
            raise ValueError("Reserved quantity must be positive.")

    # Lock every row at once, always in the same order, to prevent deadlocks.
    inventories = list(
        Inventory.objects.select_for_update()
        .filter(variant_id__in=items.keys())
        .order_by("variant_id")
    )
    if len(inventories) != len(items):
        raise InsufficientStock("One or more items are not available.")

    by_variant = {inv.variant_id: inv for inv in inventories} # {5: <Inventory: 5>, 9: <Inventory: 9>}

    for variant_id, quantity in items.items():
        inv = by_variant[variant_id]
        available = inv.quantity - inv.reserved_quantity
        if available < quantity:
            raise InsufficientStock(
                f"Only {available} available for variant {variant_id}, requested {quantity}."
            )
        
    for variant_id, quantity in items.items():
        inv = by_variant[variant_id]
        inv.reserved_quantity += quantity
        inv.save(update_fields=["reserved_quantity", "updated_at"])

        StockMovement.objects.create(
            variant_id=variant_id,
            quantity_change=0,
            reserved_change=quantity,
            quantity_after=inv.quantity,
            reserved_after=inv.reserved_quantity,
            reason=StockMovement.Reason.RESERVATION,
            created_by=user,
            note=note,
        )



@transaction.atomic
def release_stock(items, user=None, note=""):

    """Release stock for a whole cart. items = {variant_id: quantity}"""

    for quantity in items.values():
        if quantity <= 0:
            raise ValueError("Quantity to release must be positive.")

    inventories = list(
        Inventory.objects.select_for_update()
        .filter(variant_id__in=items.keys())
        .order_by("variant_id")
    )
    if len(inventories) != len(items):
        raise InventoryError("Inventory row missing for one or more variants.")

    by_variant = {inv.variant_id: inv for inv in inventories} # {5: <Inventory: 5>, 9: <Inventory: 9>}

    for variant_id, quantity in items.items():
        inv = by_variant[variant_id]

        if inv.reserved_quantity < quantity:
            raise InventoryError(
                f"Cannot release {quantity} of variant {variant_id}: only {inv.reserved_quantity} reserved."
            )
        
    for variant_id, quantity in items.items():
        inv = by_variant[variant_id]
        inv.reserved_quantity -= quantity
        inv.save(update_fields=["reserved_quantity", "updated_at"])

        StockMovement.objects.create(
            variant_id=variant_id,
            quantity_change=0,
            reserved_change=-quantity,
            quantity_after=inv.quantity,
            reserved_after=inv.reserved_quantity,
            reason=StockMovement.Reason.RELEASE,
            created_by=user,
            note=note,
        )



@transaction.atomic
def commit_sale(items, user=None, note=""):

    """Payment succeeded: reserved units leave the shelf. items = {variant_id: quantity}"""

    for quantity in items.values():
        if quantity <= 0:
            raise ValueError("Quantity must be positive.")

    inventories = list(
        Inventory.objects.select_for_update()
        .filter(variant_id__in=items.keys())
        .order_by("variant_id")
    )
    if len(inventories) != len(items):
        raise InventoryError("Inventory row missing for one or more variants.")

    by_variant = {inv.variant_id: inv for inv in inventories}

    for variant_id, quantity in items.items():
        inv = by_variant[variant_id]

        if inv.reserved_quantity < quantity:
            raise InventoryError(
                f"Cannot sell {quantity} of variant {variant_id}: only {inv.reserved_quantity} reserved."
            )

    for variant_id, quantity in items.items():
        inv = by_variant[variant_id]
        inv.reserved_quantity -= quantity
        inv.quantity -= quantity
        inv.save(update_fields=["reserved_quantity", "quantity", "updated_at"])

        StockMovement.objects.create(
            variant_id=variant_id,
            quantity_change=-quantity,
            reserved_change=-quantity,
            quantity_after=inv.quantity,
            reserved_after=inv.reserved_quantity,
            reason=StockMovement.Reason.SALE,
            created_by=user,
            note=note,
        )