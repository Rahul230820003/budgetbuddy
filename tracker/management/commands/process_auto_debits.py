from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from tracker.models import SavingsGoal, Transaction
from datetime import datetime
from dateutil.relativedelta import relativedelta

class Command(BaseCommand):
    help = 'Process automatic debits for savings goals'

    def handle(self, *args, **options):
        now = datetime.now()
        today = now.date()
        current_time = now.time()
        
        # Find goals eligible for auto-debit today
        eligible_goals = SavingsGoal.objects.filter(
            completed=False,
            auto_debit_enabled=True
        )
        
        debit_count = 0
        
        for goal in eligible_goals:
            next_debit_date = goal.next_debit_date
            
            # Check if debit is due today and the current time is after the scheduled debit time
            if today == next_debit_date and current_time >= goal.debit_time:
                # Check if already debited today
                if goal.last_debit_date == today:
                    continue
                    
                try:
                    with transaction.atomic():
                        # Create transaction for the debit
                        debit_description = f"Automatic contribution to savings goal: {goal.name}"
                        
                        # Create the transaction record
                        transaction_obj = Transaction.objects.create(
                            user=goal.user,
                            amount=goal.monthly_contribution,
                            description=debit_description,
                            date=today,
                            transaction_type='expense'  # Expense because money is being set aside
                        )
                        
                        # Update the goal amount
                        goal.current_amount += goal.monthly_contribution
                        goal.last_debit_date = today
                        
                        # Check if goal is now complete
                        if goal.current_amount >= goal.target_amount:
                            goal.completed = True
                            self.stdout.write(self.style.SUCCESS(
                                f"Goal '{goal.name}' completed with automatic debit!"
                            ))
                        
                        goal.save()
                        debit_count += 1
                        
                        self.stdout.write(
                            f"Processed auto-debit of ₹{goal.monthly_contribution} for goal '{goal.name}'"
                        )
                        
                except Exception as e:
                    self.stdout.write(
                        self.style.ERROR(f"Error processing auto-debit for goal '{goal.name}': {e}")
                    )
        
        self.stdout.write(self.style.SUCCESS(f"Successfully processed {debit_count} automatic debits")) 