from django.utils import timezone
from .models import SavingsGoal
import logging
from datetime import datetime, date
from django.db import transaction
from .models import RecurringTransaction, Transaction, TransactionNotification

logger = logging.getLogger(__name__)

def check_scheduled_debits(force=False, user=None):
    """Check savings goals for scheduled debits, filtered by user if specified"""
    processed_count = 0
    processed_goals = []
    now = timezone.now()
    
    logger.info(f"Starting scheduled debit check at {now}{' (FORCED)' if force else ''}")
    
    # Get all active goals with auto-debit enabled, filtered by user if provided
    active_goals_query = SavingsGoal.objects.filter(
        completed=False,
        auto_debit_enabled=True
    )
    
    # If a specific user is provided, filter by that user
    if user:
        active_goals_query = active_goals_query.filter(user=user)
        logger.info(f"Checking debits for user {user.username} only")
    
    active_goals = active_goals_query
    
    logger.info(f"Found {active_goals.count()} active goals with auto-debit enabled")
    
    for goal in active_goals:
        # Pass the force parameter to the goal's processing method
        success, message = goal.process_scheduled_debit(force=force)
        if success:
            processed_count += 1
            processed_goals.append({
                'id': goal.id,
                'name': goal.name,
                'amount': float(goal.monthly_contribution),
                'message': message
            })
            logger.info(f"Processed debit for goal '{goal.name}' ({goal.id}): {message}")
        else:
            logger.debug(f"Skipped debit for goal '{goal.name}' ({goal.id}): {message}")
    
    logger.info(f"Completed scheduled debit check. Processed {processed_count} debits.")
    return processed_count, processed_goals

def process_recurring_transactions():
    today = date.today()
    processed_count = 0
    
    # Get all active recurring transactions
    recurring_transactions = RecurringTransaction.objects.filter(
        is_active=True,
        start_date__lte=today
    )
    
    for rt in recurring_transactions:
        # Check if it's time to process this transaction
        if rt.should_process_today():
            try:
                with transaction.atomic():
                    # Create the transaction
                    transaction_obj = Transaction.objects.create(
                        user=rt.user,
                        amount=rt.amount,
                        description=f"Recurring {rt.transaction_type}: {rt.name}",
                        date=today,
                        transaction_type=rt.transaction_type
                    )
                    
                    # Create notification for the transaction
                    action_word = "credited" if rt.transaction_type == "income" else "debited"
                    TransactionNotification.objects.create(
                        user=rt.user,
                        transaction=transaction_obj,
                        message=f"Your {rt.name} of ₹{rt.amount} has been {action_word} to your account.",
                        notification_type=rt.transaction_type
                    )
                    
                    # Update last processed date
                    rt.last_processed = today
                    rt.save()
                    
                    processed_count += 1
                    logger.info(f"Processed recurring transaction: {rt.name}")
            except Exception as e:
                logger.error(f"Error processing transaction {rt.name}: {str(e)}")
    
    logger.info(f"Completed processing {processed_count} recurring transactions")
    return processed_count 