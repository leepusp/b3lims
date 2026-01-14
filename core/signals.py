from django.db.models.signals import pre_save
from django.dispatch import receiver
from core.models.samples.sample import Sample
from core.models.events import Event

@receiver(pre_save, sender=Sample)
def track_sample_history(sender, instance, **kwargs):
    # Se for uma amostra nova (sem ID ainda), não fazemos o rastreio de mudança
    if not instance.pk:
        return

    try:
        # Pega a versão atual que está no banco antes de salvar a nova
        old_instance = Sample.objects.get(pk=instance.pk)
    except Sample.DoesNotExist:
        return

    # 1. Rastreio de Movimentação Física (MAPA/LOG)
    if old_instance.storage_location != instance.storage_location:
        Event.objects.create(
            sample=instance,
            event_type="transfer",
            location_snapshot=instance.storage_location or "N/A",
            notes=f"Movimentação detectada: De '{old_instance.storage_location}' para '{instance.storage_location}'"
        )

    # 2. Rastreio de Mudança de Status (Controle de Qualidade)
    if old_instance.status != instance.status:
        Event.objects.create(
            sample=instance,
            event_type="qc_update",
            notes=f"Status alterado: {old_instance.get_status_display()} -> {instance.get_status_display()}"
        )