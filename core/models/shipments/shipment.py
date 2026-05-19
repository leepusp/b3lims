from uuid import uuid4
import hashlib

from django.conf import settings
from django.db import models
from django.utils import timezone


def shipment_document_upload_to(instance, filename):
    code = instance.shipment.shipment_code or "draft"
    return f"shipment_documents/{code}/{filename}"


class Shipment(models.Model):
    FLOW_TYPES = [
        ("incoming_receipt", "Incoming receipt"),
        ("outgoing_shipment", "Outgoing shipment"),
        ("internal_transfer", "Internal transfer"),
        ("external_transfer", "External transfer"),
        ("international_shipment", "International shipment"),
        ("temporary_loan", "Temporary loan"),
        ("return_to_origin", "Return to origin"),
        ("disposal_transport", "Disposal transport"),
    ]

    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("under_review", "Under review"),
        ("waiting_documents", "Waiting documents"),
        ("waiting_authorization", "Waiting authorization"),
        ("authorized", "Authorized"),
        ("packing", "Packing"),
        ("ready_for_dispatch", "Ready for dispatch"),
        ("in_transit", "In transit"),
        ("received_pending_qc", "Received pending QC"),
        ("accepted", "Accepted"),
        ("rejected", "Rejected"),
        ("cancelled", "Cancelled"),
    ]

    uuid = models.UUIDField(default=uuid4, editable=False, unique=True)
    shipment_code = models.CharField(max_length=64, unique=True, blank=True)

    flow_type = models.CharField(max_length=40, choices=FLOW_TYPES, default="incoming_receipt")
    status = models.CharField(max_length=40, choices=STATUS_CHOICES, default="draft")

    origin_biobank = models.ForeignKey(
        "core.Biobank",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="outgoing_shipments",
    )
    destination_biobank = models.ForeignKey(
        "core.Biobank",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="incoming_shipments",
    )

    sender_institution = models.CharField(max_length=255, blank=True)
    sender_responsible_name = models.CharField(max_length=255, blank=True)
    sender_email = models.EmailField(blank=True)
    sender_phone = models.CharField(max_length=100, blank=True)
    sender_address = models.TextField(blank=True)

    recipient_institution = models.CharField(max_length=255, blank=True)
    recipient_responsible_name = models.CharField(max_length=255, blank=True)
    recipient_email = models.EmailField(blank=True)
    recipient_phone = models.CharField(max_length=100, blank=True)
    recipient_address = models.TextField(blank=True)

    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="requested_shipments",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_shipments",
    )
    authorized_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="authorized_shipments",
    )

    transport_method = models.CharField(max_length=100, blank=True)
    carrier_name = models.CharField(max_length=255, blank=True)
    tracking_code = models.CharField(max_length=255, blank=True)
    temperature_condition = models.CharField(max_length=100, blank=True)

    expected_dispatch_date = models.DateField(null=True, blank=True)
    dispatched_at = models.DateTimeField(null=True, blank=True)
    expected_arrival_date = models.DateField(null=True, blank=True)
    received_at = models.DateTimeField(null=True, blank=True)

    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Shipment"
        verbose_name_plural = "Shipments"

    def __str__(self):
        return self.shipment_code or f"Shipment {self.pk}"

    def save(self, *args, **kwargs):
        if not self.shipment_code:
            today = timezone.localdate().strftime("%Y%m%d")
            self.shipment_code = f"SHP-{today}-{uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)


class ShipmentItem(models.Model):
    shipment = models.ForeignKey(
        Shipment,
        on_delete=models.CASCADE,
        related_name="items",
    )

    sample = models.ForeignKey(
        "core.Sample",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="shipment_items",
    )

    intake_record = models.ForeignKey(
        "core.SampleIntakeRecord",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="shipment_items",
    )

    imported_sample_id = models.CharField(max_length=100, blank=True)
    material_name = models.CharField(max_length=255, blank=True)
    sample_type = models.CharField(max_length=100, blank=True)

    quantity = models.DecimalField(max_digits=12, decimal_places=3, default=1)
    quantity_unit = models.CharField(max_length=50, blank=True)
    container_count = models.PositiveIntegerField(default=1)
    container_type = models.CharField(max_length=100, blank=True)
    volume_or_weight = models.CharField(max_length=100, blank=True)
    culture_medium = models.CharField(max_length=255, blank=True)
    storage_condition = models.CharField(max_length=100, blank=True)

    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["id"]
        verbose_name = "Shipment item"
        verbose_name_plural = "Shipment items"

    def __str__(self):
        return self.imported_sample_id or self.material_name or f"Item {self.pk}"

    def save(self, *args, **kwargs):
        if self.sample:
            if not self.imported_sample_id:
                self.imported_sample_id = self.sample.sample_id
            if not self.material_name:
                self.material_name = self.sample.organism_name
            if not self.sample_type:
                self.sample_type = self.sample.sample_type

        if self.intake_record:
            if not self.imported_sample_id:
                self.imported_sample_id = self.intake_record.imported_sample_id
            if not self.material_name:
                self.material_name = self.intake_record.organism_name
            if not self.sample_type:
                self.sample_type = self.intake_record.sample_type

        super().save(*args, **kwargs)


