import uuid
from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
from phonenumber_field.modelfields import PhoneNumberField
from django.db.models.functions import Lower



''' Since username = None in AbstractUser, custom UserManager needs to be defined. 
Otherwise commands such as python manage.py createsuperuser will throw an error
Default comands such as create_user etc must be defined '''

class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("Email is required")
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password() # OAuth users

        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if not extra_fields["is_staff"] or not extra_fields["is_superuser"]:
            raise ValueError("Superuser must have is_staff=True and is_superuser=True")        
        return self._create_user(email, password, **extra_fields)

    def get_by_natural_key(self, username): # Method Django calls to find a user by their USERNAME_FIELD. Overriding it makes the lookup case-insensitive.
        return self.get(email__iexact=username)



class User(AbstractUser):

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    username = None
    date_joined = None

    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    email = models.EmailField(unique=True)
    phone = PhoneNumberField(blank=True)

    email_verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager() # User uses UserManager and it's methods
    USERNAME_FIELD = "email" # main field for indentification
    REQUIRED_FIELDS = ["first_name", "last_name"] # For terminal command - required first_name and last_name as well 

    class Meta:
        constraints = [
            models.UniqueConstraint(Lower("email"), name="unique_user_email_ci"), # prevents users from registering with the same email address using different capitalization.
        ]

    def __str__(self):
        return self.email



class OAuthAccount(models.Model):
    class Provider(models.TextChoices):
        GOOGLE = "google", "Google"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="oauth_accounts")
    provider = models.CharField(max_length=20, choices=Provider.choices)
    provider_user_id = models.CharField(max_length=255) # Google's "sub" claim. Sub is Google’s permanent ID for that account and never changes
    email = models.EmailField() # email Google reported at link time, for reference
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta: 
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "provider_user_id"],
                name="unique_oauth_identity",
            ),
        ]