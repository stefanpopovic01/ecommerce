from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from .models import Category, Inventory, Product, ProductImage, ProductVariant



@admin.register(Category)
class CategoryAdmin(ModelAdmin):
    list_display = ("name", "parent", "slug", "sort_order")
    list_select_related = ("parent",)
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


class ProductVariantInline(TabularInline):
    model = ProductVariant
    extra = 1
    fields = ("sku", "price", "compare_at_price", "attributes", "weight_grams", "is_active")


class ProductImageInline(TabularInline):
    model = ProductImage
    extra = 1
    fields = ("image", "variant", "alt_text", "sort_order")


@admin.register(Product)
class ProductAdmin(ModelAdmin):
    list_display = ("name", "category", "status", "created_at")
    list_filter = ("status", "category")
    list_select_related = ("category",)
    search_fields = ("name", "slug", "variants__sku")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [ProductVariantInline, ProductImageInline]


@admin.register(Inventory)
class InventoryAdmin(ModelAdmin):
    list_display = ("variant", "quantity", "reserved_quantity", "low_stock_threshold")
    list_select_related = ("variant",)
    search_fields = ("variant__sku",)