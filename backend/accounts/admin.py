from django.contrib import admin
from django.contrib.auth.models import Group
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from unfold.admin import ModelAdmin, TabularInline
from unfold.forms import AdminOwnPasswordChangeForm

from .forms import CustomUserChangeForm, CustomUserCreationForm
from .models import OAuthAccount, User



admin.site.unregister(Group)



@admin.register(Group)
class GroupAdmin(BaseGroupAdmin, ModelAdmin):
    pass




class OAuthAccountInline(TabularInline):
    model = OAuthAccount
    extra = 0
    can_delete = False
    readonly_fields = ("provider", "provider_user_id", "email", "created_at")

    def has_add_permission(self, request, obj=None):
        return False



@admin.register(User)
class CustomUserAdmin(BaseUserAdmin, ModelAdmin):
    add_form = CustomUserCreationForm
    form = CustomUserChangeForm
    change_password_form = AdminOwnPasswordChangeForm
    model = User

    list_display = ("email", "first_name", "last_name", "is_active", "email_verified_at", "created_at")
    list_filter = ("is_active", "is_staff")
    search_fields = ("email", "first_name", "last_name", "phone")
    ordering = ("-created_at",)
    readonly_fields = ("last_login", "created_at", "updated_at")
    inlines = [OAuthAccountInline]

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal info", {"fields": ("first_name", "last_name", "phone")}),
        ("Status", {"fields": ("is_active", "email_verified_at")}),
        ("Permissions", {"fields": ("is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Dates", {"fields": ("last_login", "created_at", "updated_at")}),
    )

    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "first_name", "last_name", "password1", "password2"),
        }),
    )




@admin.register(OAuthAccount)
class OAuthAccountAdmin(ModelAdmin):
    list_display = ("user", "provider", "email", "created_at")
    search_fields = ("user__email", "email")
    readonly_fields = ("user", "provider", "provider_user_id", "email", "created_at", "updated_at")

    def has_add_permission(self, request):
        return False