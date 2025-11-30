from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from tracker.models import ExpenseCategory

class Command(BaseCommand):
    help = 'Updates existing users with new default categories'

    def handle(self, *args, **kwargs):
        # Define the new default categories
        default_categories = [
            'Food & Dining',
            'Transportation',
            'Housing',
            'Entertainment',
            'Utilities',
            'Healthcare',
            'Education',
            'Shopping',
            'Personal Care',
            'Gifts & Donations',
            'Travel',
            'Insurance',
            'Investments',
            'Debt Payments',
            'Other'
        ]

        # Get all users
        users = User.objects.all()
        updated_count = 0

        for user in users:
            # Get existing categories for this user
            existing_categories = set(ExpenseCategory.objects.filter(user=user).values_list('name', flat=True))
            
            # Add missing categories
            for category_name in default_categories:
                if category_name not in existing_categories:
                    ExpenseCategory.objects.create(
                        name=category_name,
                        user=user
                    )
                    updated_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(f'Added category "{category_name}" for user "{user.username}"')
                    )

        self.stdout.write(
            self.style.SUCCESS(f'Successfully updated categories for {updated_count} users')
        ) 