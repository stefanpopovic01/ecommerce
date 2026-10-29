import uuid
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower
from django.core.exceptions import ValidationError

from cloudinary.models import CloudinaryField



class Category(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    parent = models.ForeignKey("self", on_delete=models.PROTECT, null=True, blank=True, related_name="children")
    name = models.CharField(max_length=128) 
    slug = models.SlugField(max_length=128, unique=True)
    description = models.TextField(blank=True)
    sort_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name_plural = "categories"        
        constraints = [
            models.UniqueConstraint(
                Lower("name"), "parent",
                name="unique_category_name_per_parent",
                nulls_distinct=False,
            ),
        ]

    def __str__(self):
        return self.name



class Product(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, blank=True, null=True, related_name="products")
    name = models.CharField(max_length=255) 
    slug = models.SlugField(max_length=128, unique=True)
    description = models.TextField(blank=True)

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        ARCHIVED = "archived", "Archived"

    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    attributes = models.JSONField(default=dict, blank=True)
    meta_title = models.CharField(max_length=128, blank=True)
    meta_description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "-created_at"], name="product_status_created_idx"),
        ]

    def __str__(self):
        return self.name



class ProductVariant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants")
    sku = models.CharField(max_length=255, unique=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    compare_at_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    attributes = models.JSONField(default=dict, blank=True)
    weight_grams = models.PositiveIntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(price__gte=0),
                name="variant_price_non_negative",
            ),
            models.CheckConstraint(
                condition=Q(compare_at_price__isnull=True) | Q(compare_at_price__gt=F("price")),
                name="variant_compare_at_price_gt_price",
            ),
        ]

    def __str__(self):
        return self.sku



class Inventory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    variant = models.OneToOneField(ProductVariant, on_delete=models.CASCADE, related_name="inventory")
    quantity = models.PositiveIntegerField(default=0)
    reserved_quantity = models.PositiveIntegerField(default=0)
    low_stock_threshold = models.PositiveIntegerField(default=5) # Only x left - low-stock alerts.
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name_plural = "inventory"
        constraints = [
            models.CheckConstraint(
                condition=Q(reserved_quantity__lte=F("quantity")),
                name="inventory_reserved_lte_quantity",
            ),
        ]

    def __str__(self):
        return f"{self.variant.sku}: {self.quantity}"



class ProductImage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="images")
    variant = models.ForeignKey(ProductVariant, on_delete=models.SET_NULL, null=True, blank=True, related_name="images")
    image = CloudinaryField("image", folder="products")
    alt_text = models.CharField(max_length=255, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "created_at"]

    def __str__(self):
        return f"{self.product.name} #{self.sort_order}"

    def clean(self):
        if self.variant_id and self.variant.product_id != self.product_id:
            raise ValidationError({"variant": "This variant belongs to a different product."})