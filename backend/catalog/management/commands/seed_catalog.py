"""
Fill the database with a realistic test catalog.

    python manage.py seed_catalog           # seed (does nothing if already seeded)
    python manage.py seed_catalog --reset   # delete the catalog first, then seed

Development only: --reset refuses to run when DEBUG is False.
"""
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from catalog.models import Category, Product, ProductImage, StockMovement
from catalog.services import create_product

ACTIVE = Product.Status.ACTIVE
DRAFT = Product.Status.DRAFT

# Top-level category -> its subcategories, as (name, slug).
CATEGORIES = {
    ("Muškarci", "muskarci"): [
        ("Majice", "muske-majice"),
        ("Duksevi", "muski-duksevi"),
        ("Patike", "muske-patike"),
    ],
    ("Žene", "zene"): [
        ("Majice", "zenske-majice"),
        ("Haljine", "haljine"),
        ("Patike", "zenske-patike"),
    ],
    ("Aksesoari", "aksesoari"): [
        ("Kape", "kape"),
        ("Torbe", "torbe"),
    ],
}


def sizes(prefix, price, stock_by_size, color=None, compare_at_price=None):
    """Build one variant per size. stock_by_size = {"S": 5, "M": 0, ...}"""
    variants = []
    for size, stock in stock_by_size.items():
        attrs = {"size": size}
        sku = f"{prefix}-{size}"
        if color:
            attrs["color"] = color
            sku = f"{prefix}-{color[:3].upper()}-{size}"
        variants.append({
            "sku": sku,
            "price": Decimal(price),
            "compare_at_price": Decimal(compare_at_price) if compare_at_price else None,
            "attributes": attrs,
            "stock": stock,
        })
    return variants


def products(cat):
    """The test products. `cat` maps category slug -> Category."""
    return [
        # Several sizes × two colors
        dict(
            name="Basic pamučna majica",
            slug="basic-pamucna-majica",
            category=cat["muske-majice"],
            status=ACTIVE,
            description="Udobna majica od 100% pamuka, klasičan kroj.",
            attributes={"material": "100% pamuk"},
            variants=sizes("BPM", "1990.00", {"S": 8, "M": 12, "L": 6}, color="crna")
                     + sizes("BPM", "1990.00", {"S": 5, "M": 0, "L": 3}, color="bela"),
        ),
        # On sale
        dict(
            name="Oversized grafička majica",
            slug="oversized-graficka-majica",
            category=cat["muske-majice"],
            status=ACTIVE,
            description="Široki kroj sa štampom na leđima.",
            attributes={"material": "pamuk/poliester"},
            variants=sizes("OGM", "1790.00", {"M": 10, "L": 10, "XL": 4}, compare_at_price="2490.00"),
        ),
        # Low stock (below the threshold of 5)
        dict(
            name="Duks sa kapuljačom",
            slug="duks-sa-kapuljacom",
            category=cat["muski-duksevi"],
            status=ACTIVE,
            attributes={"material": "80% pamuk, 20% poliester"},
            variants=sizes("DSK", "4490.00", {"M": 2, "L": 3}),
        ),
        # Out of stock everywhere
        dict(
            name="Patike za trčanje Runner",
            slug="patike-za-trcanje-runner",
            category=cat["muske-patike"],
            status=ACTIVE,
            variants=sizes("RUN", "8990.00", {"42": 0, "43": 0, "44": 0}),
        ),
        dict(
            name="Ženska majica sa V izrezom",
            slug="zenska-majica-v-izrez",
            category=cat["zenske-majice"],
            status=ACTIVE,
            variants=sizes("ZMV", "1690.00", {"XS": 4, "S": 9, "M": 7}),
        ),
        # Different prices per variant
        dict(
            name="Letnja haljina na cvetove",
            slug="letnja-haljina-cvetovi",
            category=cat["haljine"],
            status=ACTIVE,
            description="Lagana haljina za leto.",
            variants=[
                {"sku": "LHC-S", "price": Decimal("3990.00"), "attributes": {"size": "S"}, "stock": 6},
                {"sku": "LHC-M", "price": Decimal("3990.00"), "attributes": {"size": "M"}, "stock": 4},
                {"sku": "LHC-XL", "price": Decimal("4290.00"), "attributes": {"size": "XL"}, "stock": 2},
            ],
        ),
        dict(
            name="Ženske platnene patike",
            slug="zenske-platnene-patike",
            category=cat["zenske-patike"],
            status=ACTIVE,
            variants=sizes("ZPP", "5490.00", {"37": 3, "38": 5, "39": 5, "40": 1}),
        ),
        # Simple product: one variant, no options
        dict(
            name="Platnena torba",
            slug="platnena-torba",
            category=cat["torbe"],
            status=ACTIVE,
            variants=[{"sku": "TORBA-01", "price": Decimal("1290.00"), "stock": 25}],
        ),
        # No category
        dict(
            name="Poklon vaučer 5000",
            slug="poklon-vaucer-5000",
            category=None,
            status=ACTIVE,
            variants=[{"sku": "VAUCER-5000", "price": Decimal("5000.00"), "stock": 100}],
        ),
        # Draft: must never appear in the shop
        dict(
            name="Zimska kapa (uskoro)",
            slug="zimska-kapa",
            category=cat["kape"],
            status=DRAFT,
            variants=[{"sku": "KAPA-ZIM", "price": Decimal("1490.00"), "stock": 0}],
        ),
    ]


class Command(BaseCommand):
    help = "Fill the database with a realistic test catalog."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete the existing catalog first.")

    def handle(self, *args, **options):
        if options["reset"]:
            if not settings.DEBUG:
                raise CommandError("Refusing to delete the catalog with DEBUG=False (production?).")
            self.reset()

        if Product.objects.filter(slug="basic-pamucna-majica").exists():
            self.stdout.write(self.style.WARNING("Catalog already seeded. Use --reset to start over."))
            return

        with transaction.atomic():
            categories = self.create_categories()
            for data in products(categories):
                create_product(**data)

        self.stdout.write(self.style.SUCCESS(
            f"Seeded {Category.objects.count()} categories and {Product.objects.count()} products."
        ))

    def reset(self):
        with transaction.atomic():
            # Order matters: stock movements PROTECT variants, and categories PROTECT their children.
            StockMovement.objects.all().delete()
            ProductImage.objects.all().delete()
            Product.objects.all().delete()  # cascades to variants and inventory
            Category.objects.filter(parent__isnull=False).delete()
            Category.objects.all().delete()
        self.stdout.write("Deleted existing catalog.")

    def create_categories(self):
        by_slug = {}
        for sort, ((name, slug), children) in enumerate(CATEGORIES.items()):
            parent = Category.objects.create(name=name, slug=slug, sort_order=sort * 10)
            by_slug[slug] = parent
            for child_sort, (child_name, child_slug) in enumerate(children):
                by_slug[child_slug] = Category.objects.create(
                    name=child_name, slug=child_slug, parent=parent, sort_order=child_sort * 10,
                )
        return by_slug
