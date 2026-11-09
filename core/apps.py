from django.apps import AppConfig

class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        # Importa os signals para que eles comecem a ouvir as mudanças nos modelos
        import core.signals
        from core.services import activity

        activity.connect()
