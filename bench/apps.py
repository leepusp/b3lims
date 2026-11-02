from django.apps import AppConfig


class BenchConfig(AppConfig):
    """B3 Bench: ELN extensions, Lab Calendar, tools and workflows.

    Dependency rule: ``bench`` may import ``core``; ``core`` never imports
    ``bench``. Panels shown on core screens are registered here through
    ``core.services.extension_panels``.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "bench"
    label = "bench"
    verbose_name = "B3 Bench"

    def ready(self):
        from bench import panels

        panels.register_all()