class TransportClassification(models.Model):
    MATERIAL_TYPES = [
        ("bacteria", "Bacteria"),
        ("phage", "Phage"),
        ("plasmid", "Plasmid"),
        ("mixed", "Mixed"),
        ("other", "Other"),
        ("unknown", "Unknown"),
    ]

    RISK_CLASSES = [
        ("unknown", "Unknown"),
        ("CR1", "Risk class 1"),
        ("CR2", "Risk class 2"),
        ("CR3", "Risk class 3"),
        ("CR4", "Risk class 4"),
    ]

    BIOSAFETY_LEVELS = [
        ("unknown", "Unknown"),
        ("NB1", "NB-1"),
        ("NB2", "NB-2"),
        ("NB3", "NB-3"),
        ("NB4", "NB-4"),
    ]

    shipment = models.OneToOneField(
        Shipment,
        on_delete=models.CASCADE,
        related_name="classification",
    )

    material_type = models.CharField(max_length=40, choices=MATERIAL_TYPES, default="unknown")
    risk_class = models.CharField(max_length=20, choices=RISK_CLASSES, default="unknown")
    biosafety_level = models.CharField(max_length=20, choices=BIOSAFETY_LEVELS, default="unknown")

    is_ogm = models.BooleanField(default=False)
    is_genetic_heritage = models.BooleanField(default=False)
    is_international = models.BooleanField(default=False)

    is_category_b_un3373 = models.BooleanField(default=False)
    is_exempt_biological_material = models.BooleanField(default=False)

    requires_cibio_notification = models.BooleanField(default=False)
    requires_ctnbio_authorization = models.BooleanField(default=False)
    requires_mta_ttm = models.BooleanField(default=False)
    requires_sisgen = models.BooleanField(default=False)

    requires_triple_packaging = models.BooleanField(default=False)
    requires_biohazard_label = models.BooleanField(default=False)
    requires_un3373_label = models.BooleanField(default=False)
    requires_external_package_identification = models.BooleanField(default=True)

    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = "Transport classification"
        verbose_name_plural = "Transport classifications"

    def __str__(self):
        return f"Classification for {self.shipment}"

    def apply_default_rules(self, save=True):
        is_higher_risk = self.risk_class in ["CR2", "CR3", "CR4"] or self.biosafety_level in ["NB2", "NB3", "NB4"]

        self.is_category_b_un3373 = bool(self.is_ogm or is_higher_risk)
        self.is_exempt_biological_material = not self.is_category_b_un3373 and not self.is_ogm

        self.requires_triple_packaging = bool(self.is_category_b_un3373 or self.is_ogm)
        self.requires_biohazard_label = bool(self.is_category_b_un3373 or self.is_ogm)
        self.requires_un3373_label = bool(self.is_category_b_un3373)

        self.requires_external_package_identification = True
        self.requires_cibio_notification = bool(self.is_ogm)
        self.requires_ctnbio_authorization = bool(self.is_ogm and is_higher_risk)

        self.requires_mta_ttm = bool(self.is_international and self.is_genetic_heritage)
        self.requires_sisgen = bool(self.is_international and self.is_genetic_heritage)

        if save:
            self.save()

    def required_document_types(self):
        documents = [
            "content_declaration",
            "external_package_identification",
        ]

        if self.is_category_b_un3373 or self.is_ogm:
            documents.extend([
                "sender_declaration",
                "triple_packaging_checklist",
            ])

        if self.is_ogm:
            documents.append("ogm_transport_notification")

        if self.requires_mta_ttm:
            documents.extend([
                "mta_ttm",
                "shipment_invoice",
            ])

        return list(dict.fromkeys(documents))


