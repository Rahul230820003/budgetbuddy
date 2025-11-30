from django.core.management.base import BaseCommand
from tracker.tasks import process_recurring_transactions

class Command(BaseCommand):
    help = 'Process recurring transactions'

    def handle(self, *args, **options):
        processed_count = process_recurring_transactions()
        self.stdout.write(
            self.style.SUCCESS(f'Successfully processed {processed_count} recurring transactions')
        ) 