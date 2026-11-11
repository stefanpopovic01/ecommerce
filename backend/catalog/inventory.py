from django.db import transaction

from .models import Inventory, StockMovement



class InsufficientStock(Exception):
    """Raised when there isn't enough available stock for an operation."""



@transaction.atomic
def receive_stock(variant, quantity, user=None, note=""):
    """A delivery arrived: add `quantity` units to the shelf."""
    if quantity <= 0:
        raise ValueError("Received quantity must be positive.")

    inv = Inventory.objects.select_for_update().get(variant=variant)
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