import uuid
from django.db import models
from django.db.models.functions import Lower



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