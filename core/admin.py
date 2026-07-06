from django.contrib import admin
from django.db.models import Q
from django.utils.html import format_html

from import_export import resources
from import_export.admin import ImportExportModelAdmin

from core.models import (
    Biobank,
    Collection,
    Sample,
    SampleFile,
    Event,
    Tag,
    Keyword,
    KeywordValue,
    Bacteria,
    Phage,
    HostRange,
    Plasmid,
    SampleImportBatch,
    SampleIntakeRecord
)

class SampleResource(resources.ModelResource):
    class Meta:
        model = Sample
        fields = ('id', 'sample_id', 'sample_type', 'organism_name', 'status', 'owner__username', 'created_at')

class SampleFileInline(admin.TabularInline):
    model = SampleFile
    extra = 0
    readonly_fields = ("uploaded_at", "mime_type", "file_size")

@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("name", "description")
    search_fields = ("name",)

@admin.register(Biobank)
class BiobankAdmin(admin.ModelAdmin):
    list_display = ("name", "location_label", "is_public", "is_active")
    filter_horizontal = ("tags", "keywords")

@admin.register(Collection)
class CollectionAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "is_public")
    filter_horizontal = ("tags", "keywords")

@admin.register(Sample)
class SampleAdmin(ImportExportModelAdmin):
    resource_classes = [SampleResource]
    list_display = ("sample_id", "sample_type", "organism_name", "status", "owner", "created_at")
    list_filter = ("status", "sample_type", "is_public")
    search_fields = ("sample_id", "organism_name")
    inlines = [SampleFileInline]
    filter_horizontal = ("collections", "tags", "keywords")

@admin.register(Bacteria)
class BacteriaAdmin(admin.ModelAdmin):
    list_display = ("sample_id", "species", "strain", "owner")
    search_fields = ("sample_id", "species", "strain")
    filter_horizontal = ("collections", "tags", "keywords")

@admin.register(Phage)
class PhageAdmin(admin.ModelAdmin):
    list_display = ("sample_id", "taxonomy", "morphotype", "lifestyle")
    list_filter = ("morphotype", "lifestyle")
    filter_horizontal = ("collections", "tags", "keywords")

@admin.register(HostRange)
class HostRangeAdmin(admin.ModelAdmin):
    list_display = ("phage", "bacteria", "is_isolation_host", "efficiency_eop")
    list_filter = ("is_isolation_host",)

@admin.register(Plasmid)
class PlasmidAdmin(admin.ModelAdmin):
    # Atualizado com os novos campos unificados
    list_display = ("sample_id", "backbone_name", "insert_name", "construction_name", "total_size_bp", "is_empty_vector")
    search_fields = ("sample_id", "backbone_name", "insert_name", "construction_name")
    readonly_fields = ("total_size_bp",) 
    filter_horizontal = ("collections", "tags", "keywords")

@admin.register(SampleFile)
class SampleFileAdmin(admin.ModelAdmin):
    list_display = ("file", "sample", "category", "uploaded_at")

@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("sample", "event_type", "timestamp", "performed_by")
    readonly_fields = ("timestamp",)


