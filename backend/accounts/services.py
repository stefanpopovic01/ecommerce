import logging
logger = logging.getLogger(__name__)

from django.db import transaction
from django.utils import timezone
from django.conf import settings
from django.core.mail import send_mail
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.contrib.auth.tokens import default_token_generator

from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from .models import OAuthAccount, User
from .tokens import email_verification_token, account_deletion_token



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

    # 2. Existing account with this email: link Google to it
    user = User.objects.filter(email__iexact=email).first()
    if user:
        if user.email_verified_at is None:
            user.set_unusable_password()
            user.email_verified_at = timezone.now()
            user.save(update_fields=["password", "email_verified_at", "updated_at"])
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



def send_verification_email(user):
    uid = urlsafe_base64_encode(force_bytes(user.pk)) # Turns the UUID into a URL-safe string.
    token = email_verification_token.make_token(user)
    link = f"{settings.FRONTEND_URL}/verify-email?uid={uid}&token={token}"

    send_mail(
        subject="Potvrdite vašu email adresu",    
        message=(
            f"Zdravo {user.first_name},\n\n"
            f"Potvrdite email adresu klikom na link:\n{link}\n\n"
            f"Link važi 3 dana. Ako niste napravili nalog, ignorišite ovu poruku."
        ),
        from_email=None, # uses DEFAULT_FROM_EMAIL
        recipient_list=[user.email],
    )



def send_password_reset_email(user):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    link = f"{settings.FRONTEND_URL}/reset-password?uid={uid}&token={token}"

    send_mail(
        subject="Resetovanje lozinke",
        message=(
            f"Zdravo {user.first_name},\n\n"
            f"Za novu lozinku kliknite na link:\n{link}\n\n"
            f"Ako niste tražili promenu lozinke, ignorišite ovu poruku."
        ),
        from_email=None,
        recipient_list=[user.email],
    )



@transaction.atomic
def reset_password(user, new_password):
    user.set_password(new_password)
    if user.email_verified_at is None:
        user.email_verified_at = timezone.now()
    user.save(update_fields=["password", "email_verified_at", "updated_at"])

    for token in OutstandingToken.objects.filter(user=user):
        BlacklistedToken.objects.get_or_create(token=token)



def blacklist_all_tokens(user):
    for token in OutstandingToken.objects.filter(user=user):
        BlacklistedToken.objects.get_or_create(token=token)



@transaction.atomic
def change_password(user, new_password):
    user.set_password(new_password)
    user.save(update_fields=["password", "updated_at"])
    blacklist_all_tokens(user)

    refresh = RefreshToken.for_user(user)       

    return {"refresh": str(refresh), "access": str(refresh.access_token)}



@transaction.atomic
def delete_account(user):
    blacklist_all_tokens(user)
    user.delete()



def send_account_deletion_email(user):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = account_deletion_token.make_token(user)
    link = f"{settings.FRONTEND_URL}/confirm-account-deletion?uid={uid}&token={token}"

    send_mail(
        subject="Potvrda brisanja naloga",
        message=(
            f"Zdravo {user.first_name},\n\n"
            f"Zatražili ste brisanje naloga. Za potvrdu kliknite na link:\n{link}\n\n"
            f"Ako niste vi zatražili brisanje, ignorišite ovu poruku. Vaš nalog ostaje nepromenjen."
        ),
        from_email=None,
        recipient_list=[user.email],
    )



@transaction.atomic
def invite_staff(email, first_name, last_name, groups):
    user = User.objects.create_user(
        email=email,
        password=None,  # unusable until they set one via the invite link
        first_name=first_name,
        last_name=last_name,
        is_staff=True,
    )
    user.groups.set(groups)
    transaction.on_commit(lambda: send_staff_invite_email(user))
    return user


def send_staff_invite_email(user):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    link = f"{settings.DASHBOARD_URL}/set-password?uid={uid}&token={token}"

    send_mail(
        subject="Pozivnica za administraciju prodavnice",
        message=(
            f"Zdravo {user.first_name},\n\n"
            f"Dodati ste kao član osoblja. Postavite lozinku klikom na link:\n{link}\n\n"
            f"Link važi 3 dana."
        ),
        from_email=None,
        recipient_list=[user.email],
    )


@transaction.atomic
def set_staff_groups(user, groups):
    user.groups.set(groups)
    blacklist_all_tokens(user)  # force re-login so the dashboard reloads their new permissions