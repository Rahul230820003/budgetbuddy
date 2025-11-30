from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import datetime, time, date, timedelta
from django.db.models import Sum
from math import ceil
from dateutil.relativedelta import relativedelta
from django.db import transaction
from django.core.validators import MinValueValidator, MaxValueValidator
import logging

class Transaction(models.Model):
    TRANSACTION_TYPE_CHOICES = [
        ('income', 'Income'),
        ('expense', 'Expense'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    description = models.CharField(max_length=255)
    date = models.DateField(default=timezone.now)
    transaction_type = models.CharField(max_length=10, choices=TRANSACTION_TYPE_CHOICES)
    
    def __str__(self):
        return f"{self.transaction_type}: {self.amount} - {self.description}"

class ExpenseCategory(models.Model):
    name = models.CharField(max_length=100)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    
    def __str__(self):
        return self.name
    
    class Meta:
        verbose_name_plural = "Expense Categories"

class Expense(models.Model):
    transaction = models.OneToOneField(Transaction, on_delete=models.CASCADE, related_name='expense_details')
    category = models.ForeignKey(ExpenseCategory, on_delete=models.SET_NULL, null=True)
    
    def __str__(self):
        return f"{self.transaction.amount} - {self.category.name if self.category else 'Uncategorized'}"

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    reset_word = models.CharField(max_length=100, default='')
    email_verified = models.BooleanField(default=False)
    otp = models.CharField(max_length=6, null=True, blank=True)
    otp_created_at = models.DateTimeField(null=True, blank=True)
    otp_expires_at = models.DateTimeField(null=True, blank=True)
    
    def __str__(self):
        return self.user.username

    def generate_otp(self):
        import random
        import datetime
        
        # Generate a 6-digit OTP
        self.otp = ''.join([str(random.randint(0, 9)) for _ in range(6)])
        self.otp_created_at = timezone.now()
        self.otp_expires_at = self.otp_created_at + datetime.timedelta(minutes=10)
        self.save()
        
        return self.otp

    def verify_otp(self, otp):
        if not self.otp or not self.otp_created_at or not self.otp_expires_at:
            return False
            
        if timezone.now() > self.otp_expires_at:
            return False
            
        if self.otp == otp:
            self.email_verified = True
            self.otp = None
            self.otp_created_at = None
            self.otp_expires_at = None
            self.save()
            return True
            
        return False

class Budget(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='budgets')
    category = models.ForeignKey(ExpenseCategory, on_delete=models.CASCADE, related_name='budgets')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    start_date = models.DateField(default=datetime.now)
    end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.category.name} - ₹{self.amount}"

    @property
    def spent(self):
        # Get the current date
        current_date = datetime.now().date()
        # Get the start of the current month
        current_month_start = current_date.replace(day=1)
        # Get the end of the current month
        if current_date.month == 12:
            next_month = current_date.replace(year=current_date.year + 1, month=1, day=1)
        else:
            next_month = current_date.replace(month=current_date.month + 1, day=1)
        current_month_end = next_month - timedelta(days=1)

        # Calculate total spent in this category for the current month, including future expenses
        total = Expense.objects.filter(
            category=self.category,
            transaction__user=self.user,
            transaction__date__gte=current_month_start,
            transaction__date__lte=current_month_end
        ).aggregate(total=Sum('transaction__amount'))['total'] or 0
        return total

    @property
    def remaining(self):
        return self.amount - self.spent

    @property
    def percentage_used(self):
        if self.amount == 0:
            return 100
        return (self.spent / self.amount) * 100

class SavingsGoal(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='savings_goals')
    name = models.CharField(max_length=100)
    target_amount = models.DecimalField(max_digits=10, decimal_places=2)
    current_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    monthly_contribution = models.DecimalField(max_digits=10, decimal_places=2)
    start_date = models.DateField(default=datetime.now)
    target_date = models.DateField(null=True, blank=True)
    completed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_debit_date = models.DateField(null=True, blank=True)
    last_debit_time = models.TimeField(null=True, blank=True)
    auto_debit_enabled = models.BooleanField(default=True)
    debit_day = models.IntegerField(
        default=1, 
        validators=[MinValueValidator(1), MaxValueValidator(31)],
        help_text="Day of month for automatic debits (1-31, will adjust for shorter months)"
    )
    debit_time = models.TimeField(default=time(0, 0), help_text="Time for automatic debits")
    
    def __str__(self):
        return f"{self.name} - ₹{self.target_amount}"
    
    @property
    def percentage_complete(self):
        if self.target_amount == 0:
            return 100
        return (self.current_amount / self.target_amount) * 100
    
    @property
    def remaining_amount(self):
        return self.target_amount - self.current_amount
    
    @property
    def months_remaining(self):
        if self.monthly_contribution <= 0:
            return None
        return ceil(self.remaining_amount / self.monthly_contribution)
    
    @property
    def estimated_completion_date(self):
        if not self.months_remaining:
            return None
        today = datetime.now().date()
        return today + relativedelta(months=self.months_remaining)

    @property
    def next_debit_date(self):
        """Calculate the next debit date based on selected day, handling month end edge cases"""
        today = datetime.now().date()
        
        # If we already debited this month, calculate for next month
        if self.last_debit_date and self.last_debit_date.month == today.month and self.last_debit_date.year == today.year:
            return self._calculate_future_debit_date(today.replace(day=1) + relativedelta(months=1))
        
        # Calculate this month's debit date
        this_month_target = self._calculate_future_debit_date(today.replace(day=1))
        
        # If today is the debit day, return today
        if today == this_month_target:
            return today
        
        # If today is before this month's debit day, use this month
        if today < this_month_target:
            return this_month_target
        
        # Otherwise, schedule for next month
        return self._calculate_future_debit_date(today.replace(day=1) + relativedelta(months=1))

    def _calculate_future_debit_date(self, first_day_of_month):
        """Helper to calculate actual debit date based on the day selected and month length"""
        # Get the last day of the month
        last_day = (first_day_of_month + relativedelta(months=1, days=-1)).day
        
        # Use the selected day, but cap at the last day of the month if needed
        actual_day = min(self.debit_day, last_day)
        
        # Return the date with the calculated day
        return first_day_of_month.replace(day=actual_day)

    @property
    def days_until_next_debit(self):
        """Calculate days until next automatic debit"""
        if self.completed or not self.auto_debit_enabled:
            return None
        next_date = self.next_debit_date
        today = datetime.now().date()
        return (next_date - today).days

    @property
    def formatted_next_debit(self):
        """Format the next debit date and time in a human-readable format"""
        if self.completed or not self.auto_debit_enabled:
            return None
            
        next_date = self.next_debit_date
        if not next_date:
            return None
            
        # Format with time
        time_str = self.debit_time.strftime('%I:%M %p') if self.debit_time else '12:00 AM'
        return f"{next_date.strftime('%b %d, %Y')} at {time_str}"

    def process_scheduled_debit(self, force=False):
        """Attempt to process a scheduled debit if it's due or forced"""
        logger = logging.getLogger(__name__)
        
        if not self.auto_debit_enabled or self.completed:
            logger.debug(f"Goal {self.id} - Auto-debit not enabled or goal completed")
            return False, "Auto-debit not enabled or goal completed"
        
        now = timezone.now()
        current_date = now.date()
        current_time = now.time()
        
        # If force is true, ALWAYS process regardless of other conditions
        if force:
            logger.info(f"Goal {self.id} - Processing forced debit")
            # Skip all checks when forced
            return self._execute_debit(current_date, current_time, "Manually forced debit")
        
        # Regular checks for non-forced debits
        # If we already debited today, don't process again
        if self.last_debit_date == current_date:
            logger.debug(f"Goal {self.id} - Already debited today")
            return False, "Already debited today"
        
        # Calculate the debit date for this month
        this_month_debit_date = self._calculate_future_debit_date(current_date.replace(day=1))
        
        # Check if today is the scheduled debit day
        if current_date == this_month_debit_date:
            # On the scheduled day, check if we've reached the target time
            if current_time >= self.debit_time:
                logger.info(f"Goal {self.id} - Processing regular scheduled debit")
                return self._execute_debit(current_date, current_time, "Regular scheduled debit")
            else:
                logger.debug(f"Goal {self.id} - Waiting for scheduled time {self.debit_time.strftime('%H:%M')}")
                return False, f"Waiting for scheduled time {self.debit_time.strftime('%H:%M')}"
        elif current_date > this_month_debit_date and current_date.month == this_month_debit_date.month:
            # If we're past the debit day but still in the same month, process it immediately
            logger.info(f"Goal {self.id} - Catching up on missed debit")
            return self._execute_debit(current_date, current_time, "Catching up on missed debit")
        
        logger.debug(f"Goal {self.id} - Not scheduled debit day (scheduled for {this_month_debit_date})")
        return False, f"Not scheduled debit day (scheduled for {this_month_debit_date})"

    def _execute_debit(self, current_date, current_time, status_message="Regular debit"):
        """Execute the actual debit transaction"""
        logger = logging.getLogger(__name__)
        
        logger.info(f"Executing debit for goal {self.name} ({self.id}): {status_message}")
        
        try:
            with transaction.atomic():
                # Create transaction for the debit
                transaction_obj = Transaction.objects.create(
                    user=self.user,
                    amount=self.monthly_contribution,
                    description=f"Automatic contribution to savings goal: {self.name}",
                    date=current_date,
                    transaction_type='expense'  # Expense because money is being set aside
                )
                
                # Update the goal amount
                self.current_amount += self.monthly_contribution
                self.last_debit_date = current_date
                self.last_debit_time = current_time
                
                # Check if goal is now complete
                if self.current_amount >= self.target_amount:
                    self.completed = True
                
                self.save()
                logger.info(f"Successfully processed debit for goal {self.name}: {self.monthly_contribution}")
                return True, f"Successfully debited ₹{self.monthly_contribution} ({status_message})"
                
        except Exception as e:
            logger.error(f"Error processing debit for goal {self.name}: {str(e)}")
            return False, f"Error processing debit: {str(e)}"

    def _execute_manual_debit(self, current_date, current_time):
        """Execute a manually forced debit (when already debited once today)"""
        try:
            with transaction.atomic():
                # Create transaction for the manual contribution
                transaction_obj = Transaction.objects.create(
                    user=self.user,
                    amount=self.monthly_contribution,
                    description=f"Manual contribution to savings goal: {self.name}",
                    date=current_date,
                    transaction_type='expense'  # Expense because money is being set aside
                )
                
                # Update the goal amount (but don't update last_debit_date)
                self.current_amount += self.monthly_contribution
                
                # Check if goal is now complete
                if self.current_amount >= self.target_amount:
                    self.completed = True
                
                self.save()
                return True, f"Successfully added ₹{self.monthly_contribution} (additional manual debit)"
                
        except Exception as e:
            return False, f"Error processing manual debit: {str(e)}"

class RecurringTransaction(models.Model):
    TRANSACTION_TYPES = [
        ('income', 'Income'),
        ('expense', 'Expense'),
    ]
    
    FREQUENCY_CHOICES = [
        ('monthly', 'Monthly'),
        ('quarterly', 'Quarterly'),
        ('yearly', 'Yearly'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]

    user = models.ForeignKey('auth.User', on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    transaction_type = models.CharField(max_length=7, choices=TRANSACTION_TYPES)
    frequency = models.CharField(max_length=10, choices=FREQUENCY_CHOICES)
    start_date = models.DateField()
    day_of_month = models.IntegerField(help_text="Day of the month (1-31)")
    scheduled_time = models.TimeField(default='00:00')
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    last_processed = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['day_of_month', 'name']

    def __str__(self):
        return f"{self.name} - {self.amount} ({self.get_frequency_display()})"

    def should_process_today(self):
        today = date.today()
        now = datetime.now().time()
        
        # If it's already been processed this month
        if self.last_processed and self.last_processed.month == today.month:
            return False
        
        # Check if today is the processing day
        if today.day != self.day_of_month:
            return False
            
        # Check if it's time to process
        if now < self.scheduled_time:
            return False
        
        # For monthly transactions
        if self.frequency == 'monthly':
            return True
        
        # For quarterly transactions
        if self.frequency == 'quarterly':
            months_since_start = (today.year - self.start_date.year) * 12 + today.month - self.start_date.month
            return months_since_start % 3 == 0
        
        # For yearly transactions
        if self.frequency == 'yearly':
            return today.month == self.start_date.month
        
        return False

    def process_transaction(self):
        """Process the recurring transaction and create a new transaction record"""
        today = date.today()
        
        try:
            with transaction.atomic():
                # Create the transaction
                transaction_obj = Transaction.objects.create(
                    user=self.user,
                    amount=self.amount,
                    description=f"Recurring {self.transaction_type}: {self.name}",
                    date=today,
                    transaction_type=self.transaction_type
                )
                
                # Create notification
                action_word = "credited" if self.transaction_type == "income" else "debited"
                TransactionNotification.objects.create(
                    user=self.user,
                    transaction=transaction_obj,
                    message=f"Your {self.name} of ₹{self.amount} has been {action_word} to your account.",
                    notification_type=self.transaction_type
                )
                
                # Update last processed date and status
                self.last_processed = today
                self.status = 'completed'
                self.save()
                
                return True, "Transaction processed successfully"
        except Exception as e:
            self.status = 'failed'
            self.save()
            return False, str(e)

class TransactionNotification(models.Model):
    NOTIFICATION_TYPES = [
        ('income', 'Income'),
        ('expense', 'Expense'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    transaction = models.ForeignKey(Transaction, on_delete=models.CASCADE)
    message = models.CharField(max_length=255)
    notification_type = models.CharField(max_length=10, choices=NOTIFICATION_TYPES)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.notification_type}: {self.message}"

# Remove or comment out the Receipt model class

class Discussion(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    likes = models.ManyToManyField(User, related_name='liked_discussions', blank=True)
    
    def __str__(self):
        return self.title
    
    class Meta:
        ordering = ['-created_at']

class Comment(models.Model):
    discussion = models.ForeignKey(Discussion, on_delete=models.CASCADE, related_name='comments')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f'Comment by {self.user.username} on {self.discussion.title}'
    
    class Meta:
        ordering = ['created_at']
