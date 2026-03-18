import os
import shutil
import mimetypes
from django.db import models
from django.utils.text import slugify
from django.conf import settings

# Relative import within the same package (samples)
from .sample import Sample

def sample_file_upload_to(instance, filename):
    sample = instance.sample
    first_collection = sample.collections.first()
    
    # If there is no collection or no biobank, place in unassigned folder
    if not first_collection or not sample.biobank:
        path = f"_unassigned_samples/{slugify(sample.sample_id)}"
    else:
        path = f"{slugify(sample.biobank.name)}/{slugify(first_collection.name)}/{slugify(sample.sample_id)}"
        
    return f"{path}/{filename}"

class SampleFile(models.Model):
    # Categories for the frontend viewer
    VIEW_CATEGORIES = [
        ('image', 'Image (Microscopy/Gel)'),
        ('table', 'Table (CSV/Excel)'),
        ('sequence', 'Sequence (FASTA/FASTQ)'),
        ('pdf', 'PDF Document'),
        ('raw', 'Raw Data / Other'),
    ]

    sample = models.ForeignKey(
        Sample,
        on_delete=models.CASCADE,
        related_name="files",
    )

    file = models.FileField(upload_to=sample_file_upload_to)
    description = models.TextField(blank=True, null=True)
    
    # Metadata for the Viewer
    mime_type = models.CharField(max_length=100, blank=True, null=True)
    file_size = models.BigIntegerField(blank=True, null=True)
    category = models.CharField(max_length=20, choices=VIEW_CATEGORIES, default='raw')
    
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        # Auto-detect metadata before saving
        if self.file:
            self.file_size = self.file.size
            guess, _ = mimetypes.guess_type(self.file.name)
            self.mime_type = guess
            
            ext = os.path.splitext(self.file.name)[1].lower()
            if ext in ['.jpg', '.jpeg', '.png', '.tif', '.tiff']:
                self.category = 'image'
            elif ext in ['.csv', '.xlsx', '.xls']:
                self.category = 'table'
            elif ext in ['.fasta', '.fastq', '.gb']:
                self.category = 'sequence'
            elif ext == '.pdf':
                self.category = 'pdf'
        
        super().save(*args, **kwargs)

    def __str__(self):
        return f"File for {self.sample.sample_id} ({self.category})"

def move_sample_files(sample):
    """Physical file movement logic when associating a new collection"""
    first_collection = sample.collections.first()
    
    if not first_collection or not sample.biobank:
        return

    old_base_rel = os.path.join("_unassigned_samples", slugify(sample.sample_id))
    old_base_abs = os.path.join(settings.MEDIA_ROOT, old_base_rel)

    if not os.path.exists(old_base_abs):
        return

    new_base_rel = os.path.join(
        slugify(sample.biobank.name),
        slugify(first_collection.name),
        slugify(sample.sample_id),
    )
    new_base_abs = os.path.join(settings.MEDIA_ROOT, new_base_rel)

    os.makedirs(new_base_abs, exist_ok=True)
    for filename in os.listdir(old_base_abs):
        old_file_path = os.path.join(old_base_abs, filename)
        new_file_path = os.path.join(new_base_abs, filename)
        shutil.move(old_file_path, new_file_path)

    if not os.listdir(old_base_abs):
        os.rmdir(old_base_abs)

    # FIX: Update the file path in the database using forward slashes for URLs
    db_new_base_rel = f"{slugify(sample.biobank.name)}/{slugify(first_collection.name)}/{slugify(sample.sample_id)}"
    
    for sample_file in sample.files.all():
        # Check if it's still mapped to the old unassigned path
        if "_unassigned_samples" in str(sample_file.file.name):
            filename = os.path.basename(sample_file.file.name)
            sample_file.file.name = f"{db_new_base_rel}/{filename}"
            # update_fields prevents triggering a full super().save() unnecessarily
            sample_file.save(update_fields=['file'])
