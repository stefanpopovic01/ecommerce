from django.db import transaction
from .models import Product, ProductVariant, Inventory
from .inventory import receive_stock



@transaction.atomic
def create_product(*, name, slug, variants, category=None, description="",
                   status=Product.Status.DRAFT, attributes=None, user=None):
    """Create a product with its variants, an inventory row for each, and initial stock."""
    if not variants:
        raise ValueError("A product needs at least one variant.")

    skus = [v["sku"] for v in variants]
    if len(skus) != len(set(skus)):
        raise ValueError("Duplicate SKU in variants.")

    product = Product.objects.create(
        category=category, name=name, slug=slug, description=description,
        status=status, attributes=attributes or {},
    )

    for v in variants:
        variant = ProductVariant.objects.create(
            product=product,
            sku=v["sku"],
            price=v["price"],
            compare_at_price=v.get("compare_at_price"),
            attributes=v.get("attributes", {}),
            weight_grams=v.get("weight_grams"),
            is_active=v.get("is_active", True),
        )
        Inventory.objects.create(variant=variant)

        stock = v.get("stock", 0)
        if stock > 0:
            receive_stock(variant, stock, user=user, note="Initial stock")

    return product