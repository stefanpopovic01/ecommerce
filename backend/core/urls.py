
from django.contrib import admin
from django.urls import path, include

admin.site.has_permission = lambda request: request.user.is_active and request.user.is_superuser

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/', include('accounts.urls')),
    path('api/staff/', include("accounts.staff_urls"))
]
