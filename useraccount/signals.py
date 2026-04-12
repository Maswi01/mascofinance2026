from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
from .models import CustomUser

@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_token(sender, instance, created, **kwargs):
    if not created or instance.is_superuser:
        return

    # Social login user (Google) — activate immediately
    if not instance.has_usable_password():
        instance.is_active = True
        instance.save()
        return

    # All other users (staff, regular signup) — just ensure they are active
    # No OTP, no email sent
    if not instance.is_active:
        CustomUser.objects.filter(id=instance.id).update(is_active=True)