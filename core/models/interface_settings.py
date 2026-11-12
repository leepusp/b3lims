from django.db import models


class InterfaceSettings(models.Model):
    """What this installation shows in its menu and in the New Sample form (a single row).

    Hiding is about tidiness, not security: a hidden page is still reachable by its address and
    still obeys the normal permissions.
    """

    hidden_features = models.JSONField(default=list, blank=True)
    hidden_sample_types = models.JSONField(default=list, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "interface settings"

    def __str__(self):
        return "Interface settings"
