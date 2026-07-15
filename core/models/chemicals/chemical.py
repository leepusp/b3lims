import mimetypes
import os
import uuid
from django.db import models
from django.contrib.auth.models import User
from core.models.research_groups.model import ResearchGroup


def chemical_document_upload_to(instance, filename):
    """Store documents under an opaque reagent UUID and opaque filename."""
    extension = os.path.splitext(filename)[1].lower()[:16]
    return f"chemicals/{instance.chemical.uuid}/documents/{uuid.uuid4().hex}{extension}"

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
    is_active = models.BooleanField(default=True, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.quantity})"


class ChemicalFile(models.Model):
    DOCUMENT_TYPES = [
        ("sds", "Safety Data Sheet (SDS)"),
        ("coa", "Certificate of Analysis"),
        ("specification", "Product Specification"),
        ("protocol", "Protocol / Instructions"),
        ("other", "Other Document"),
    ]

    chemical = models.ForeignKey(
        Chemical,
        on_delete=models.CASCADE,
        related_name="files",
    )
    file = models.FileField(upload_to=chemical_document_upload_to)
    original_filename = models.CharField(max_length=255)
    title = models.CharField(max_length=255)
    document_type = models.CharField(
        max_length=30,
        choices=DOCUMENT_TYPES,
        default="other",
    )
    description = models.TextField(blank=True)
    version = models.CharField(max_length=50, blank=True)
    document_date = models.DateField(blank=True, null=True)
    mime_type = models.CharField(max_length=150, blank=True)
    file_size = models.BigIntegerField(blank=True, null=True)
    is_primary = models.BooleanField(
        default=False,
        help_text="Primary SDS shown on the reagent QR page.",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    uploaded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="chemical_files",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-is_primary", "-document_date", "-uploaded_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["chemical"],
                condition=models.Q(is_active=True, is_primary=True),
                name="unique_active_primary_chemical_document",
            ),
            models.CheckConstraint(
                condition=models.Q(is_primary=False) | models.Q(document_type="sds"),
                name="primary_chemical_document_must_be_sds",
            ),
        ]

    def save(self, *args, **kwargs):
        if self.file:
            if not self.original_filename:
                self.original_filename = os.path.basename(self.file.name)
            self.file_size = self.file.size
            self.mime_type = mimetypes.guess_type(self.original_filename)[0] or "application/octet-stream"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.chemical.name} · {self.title}"



class ChemicalStockMovement(models.Model):
    """
    Audit trail for reagent stock changes.

    intake: stock added
    consumption: stock consumed by routine use
    adjustment: manual correction; amount_value becomes the new stock value
    disposal: stock removed due to discard
    """
    MOVEMENT_TYPES = [
        ("intake", "Intake"),
        ("consumption", "Consumption"),
        ("adjustment", "Adjustment"),
        ("disposal", "Disposal"),
    ]

    chemical = models.ForeignKey(
        Chemical,
        on_delete=models.CASCADE,
        related_name="stock_movements",
    )
    movement_type = models.CharField(max_length=20, choices=MOVEMENT_TYPES)
    amount_value = models.DecimalField(max_digits=12, decimal_places=3)
    amount_unit = models.CharField(max_length=30, blank=True, null=True)

    quantity_before = models.DecimalField(max_digits=12, decimal_places=3, blank=True, null=True)
    quantity_after = models.DecimalField(max_digits=12, decimal_places=3, blank=True, null=True)

    reason = models.TextField(blank=True, null=True)
    performed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="chemical_stock_movements",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.chemical.name} · {self.get_movement_type_display()} · {self.amount_value} {self.amount_unit or ''}".strip()
