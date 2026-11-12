from django.db import models


class SampleType(models.Model):
    """A Sample type defined by the installation (cell line, nucleic acid, dataset ...).

    The four built-in types (bacterium, phage, plasmid, other) stay in code; this table only holds the
    types an installation adds. ``fields`` lists the extra fields as dictionaries with the keys
    ``key``, ``label``, ``kind`` (text, integer, decimal, boolean, choice, date), ``required`` and ``choices``.
    """

    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=60, unique=True)
    id_prefix = models.CharField(max_length=12, default="SMP-")
    has_organism = models.BooleanField(
        default=False, help_text="Ask for an organism or species name when registering this type.",
    )
    default_biosafety = models.CharField(max_length=10, blank=True)
    fields = models.JSONField(default=list, blank=True)
    description = models.CharField(max_length=300, blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=100)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name
