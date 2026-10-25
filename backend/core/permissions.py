from rest_framework.permissions import BasePermission, DjangoModelPermissions



class StrictModelPermissions(DjangoModelPermissions):
    """DjangoModelPermissions, but reading also requires the view permission."""
    perms_map = {
        **DjangoModelPermissions.perms_map,
        "GET": ["%(app_label)s.view_%(model_name)s"],
        "HEAD": ["%(app_label)s.view_%(model_name)s"],
    }



def require_perm(perm):
    """Permission class requiring one specific Django permission, e.g. 'accounts.change_user'."""
    class HasPerm(BasePermission):
        def has_permission(self, request, view):
            return request.user.has_perm(perm)
    return HasPerm

