from django.contrib.auth.tokens import PasswordResetTokenGenerator

''' Custom token generator for email verification created by reusing Django's built-in password-reset token mechanism.
The idea is that when a user registers, we generate a token, sent it via email, and let the user click
a link to verify their email address. Backend then checks wheter the token is valid. '''

class EmailVerificationTokenGenerator(PasswordResetTokenGenerator): # Inherits the functionality of PasswordResetTokenGenerator
    key_salt = "accounts.tokens.EmailVerificationTokenGenerator" # helps distinguis email-verification tokens from other tokens

    def _make_hash_value(self, user, timestamp):
        return f"{user.pk}{user.email}{user.email_verified_at}{timestamp}" # Returns a string containing values associated with the user and token's timestamp.

email_verification_token = EmailVerificationTokenGenerator() # Instance of our custom token generator - use it as: token = email_verification_token.make_token(user)