class ShipmentDocument(models.Model):
    DOCUMENT_TYPES = [
        ("content_declaration", "Content declaration"),
        ("sender_declaration", "Sender declaration"),
        ("external_package_identification", "External package identification"),
        ("triple_packaging_checklist", "Triple packaging checklist"),
        ("ogm_transport_notification", "OGM transport notification"),
        ("mta_ttm", "MTA/TTM"),
        ("shipment_invoice", "Shipment invoice"),
        ("receipt_confirmation", "Receipt confirmation"),
        ("other", "Other"),
    ]

    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("generated", "Generated"),
        ("waiting_signature", "Waiting signature"),
        ("signed", "Signed"),
        ("uploaded", "Uploaded"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
    ]

    SIGNATURE_PROVIDERS = [
        ("manual_upload", "Manual upload"),
        ("govbr_external", "gov.br external signature"),
        ("usp_sam", "USP SAM"),
        ("other", "Other"),
    ]

    shipment = models.ForeignKey(
        Shipment,
        on_delete=models.CASCADE,
        related_name="documents",
    )

    document_type = models.CharField(max_length=80, choices=DOCUMENT_TYPES)
    status = models.CharField(max_length=40, choices=STATUS_CHOICES, default="draft")

    generated_file = models.FileField(upload_to=shipment_document_upload_to, blank=True, null=True)
    signed_file = models.FileField(upload_to=shipment_document_upload_to, blank=True, null=True)

    generated_hash = models.CharField(max_length=128, blank=True)
    signed_hash = models.CharField(max_length=128, blank=True)

    requires_signature = models.BooleanField(default=False)
    signature_provider = models.CharField(max_length=50, choices=SIGNATURE_PROVIDERS, default="manual_upload")

    generated_at = models.DateTimeField(null=True, blank=True)
    signed_at = models.DateTimeField(null=True, blank=True)

    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="uploaded_shipment_documents",
    )

    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["document_type", "id"]
        unique_together = ("shipment", "document_type")
        verbose_name = "Shipment document"
        verbose_name_plural = "Shipment documents"

    def __str__(self):
        return f"{self.get_document_type_display()} - {self.shipment}"

    def update_hashes(self, save=True):
        if self.generated_file:
            self.generated_hash = self._file_sha256(self.generated_file)
        if self.signed_file:
            self.signed_hash = self._file_sha256(self.signed_file)
        if save:
            self.save()

    @staticmethod
    def _file_sha256(file_field):
        sha = hashlib.sha256()
        file_field.open("rb")
        try:
            for chunk in iter(lambda: file_field.read(8192), b""):
                sha.update(chunk)
        finally:
            file_field.close()
        return sha.hexdigest()


class ShipmentChecklistItem(models.Model):
    CHECKLIST_TYPES = [
        ("data", "Required data"),
        ("document", "Document"),
        ("authorization", "Authorization"),
        ("packaging", "Packaging"),
        ("label", "Label"),
        ("dispatch", "Dispatch"),
        ("receipt", "Receipt"),
    ]

    shipment = models.ForeignKey(
        Shipment,
        on_delete=models.CASCADE,
        related_name="checklist_items",
    )

    checklist_type = models.CharField(max_length=40, choices=CHECKLIST_TYPES)
    label = models.CharField(max_length=255)
    is_required = models.BooleanField(default=True)
    is_completed = models.BooleanField(default=False)

    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="completed_shipment_checklist_items",
    )
    completed_at = models.DateTimeField(null=True, blank=True)

    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["checklist_type", "id"]
        verbose_name = "Shipment checklist item"
        verbose_name_plural = "Shipment checklist items"

    def __str__(self):
        return self.label

    def mark_completed(self, user=None, save=True):
        self.is_completed = True
        self.completed_by = user
        self.completed_at = timezone.now()
        if save:
            self.save()


class ShipmentEvent(models.Model):
    EVENT_TYPES = [
        ("created", "Created"),
        ("updated", "Updated"),
        ("submitted", "Submitted"),
        ("classified", "Classified"),
        ("document_generated", "Document generated"),
        ("document_uploaded", "Document uploaded"),
        ("authorized", "Authorized"),
        ("packed", "Packed"),
        ("dispatched", "Dispatched"),
        ("received", "Received"),
        ("qc_checked", "QC checked"),
        ("accepted", "Accepted"),
        ("rejected", "Rejected"),
        ("cancelled", "Cancelled"),
    ]

    shipment = models.ForeignKey(
        Shipment,
        on_delete=models.CASCADE,
        related_name="events",
    )

    event_type = models.CharField(max_length=40, choices=EVENT_TYPES)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="shipment_events",
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = "Shipment event"
        verbose_name_plural = "Shipment events"

    def __str__(self):
        return f"{self.get_event_type_display()} - {self.shipment}"
