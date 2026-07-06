import uuid
from django.db import models
from django.contrib.auth.models import User
from core.models.research_groups.model import ResearchGroup

class Chemical(models.Model):
    """
    Representa um Reagente, Solvente ou Solução no laboratório.
    """
    STATUS_CHOICES = [
        ('available', 'Available'),
        ('low_stock', 'Low Stock'),
        ('expired', 'Expired'),
        ('depleted', 'Depleted'),
    ]

    # Identificação
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    name = models.CharField(max_length=255, help_text="Common name (e.g. Ethanol 70%)")
    formula = models.CharField(max_length=100, blank=True, null=True, help_text="Molecular formula (e.g. C2H5OH)")
    cas_number = models.CharField(max_length=50, blank=True, null=True, help_text="CAS Registry Number")
    
    # Inventory metadata
    supplier = models.CharField(max_length=255, blank=True, null=True, help_text="Supplier or manufacturer")
    catalog_number = models.CharField(max_length=100, blank=True, null=True, help_text="Supplier catalog number")
    lot_number = models.CharField(max_length=100, blank=True, null=True, help_text="Batch or lot number")

    # Structured stock information
    quantity_value = models.DecimalField(max_digits=12, decimal_places=3, blank=True, null=True)
    quantity_unit = models.CharField(max_length=30, blank=True, null=True, help_text="mL, L, g, mg, units, kits, bottles, etc.")
    minimum_quantity = models.DecimalField(max_digits=12, decimal_places=3, blank=True, null=True)

    # Legacy free-text quantity kept for backward compatibility
    quantity = models.CharField(max_length=50, help_text="Quantity with units (e.g. 500mL, 10g)")

    expiry_date = models.DateField(blank=True, null=True)

    # Structured and legacy storage location
    storage_temperature = models.CharField(max_length=50, blank=True, null=True, help_text="-80C, -20C, 4C, RT, LN2, etc.")
    storage_location = models.CharField(max_length=255, blank=True, null=True, help_text="Room, cabinet, freezer, shelf or box")
    barcode = models.CharField(max_length=100, blank=True, null=True, unique=True)

    # Legacy free-text location kept for backward compatibility
    location = models.CharField(max_length=255, blank=True, null=True, help_text="Shelf, Cabinet, or Fridge location")
    
    # Segurança
    msds_link = models.URLField(blank=True, null=True, help_text="Link to Material Safety Data Sheet")
    hazard_notes = models.TextField(blank=True, null=True, help_text="Safety warnings (Flammable, Toxic, etc.)")

    # Sistema
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='available')
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="chemicals")
    research_group = models.ForeignKey(
        ResearchGroup,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="chemicals",
        help_text="Research group responsible for this reagent."
    )
    is_public = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.quantity})"