@admin.register(SampleImportBatch)
class SampleImportBatchAdmin(admin.ModelAdmin):
    list_display = ("id", "original_filename", "uploaded_by", "status", "total_rows", "valid_rows", "invalid_rows", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("original_filename", "uploaded_by__username")


@admin.register(SampleIntakeRecord)
class SampleIntakeRecordAdmin(admin.ModelAdmin):
    list_display = ("row_number", "imported_sample_id", "sample_type", "organism_name", "status", "matched_biobank", "matched_collection")
    list_filter = ("status", "sample_type")
    search_fields = ("imported_sample_id", "organism_name", "biobank_name", "collection_name")


# Shipment / transport administration
from core.models import (
    Shipment,
    ShipmentItem,
    TransportClassification,
    ShipmentDocument,
    ShipmentChecklistItem,
    ShipmentReceipt,
    ShipmentAccessToken,
    ShipmentEvent,
)


class ShipmentItemInline(admin.TabularInline):
    model = ShipmentItem
    extra = 0
    autocomplete_fields = ["sample", "intake_record"]


class ShipmentDocumentInline(admin.TabularInline):
    model = ShipmentDocument
    extra = 0


class ShipmentChecklistItemInline(admin.TabularInline):
    model = ShipmentChecklistItem
    extra = 0


class TransportClassificationInline(admin.StackedInline):
    model = TransportClassification
    extra = 0
    max_num = 1



class ShipmentReceiptInline(admin.StackedInline):
    model = ShipmentReceipt
    extra = 0
    max_num = 1
    readonly_fields = ["created_at", "updated_at"]

@admin.register(Shipment)
class ShipmentAdmin(admin.ModelAdmin):
    list_display = [
        "shipment_code",
        "flow_type",
        "status",
        "origin_biobank",
        "destination_biobank",
        "requested_by",
        "created_at",
    ]
    list_filter = ["flow_type", "status", "origin_biobank", "destination_biobank"]
    search_fields = [
        "shipment_code",
        "sender_institution",
        "recipient_institution",
        "tracking_code",
    ]
    readonly_fields = ["uuid", "shipment_code", "created_at", "updated_at"]
    inlines = [
        TransportClassificationInline,
        ShipmentItemInline,
        ShipmentDocumentInline,
        ShipmentChecklistItemInline,
        ShipmentReceiptInline,
    ]


@admin.register(ShipmentEvent)



class ShipmentEventAdmin(admin.ModelAdmin):
    list_display = ["shipment", "event_type", "actor", "created_at"]
    list_filter = ["event_type", "created_at"]
    search_fields = ["shipment__shipment_code", "notes"]



@admin.register(ShipmentReceipt)
class ShipmentReceiptAdmin(admin.ModelAdmin):
    list_display = [
        "shipment",
        "package_condition",
        "package_integrity_confirmed",
        "documents_received",
        "items_checked",
        "received_by",
        "received_at",
    ]
    list_filter = [
        "package_condition",
        "package_integrity_confirmed",
        "documents_received",
        "items_checked",
        "received_at",
    ]
    search_fields = [
        "shipment__shipment_code",
        "notes",
    ]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(ShipmentAccessToken)
class ShipmentAccessTokenAdmin(admin.ModelAdmin):
    list_display = [
        "shipment",
        "access_type",
        "token",
        "is_active",
        "expires_at",
        "created_at",
    ]
    list_filter = [
        "access_type",
        "is_active",
        "created_at",
    ]
    search_fields = [
        "shipment__shipment_code",
        "token",
    ]
    readonly_fields = [
        "token",
        "created_at",
        "updated_at",
    ]

from core.models.chemicals.chemical import Chemical, ChemicalStockMovement


@admin.register(Chemical)
class ChemicalAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "cas_number",
        "supplier",
        "catalog_number",
        "lot_number",
        "quantity",
        "quantity_value",
        "quantity_unit",
        "storage_location",
        "storage_temperature",
        "expiry_date",
        "status",
        "research_group",
        "created_by",
        "created_at",
    )
    list_filter = (
        "status",
        "storage_temperature",
        "research_group",
        "is_public",
        "created_at",
        "expiry_date",
    )
    search_fields = (
        "name",
        "formula",
        "cas_number",
        "supplier",
        "catalog_number",
        "lot_number",
        "barcode",
        "location",
        "storage_location",
    )
    readonly_fields = ("uuid", "created_at", "updated_at")
    ordering = ("name",)



@admin.register(ChemicalStockMovement)
class ChemicalStockMovementAdmin(admin.ModelAdmin):
    list_display = (
        "chemical",
        "movement_type",
        "amount_value",
        "amount_unit",
        "quantity_before",
        "quantity_after",
        "performed_by",
        "created_at",
    )
    list_filter = ("movement_type", "created_at", "performed_by")
    search_fields = (
        "chemical__name",
        "chemical__cas_number",
        "chemical__supplier",
        "chemical__lot_number",
        "reason",
    )
    readonly_fields = ("created_at",)
    ordering = ("-created_at", "-id")
