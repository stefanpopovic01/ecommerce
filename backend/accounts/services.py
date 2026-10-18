from django.db import transaction
from django.utils import timezone

from .models import OAuthAccount, User

@transaction.atomic
def get_or_create_google_user(payload: dict) -> User:
    sub = payload["sub"]
    email = payload["email"].lower()

    # 1. Returning Google user: matched by Google's stable ID
    link = (
        OAuthAccount.objects.select_related("user")
        .filter(provider=OAuthAccount.Provider.GOOGLE, provider_user_id=sub)
        .first()
    )
    if link:
        return link.user

    # "payload: dict" just a hint, payload is expected to be dictionary
    # -> User just a hint, return value of function is expected to be User model instance.

    # 2. Existing account with this email: link Google to it
    user = User.objects.filter(email__iexact=email).first()
    if user:
        if user.email_verified_at is None:
            user.set_unusable_password()
            user.email_verified_at = timezone.now()
            user.save(update_fields=["password", "email_verified_at"])

    else:
        # 3. Brand-new user
        user = User.objects.create_user(
            email=email,
            password=None,
            first_name=payload.get("given_name", ""),
            last_name=payload.get("family_name", ""),
            email_verified_at=timezone.now(),
        )

    OAuthAccount.objects.create(
        user=user,
        provider=OAuthAccount.Provider.GOOGLE,
        provider_user_id=sub,
        email=email
    )
    return user