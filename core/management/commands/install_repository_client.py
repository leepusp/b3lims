from django.core.management.base import BaseCommand, CommandError

from core.services import repository


class Command(BaseCommand):
    help = "Copy b3repo.py (the notebook/Galaxy reader of the internal repository) into <repository>/lib."

    def handle(self, *args, **options):
        try:
            target = repository.install_client()
        except OSError as exc:
            raise CommandError(str(exc))

        self.stdout.write(self.style.SUCCESS(f"Installed {target}"))
