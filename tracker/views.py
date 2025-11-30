from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.db.models import Sum, Count
from django.http import HttpResponse, JsonResponse
import csv
from datetime import datetime, time
from .models import Transaction, ExpenseCategory, Expense, UserProfile, Budget, SavingsGoal, RecurringTransaction, TransactionNotification, Discussion, Comment
from django.contrib.auth.models import User
from django.core.serializers.json import DjangoJSONEncoder
import json
from django.db.models.functions import TruncMonth
from django.shortcuts import render, redirect
from django.contrib import messages
import decimal
from django.utils import timezone
from decimal import Decimal
import logging
import calendar
from datetime import timedelta
from datetime import date
from dateutil.relativedelta import relativedelta
from django.db.models import Avg
from .recommendations import FinancialRecommendationEngine
import math
from .utils import send_otp_email

def landing_page(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'tracker/landing.html')

def register_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        email = request.POST.get('email')
        password = request.POST.get('password')
        confirm_password = request.POST.get('confirm_password')
        reset_word = request.POST.get('reset_word')
        
        if password != confirm_password:
            messages.error(request, 'Passwords do not match')
            return redirect('register')
        
        if User.objects.filter(username=username).exists():
            messages.error(request, 'Username already exists')
            return redirect('register')
            
        if User.objects.filter(email=email).exists():
            messages.error(request, 'Email already exists')
            return redirect('register')
            
        user = User.objects.create_user(username=username, email=email, password=password)
        profile = UserProfile.objects.create(user=user, reset_word=reset_word)
        
        # Generate and send OTP
        otp = profile.generate_otp()
        send_otp_email(user, otp)
        
        # Create default expense categories for the user
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
        for category in default_categories:
            ExpenseCategory.objects.create(name=category, user=user)
            
        messages.success(request, 'Account created successfully. Please check your email for verification code.')
        return redirect('verify_otp')
        
    return render(request, 'tracker/register.html')

def verify_otp(request):
    if not request.user.is_authenticated:
        return redirect('login')
        
    profile = request.user.userprofile
    
    if profile.email_verified:
        return redirect('dashboard')
        
    if request.method == 'POST':
        otp = request.POST.get('otp')
        if profile.verify_otp(otp):
            messages.success(request, 'Email verified successfully!')
            return redirect('dashboard')
        else:
            messages.error(request, 'Invalid or expired verification code.')
            
    return render(request, 'tracker/verify_otp.html')

def resend_otp(request):
    if not request.user.is_authenticated:
        return redirect('login')
        
    profile = request.user.userprofile
    
    if profile.email_verified:
        return redirect('dashboard')
        
    # Generate and send new OTP
    otp = profile.generate_otp()
    send_otp_email(request.user, otp)
    
    messages.success(request, 'New verification code has been sent to your email.')
    return redirect('verify_otp')

def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            if not user.userprofile.email_verified:
                # Generate and send new OTP if email is not verified
                otp = user.userprofile.generate_otp()
                send_otp_email(user, otp)
                login(request, user)
                messages.warning(request, 'Please verify your email address.')
                return redirect('verify_otp')
            else:
                login(request, user)
                return redirect('dashboard')
        else:
            messages.error(request, 'Invalid username or password')
            
    return render(request, 'tracker/login.html')

def logout_view(request):
    logout(request)
    return redirect('landing_page')

@login_required
def dashboard(request):
    # Get total income
    total_income = Transaction.objects.filter(
        user=request.user,
        transaction_type='income'
    ).aggregate(total=Sum('amount'))['total'] or 0

    # Get total expenses
    total_expenses = Transaction.objects.filter(
        user=request.user,
        transaction_type='expense'
    ).aggregate(total=Sum('amount'))['total'] or 0

    # Calculate balance
    balance = total_income - total_expenses

    # Get recent transactions
    recent_transactions = Transaction.objects.filter(
        user=request.user
    ).order_by('-date')[:5]

    # Get budgets
    budgets = Budget.objects.filter(user=request.user)

    # Get savings goals
    savings_goals = SavingsGoal.objects.filter(user=request.user)

    # Get upcoming debits
    upcoming_debits = []
    for goal in savings_goals:
        if goal.auto_debit_enabled and not goal.completed:
            next_debit = goal.next_debit_date
            if next_debit:
                days_until = (next_debit - timezone.now().date()).days
                if 0 <= days_until <= 7:  # Show debits in next 7 days
                    upcoming_debits.append({
                        'goal': goal,
                        'date': next_debit,
                        'days_until': days_until
                    })

    # Get personalized recommendations
    recommendation_engine = FinancialRecommendationEngine(request.user)
    recommendations = recommendation_engine.analyze_financial_health()
    
    # Only show high-confidence recommendations on dashboard
    dashboard_recommendations = [r for r in recommendations if r['confidence'] >= 0.85][:3]
    
    # Get recent notifications
    recent_notifications = TransactionNotification.objects.filter(
        user=request.user,
        is_read=False
    ).order_by('-created_at')[:5]
    
    # Get upcoming recurring transactions for the next 2 days
    today = timezone.now().date()
    tomorrow = today + timedelta(days=1)
    
    upcoming_recurring = []
    pending_transactions = []
    recurring_transactions = RecurringTransaction.objects.filter(
        user=request.user,
        is_active=True
    )
    
    for rt in recurring_transactions:
        # Calculate next occurrence
        if rt.day_of_month == today.day or rt.day_of_month == tomorrow.day:
            # Check if it hasn't been processed this month
            if not rt.last_processed or rt.last_processed.month != today.month:
                if rt.status == 'pending':
                    pending_transactions.append(rt)
                else:
                    upcoming_recurring.append({
                        'name': rt.name,
                        'amount': rt.amount,
                        'type': rt.transaction_type,
                        'date': tomorrow if rt.day_of_month == tomorrow.day else today
                    })
    
    context = {
        'total_income': total_income,
        'total_expenses': total_expenses,
        'balance': balance,
        'recent_transactions': recent_transactions,
        'budgets': budgets,
        'savings_goals': savings_goals,
        'upcoming_debits': upcoming_debits,
        'now': timezone.now(),
        'recommendations': dashboard_recommendations,
        'notifications': recent_notifications,
        'upcoming_recurring': upcoming_recurring,
        'pending_transactions': pending_transactions,
    }
    
    return render(request, 'tracker/dashboard.html', context)

@login_required
def add_income(request):
    if request.method == 'POST':
        amount = request.POST.get('amount')
        description = request.POST.get('description')
        date = request.POST.get('date')
        
        if not date:
            date = datetime.now().date()
        
        transaction = Transaction.objects.create(
            user=request.user,
            amount=amount,
            description=description,
            date=date,
            transaction_type='income'
        )
        
        # Create notification for the income
        TransactionNotification.objects.create(
            user=request.user,
            transaction=transaction,
            message=f"Your {description} of ₹{amount} has been credited to your account.",
            notification_type='income'
        )
        
        messages.success(request, 'Income added successfully')
        return redirect('dashboard')
        
    return render(request, 'tracker/add_income.html')

@login_required
def add_expense(request):
    categories = ExpenseCategory.objects.filter(user=request.user)
    
    if request.method == 'POST':
        amount = request.POST.get('amount')
        description = request.POST.get('description')
        date = request.POST.get('date')
        category_id = request.POST.get('category')
        
        if not date:
            date = datetime.now().date()
            
        transaction = Transaction.objects.create(
            user=request.user,
            amount=amount,
            description=description,
            date=date,
            transaction_type='expense'
        )
        
        # Create notification for the expense
        TransactionNotification.objects.create(
            user=request.user,
            transaction=transaction,
            message=f"Your {description} of ₹{amount} has been debited from your account.",
            notification_type='expense'
        )
        
        category = None
        if category_id:
            category = get_object_or_404(ExpenseCategory, id=category_id, user=request.user)
            
        Expense.objects.create(
            transaction=transaction,
            category=category
        )
        
        # Check if this expense exceeds any budget
        if category:
            budget = Budget.objects.filter(user=request.user, category=category, is_active=True).first()
            if budget:
                spent = budget.spent
                if spent > budget.amount:
                    messages.warning(request, f'You have exceeded your budget for {category.name}! Budget: ₹{budget.amount}, Spent: ₹{spent}')
                elif spent >= (budget.amount * decimal.Decimal('0.8')):
                    messages.warning(request, f'You are approaching your budget limit for {category.name}! Budget: ₹{budget.amount}, Spent: ₹{spent}')
        
        messages.success(request, 'Expense added successfully')
        return redirect('dashboard')
        
    context = {
        'categories': categories
    }
    
    return render(request, 'tracker/add_expense.html', context)

@login_required
def transactions(request):
    transaction_type = request.GET.get('type', 'all')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    
    # Get all transactions ordered by date ascending for balance calculation
    all_transactions = Transaction.objects.filter(
        user=request.user
    ).order_by('date', 'id')
    
    # Calculate running balance for all transactions
    balance_dict = {}
    running_balance = 0
    for transaction in all_transactions:
        if transaction.transaction_type == 'income':
            running_balance += transaction.amount
        else:
            running_balance -= transaction.amount
        balance_dict[transaction.id] = running_balance
    
    # Get filtered transactions for display in descending order
    filtered_transactions = Transaction.objects.filter(
        user=request.user
    ).order_by('-date', '-id')  # Changed to descending order
    
    if transaction_type == 'income':
        filtered_transactions = filtered_transactions.filter(transaction_type='income')
    elif transaction_type == 'expense':
        filtered_transactions = filtered_transactions.filter(transaction_type='expense')
        
    if start_date:
        filtered_transactions = filtered_transactions.filter(date__gte=start_date)
        
    if end_date:
        filtered_transactions = filtered_transactions.filter(date__lte=end_date)
    
    # Prepare transactions with their respective balances
    transactions_with_balance = []
    for transaction in filtered_transactions:
        transactions_with_balance.append({
            'transaction': transaction,
            'balance': balance_dict[transaction.id]
        })
    
    context = {
        'transactions': transactions_with_balance,
        'transaction_type': transaction_type,
        'start_date': start_date,
        'end_date': end_date
    }
    
    return render(request, 'tracker/transactions.html', context)

@login_required
def download_transactions(request):
    transaction_type = request.GET.get('type', 'all')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    
    # Get all transactions ordered by date ascending for balance calculation
    all_transactions = Transaction.objects.filter(
        user=request.user
    ).order_by('date', 'id')
    
    # Calculate running balance for all transactions
    balance_dict = {}
    running_balance = 0
    for transaction in all_transactions:
        if transaction.transaction_type == 'income':
            running_balance += transaction.amount
        else:
            running_balance -= transaction.amount
        balance_dict[transaction.id] = running_balance
    
    # Get filtered transactions for Excel in ascending order
    transactions = Transaction.objects.filter(
        user=request.user
    ).order_by('date', 'id')  # Changed to ascending order
    
    if transaction_type == 'income':
        transactions = transactions.filter(transaction_type='income')
        filename = 'income'
    elif transaction_type == 'expense':
        transactions = transactions.filter(transaction_type='expense')
        filename = 'expenses'
    else:
        filename = 'transactions'
        
    # Only apply date filters if valid dates are provided
    if start_date and start_date.strip():
        try:
            datetime.strptime(start_date, '%Y-%m-%d')  # Validate date format
            transactions = transactions.filter(date__gte=start_date)
            filename += f'_from_{start_date}'
        except ValueError:
            pass  # Skip invalid date
        
    if end_date and end_date.strip():
        try:
            datetime.strptime(end_date, '%Y-%m-%d')  # Validate date format
            transactions = transactions.filter(date__lte=end_date)
            filename += f'_to_{end_date}'
        except ValueError:
            pass  # Skip invalid date
    
    response = HttpResponse(
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f'attachment; filename="{filename}.xlsx"'},
    )
    
    import xlsxwriter
    workbook = xlsxwriter.Workbook(response, {'in_memory': True})
    worksheet = workbook.add_worksheet()
    
    # Add headers
    headers = ['Date', 'Type', 'Description', 'Amount', 'Balance']
    for col, header in enumerate(headers):
        worksheet.write(0, col, header)
    
    # Add data
    date_format = workbook.add_format({'num_format': 'dd-mm-yyyy'})
    
    for row, transaction in enumerate(transactions, start=1):
        # Format amount with sign
        amount_str = f"{'-' if transaction.transaction_type == 'expense' else '+'}{transaction.amount}"
        
        # Convert date string to datetime object for Excel
        date_obj = transaction.date
        
        worksheet.write_datetime(row, 0, date_obj, date_format)  # Date with format
        worksheet.write(row, 1, transaction.transaction_type)  # Type
        worksheet.write(row, 2, transaction.description)  # Description
        worksheet.write(row, 3, amount_str)  # Amount
        worksheet.write(row, 4, balance_dict[transaction.id])  # Balance
    
    # Set column widths
    worksheet.set_column(0, 0, 12)  # Date
    worksheet.set_column(1, 1, 10)  # Type
    worksheet.set_column(2, 2, 30)  # Description
    worksheet.set_column(3, 3, 12)  # Amount
    worksheet.set_column(4, 4, 12)  # Balance
    
    workbook.close()
    return response

@login_required
def profile(request):
    return render(request, 'tracker/profile.html')

@login_required
def update_email(request):
    if request.method == 'POST':
        email = request.POST.get('email')
        
        if User.objects.filter(email=email).exclude(id=request.user.id).exists():
            messages.error(request, 'Email already exists')
            return redirect('update_email')
            
        request.user.email = email
        request.user.save()
        
        messages.success(request, 'Email updated successfully')
        return redirect('profile')
        
    return render(request, 'tracker/update_email.html')

@login_required
def change_password(request):
    if request.method == 'POST':
        current_password = request.POST.get('current_password')
        new_password = request.POST.get('new_password')
        confirm_password = request.POST.get('confirm_password')
        
        if not request.user.check_password(current_password):
            messages.error(request, 'Current password is incorrect')
            return redirect('change_password')
            
        if new_password != confirm_password:
            messages.error(request, 'Passwords do not match')
            return redirect('change_password')
            
        request.user.set_password(new_password)
        request.user.save()
        
        messages.success(request, 'Password changed successfully. Please log in again.')
        return redirect('login')
        
    return render(request, 'tracker/change_password.html')

def reset_password(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        reset_word = request.POST.get('reset_word')
        new_password = request.POST.get('new_password')
        confirm_password = request.POST.get('confirm_password')
        
        try:
            user = User.objects.get(username=username)
            profile = UserProfile.objects.get(user=user)
            
            if profile.reset_word != reset_word:
                messages.error(request, 'Invalid reset word')
                return redirect('reset_password')
                
            if new_password != confirm_password:
                messages.error(request, 'Passwords do not match')
                return redirect('reset_password')
                
            user.set_password(new_password)
            user.save()
            
            messages.success(request, 'Password reset successfully. Please log in.')
            return redirect('login')
            
        except (User.DoesNotExist, UserProfile.DoesNotExist):
            messages.error(request, 'User not found')
            return redirect('reset_password')
            
    return render(request, 'tracker/reset_password.html')


def feedback_view(request):
    if request.method == 'POST':
        # Process the feedback form
        name = request.POST.get('name')
        email = request.POST.get('email')
        feedback_type = request.POST.get('feedback_type')
        message = request.POST.get('message')
        rating = request.POST.get('rating')
        
        # Here you can add code to save the feedback to your database
        # For now, we'll just show a success message
        messages.success(request, 'Thank you for your feedback!')
        return redirect('landing_page')
        
    return render(request, 'tracker/feedback.html')

@login_required
def budget(request):
    # Get user's expense categories
    categories = ExpenseCategory.objects.filter(user=request.user)
    
    # Get existing budgets
    budgets = Budget.objects.filter(user=request.user, is_active=True)
    
    if request.method == 'POST':
        category_id = request.POST.get('category')
        amount = request.POST.get('amount')
        
        if not category_id or not amount:
            messages.error(request, 'Please select a category and enter an amount')
            return redirect('budget')
            
        try:
            category = ExpenseCategory.objects.get(id=category_id, user=request.user)
            
            # Check if budget already exists for this category
            existing_budget = Budget.objects.filter(user=request.user, category=category, is_active=True).first()
            
            if existing_budget:
                # Update existing budget
                existing_budget.amount = amount
                existing_budget.updated_at = datetime.now()
                existing_budget.save()
                messages.success(request, f'Budget for {category.name} updated to ₹{amount}')
            else:
                # Create new budget
                Budget.objects.create(
                    user=request.user,
                    category=category,
                    amount=amount
                )
                messages.success(request, f'Budget for {category.name} set to ₹{amount}')
                
        except ExpenseCategory.DoesNotExist:
            messages.error(request, 'Category not found')
            
        return redirect('budget')
    
    # For each budget, calculate how much has been spent
    for budget in budgets:
        budget.alert_class = ""
        percentage = budget.percentage_used
        
        if percentage >= 100:
            budget.alert_class = "bg-red-100 border-red-500 text-red-700"
        elif percentage >= 80:
            budget.alert_class = "bg-yellow-100 border-yellow-500 text-yellow-700"
    
    context = {
        'categories': categories,
        'budgets': budgets
    }
    
    return render(request, 'tracker/budget.html', context)

@login_required
def edit_budget(request, budget_id):
    budget = get_object_or_404(Budget, id=budget_id, user=request.user)
    
    if request.method == 'POST':
        amount = request.POST.get('amount')
        if amount:
            budget.amount = amount
            budget.save()
            messages.success(request, f'Budget for {budget.category.name} updated to ₹{amount}')
        else:
            messages.error(request, 'Please enter an amount')
            
    return redirect('budget')

@login_required
def delete_budget(request, budget_id):
    budget = get_object_or_404(Budget, id=budget_id, user=request.user)
    
    if request.method == 'POST':
        category_name = budget.category.name
        budget.delete()
        messages.success(request, f'Budget for {category_name} deleted')
        
    return redirect('budget')

@login_required
def savings_goals(request):
    goals = SavingsGoal.objects.filter(user=request.user).order_by('completed', 'target_date')
    
    if request.method == 'POST':
        name = request.POST.get('name')
        target_amount = request.POST.get('target_amount')
        monthly_contribution = request.POST.get('monthly_contribution')
        target_date = request.POST.get('target_date')
        debit_time = request.POST.get('debit_time', '00:00')
        debit_day = request.POST.get('debit_day', '1')  # Get the debit day
        
        if not name or not target_amount or not monthly_contribution:
            messages.error(request, 'Please fill in all required fields')
            return redirect('savings_goals')
        
        # Parse the time    
        try:
            hour, minute = map(int, debit_time.split(':'))
            time_obj = time(hour, minute)
        except (ValueError, TypeError):
            time_obj = time(0, 0)
            
        # Parse the debit day
        try:
            day = int(debit_day)
            debit_day_int = min(max(day, 1), 31)  # Allow between 1-31
        except (ValueError, TypeError):
            debit_day_int = 1
            
        SavingsGoal.objects.create(
            user=request.user,
            name=name,
            target_amount=target_amount,
            monthly_contribution=monthly_contribution,
            target_date=target_date if target_date else None,
            debit_time=time_obj,
            debit_day=debit_day_int
        )
        
        messages.success(request, f'Savings goal "{name}" created successfully')
        return redirect('savings_goals')
    
    # Initialize analytics data
    active_goals = goals.filter(completed=False)
    active_goals_count = active_goals.count()
    total_saved = sum(goal.current_amount for goal in goals)
    total_monthly = sum(goal.monthly_contribution for goal in active_goals)
    total_remaining = sum(goal.remaining_amount for goal in active_goals)

    # Calculate monthly expenses for emergency fund
    monthly_expenses = Transaction.objects.filter(
        user=request.user,
        transaction_type='expense',
        date__gte=timezone.now().date() - timedelta(days=30)
    ).aggregate(total=Sum('amount'))['total'] or 0

    # Get or create lifetime savings goals
    emergency_fund = goals.filter(name='Family Emergency Fund').first()
    education_fund = goals.filter(name="Children's Education").first()
    retirement_fund = goals.filter(name='Retirement Fund').first()

    # Calculate emergency fund data
    emergency_fund_target = monthly_expenses * 6  # 6 months of expenses
    emergency_fund_current = emergency_fund.current_amount if emergency_fund else 0
    emergency_fund_percentage = min(100, (emergency_fund_current / emergency_fund_target * 100) if emergency_fund_target > 0 else 0)
    emergency_fund_id = emergency_fund.id if emergency_fund else None

    # Calculate education fund data
    education_fund_target = education_fund.target_amount if education_fund else 5000000  # Default 50L
    education_fund_current = education_fund.current_amount if education_fund else 0
    education_fund_percentage = min(100, (education_fund_current / education_fund_target * 100) if education_fund_target > 0 else 0)
    education_fund_id = education_fund.id if education_fund else None

    # Calculate retirement fund data
    retirement_fund_target = retirement_fund.target_amount if retirement_fund else 10000000  # Default 1Cr
    retirement_fund_current = retirement_fund.current_amount if retirement_fund else 0
    retirement_fund_percentage = min(100, (retirement_fund_current / retirement_fund_target * 100) if retirement_fund_target > 0 else 0)
    retirement_fund_id = retirement_fund.id if retirement_fund else None

    # Prepare timeline data
    timeline_data = {
        'labels': [],
        'datasets': []
    }
    try:
        timeline_data = prepare_timeline_data(goals)
    except Exception as e:
        print(f"Error preparing timeline data: {e}")

    # Prepare forecast data
    forecast_data = {
        'labels': [],
        'months': []
    }
    try:
        forecast_data = prepare_forecast_data(active_goals)
    except Exception as e:
        print(f"Error preparing forecast data: {e}")

    # Prepare calendar data
    calendar_data = {}
    try:
        calendar_data = prepare_calendar_data(active_goals)
    except Exception as e:
        print(f"Error preparing calendar data: {e}")

    # Prepare goal data for charts
    goal_names = [goal.name for goal in active_goals]
    current_amounts = [float(goal.current_amount) for goal in active_goals]
    remaining_amounts = [float(goal.remaining_amount) for goal in active_goals]

    context = {
        'goals': goals,
        'range_1_31': range(1, 32),
        'now': timezone.now(),
        'goal_names': json.dumps(goal_names),
        'current_amounts': json.dumps(current_amounts),
        'remaining_amounts': json.dumps(remaining_amounts),
        'active_goals_count': active_goals_count,
        'total_saved': total_saved,
        'total_monthly': total_monthly,
        'total_remaining': total_remaining,
        'timeline_labels': json.dumps(timeline_data.get('labels', [])),
        'timeline_datasets': json.dumps(timeline_data.get('datasets', [])),
        'forecast_labels': json.dumps(forecast_data.get('labels', [])),
        'forecast_months': json.dumps(forecast_data.get('months', [])),
        'calendar_data': json.dumps(calendar_data),
        # Add lifetime savings goals data
        'monthly_expenses': monthly_expenses,
        'emergency_fund_target': emergency_fund_target,
        'emergency_fund_current': emergency_fund_current,
        'emergency_fund_percentage': emergency_fund_percentage,
        'emergency_fund_id': emergency_fund_id,
        'education_fund_target': education_fund_target,
        'education_fund_current': education_fund_current,
        'education_fund_percentage': education_fund_percentage,
        'education_fund_id': education_fund_id,
        'retirement_fund_target': retirement_fund_target,
        'retirement_fund_current': retirement_fund_current,
        'retirement_fund_percentage': retirement_fund_percentage,
        'retirement_fund_id': retirement_fund_id,
    }
    
    return render(request, 'tracker/savings_goals.html', context)

def prepare_timeline_data(goals):
    """Prepare timeline data for savings growth chart"""
    # Get the last 6 months of data
    end_date = timezone.now().date()
    start_date = end_date - timedelta(days=180)
    
    # Generate monthly labels
    labels = []
    current_date = start_date
    while current_date <= end_date:
        labels.append(current_date.strftime('%b %Y'))
        current_date = (current_date.replace(day=1) + timedelta(days=32)).replace(day=1)
    
    # Create datasets for each goal
    datasets = []
    for goal in goals:
        data = []
        current_date = start_date
        while current_date <= end_date:
            # You'll need to implement logic to get the amount saved up to this date
            # This is a placeholder - replace with actual historical data
            amount = float(goal.current_amount)  # Replace with historical data
            data.append(amount)
            current_date = (current_date.replace(day=1) + timedelta(days=32)).replace(day=1)
        
        datasets.append({
            'label': goal.name,
            'data': data,
            'borderColor': get_color_for_index(len(datasets)),
            'backgroundColor': get_color_for_index(len(datasets), 0.1),
            'fill': True
        })
    
    return {
        'labels': labels,
        'datasets': datasets
    }

def prepare_forecast_data(goals):
    """Prepare forecast data for completion chart"""
    labels = []
    months = []
    
    for goal in goals:
        if not goal.completed:
            labels.append(goal.name)
            # Calculate months to completion based on monthly contribution
            if goal.monthly_contribution > 0:
                months_left = math.ceil(float(goal.remaining_amount) / float(goal.monthly_contribution))
            else:
                months_left = 0
            months.append(months_left)
    
    return {
        'labels': labels,
        'months': months
    }

def prepare_calendar_data(goals):
    """Prepare calendar data for auto-debit display"""
    calendar_data = {}
    today = timezone.now().date()
    
    # Get data for current and next 3 months
    for month_offset in range(4):
        current_date = today + relativedelta(months=month_offset)
        month_start = current_date.replace(day=1)
        month_end = (month_start + relativedelta(months=1) - timedelta(days=1))
        
        for goal in goals:
            if goal.auto_debit_enabled and not goal.completed:
                debit_day = min(goal.debit_day, calendar.monthrange(current_date.year, current_date.month)[1])
                debit_date = current_date.replace(day=debit_day)
                
                if month_start <= debit_date <= month_end:
                    date_str = debit_date.strftime('%Y-%m-%d')
                    if date_str not in calendar_data:
                        calendar_data[date_str] = {
                            'autoDebits': [],
                            'manualDebits': [],
                            'transfers': []
                        }
                    
                    calendar_data[date_str]['autoDebits'].append({
                        'goal': goal.name,
                        'amount': float(goal.monthly_contribution),
                        'description': f"Auto-debit for {goal.name}"
                    })
    
    return calendar_data

@login_required
def edit_savings_goal(request, goal_id):
    goal = get_object_or_404(SavingsGoal, id=goal_id, user=request.user)
    add_funds_focus = request.GET.get('add_funds') == 'true'
    
    if request.method == 'POST':
        if 'update_goal' in request.POST:
            name = request.POST.get('name')
            target_amount = request.POST.get('target_amount')
            monthly_contribution = request.POST.get('monthly_contribution')
            target_date = request.POST.get('target_date')
            auto_debit_enabled = request.POST.get('auto_debit_enabled') == 'on'
            debit_time = request.POST.get('debit_time')
            debit_day = request.POST.get('debit_day', '1')  # Get the debit day
            
            if name and target_amount and monthly_contribution:
                goal.name = name
                goal.target_amount = target_amount
                goal.monthly_contribution = monthly_contribution
                goal.target_date = target_date if target_date else None
                goal.auto_debit_enabled = auto_debit_enabled
                
                # Set debit time if provided
                if debit_time:
                    hour, minute = map(int, debit_time.split(':'))
                    goal.debit_time = time(hour, minute)
                
                # Set debit day (allow 1-31)
                try:
                    day = int(debit_day)
                    goal.debit_day = min(max(day, 1), 31)  # Allow between 1-31
                except (ValueError, TypeError):
                    goal.debit_day = 1
                    
                goal.save()
                messages.success(request, f'Savings goal "{name}" updated successfully')
            else:
                messages.error(request, 'Please fill in all required fields')
        
        elif 'add_funds' in request.POST:
            amount = request.POST.get('amount')
            if amount:
                goal.current_amount += Decimal(amount)
                if goal.current_amount >= goal.target_amount:
                    goal.completed = True
                goal.save()
                
                # Create a transaction record for this contribution
                transaction = Transaction.objects.create(
                    user=request.user,
                    amount=amount,
                    description=f"Contribution to savings goal: {goal.name}",
                    date=timezone.now(),
                    transaction_type='expense'  # It's an expense because money is being set aside
                )
                
                messages.success(request, f'Added ₹{amount} to your savings goal')
            else:
                messages.error(request, 'Please enter an amount')
                
        elif 'complete_goal' in request.POST:
            goal.completed = True
            goal.save()
            messages.success(request, f'Congratulations on completing your savings goal!')
        
        return redirect('savings_goals')
    
    context = {
        'goal': goal,
        'add_funds_focus': add_funds_focus,
        'range_1_31': range(1, 32)  # Modified to show days 1-31
    }
    
    return render(request, 'tracker/edit_savings_goal.html', context)

@login_required
def delete_savings_goal(request, goal_id):
    goal = get_object_or_404(SavingsGoal, id=goal_id, user=request.user)
    
    if request.method == 'POST':
        goal_name = goal.name
        goal.delete()
        messages.success(request, f'Savings goal "{goal_name}" deleted')
    
    return redirect('savings_goals')

@login_required
def check_debits(request, force=False):
    """Manual endpoint to check for scheduled debits with option to force process"""
    from .tasks import check_scheduled_debits  # Import here to avoid circular imports
    import logging
    
    logger = logging.getLogger(__name__)
    
    # Get the force parameter from URL parameter or GET parameter
    force_process = force or request.GET.get('force', 'false').lower() == 'true'
    
    logger.info(f"Starting check_debits view for user {request.user.username} with force={force_process}")
    
    # Store original timezone function for restoration later
    from django.utils import timezone
    import datetime
    original_now = timezone.now
    
    try:
        if force_process:
            # Create a better custom now function that appears to be in the future
            def forced_now():
                real_now = original_now()
                # Make it appear to be after the scheduled time
                return real_now.replace(hour=23, minute=59, second=59)
            
            # Replace timezone.now with our custom function temporarily
            timezone.now = forced_now
            logger.info("Using forced time for processing")
        
        # Process the debits with the force parameter, but only for the current user
        debit_count, processed_goals = check_scheduled_debits(force=force_process, user=request.user)
        
        if debit_count > 0:
            # Show success message with details
            total_amount = sum(goal['amount'] for goal in processed_goals)
            goal_names = ", ".join([goal['name'] for goal in processed_goals])
            success_msg = (f"Successfully processed {debit_count} automatic debit(s) totaling ₹{total_amount:.2f} "
                          f"for: {goal_names}. Your account balance has been updated.")
            messages.success(request, success_msg)
            logger.info(success_msg)
        else:
            # Query goals to check what's happening
            from .models import SavingsGoal
            today = datetime.datetime.now().date()
            
            # Check only the current user's goals
            goals_due_today = list(SavingsGoal.objects.filter(
                user=request.user,
                completed=False,
                auto_debit_enabled=True
            ))
            
            if goals_due_today:
                # Debug info
                debug_info = []
                for goal in goals_due_today:
                    debit_date = goal.next_debit_date
                    days_until = getattr(goal, 'days_until_next_debit', None)
                    already_debited = goal.last_debit_date == today
                    debug_info.append(f"{goal.name}: due_date={debit_date}, days_until={days_until}, already_debited={already_debited}")
                
                logger.warning(f"No debits processed for user {request.user.username} despite having goals. Debug info: {', '.join(debug_info)}")
                
                if force_process:
                    messages.warning(
                        request, 
                        "No debits were processed. This could be because your goals have already "
                        "been debited today. Try again tomorrow or manually add funds."
                    )
                else:
                    messages.info(
                        request,
                        "No automatic debits were due for processing at this time. Try using 'Process Now' "
                        "to force immediate processing."
                    )
            else:
                messages.info(request, "No automatic debits were due for processing at this time.")
                
    finally:
        # Always restore the original function if we replaced it
        timezone.now = original_now
        
    # Redirect back to the page they came from
    redirect_url = request.META.get('HTTP_REFERER', 'dashboard')
    return redirect(redirect_url)

@login_required
def savings_analytics(request):
    # Get all savings goals for this user
    goals = SavingsGoal.objects.filter(user=request.user).order_by('completed', 'target_date')
    active_goals = goals.filter(completed=False)
    
    # Calculate summary statistics
    active_goals_count = active_goals.count()
    total_saved = sum(goal.current_amount for goal in goals)
    total_monthly = sum(goal.monthly_contribution for goal in active_goals)
    total_remaining = sum(goal.remaining_amount for goal in active_goals)
    
    # Prepare data for Goal Progress chart
    goal_names = [goal.name for goal in active_goals]
    goal_percentages = [float(goal.percentage_complete) for goal in active_goals]
    
    # Prepare data for Savings Timeline chart (last 6 months)
    today = timezone.now().date()
    timeline_labels = []
    timeline_datasets = []
    
    # Generate the past 6 months of labels
    for i in range(5, -1, -1):
        month_date = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
        for _ in range(i):
            month_date = (month_date.replace(day=1) - timedelta(days=1)).replace(day=1)
        timeline_labels.append(month_date.strftime('%b %Y'))
    
    # Add future 6 months
    next_month = today.replace(day=1)
    for i in range(6):
        next_date = (next_month + timedelta(days=32)).replace(day=1)
        timeline_labels.append(next_date.strftime('%b %Y'))
        next_month = next_date
    
    # Create a dataset for each active goal
    for i, goal in enumerate(active_goals):
        # Placeholder data - in a real app, you would query historical data
        # For demonstration, we'll generate simulated growth data
        starting_amount = float(goal.current_amount) * 0.6  # Simulated past value
        monthly_contribution = float(goal.monthly_contribution)
        
        data = []
        # Past 6 months (simulated)
        for i in range(6):
            data.append(round(starting_amount + (monthly_contribution * i), 2))
        
        # Current month (actual)
        data.append(float(goal.current_amount))
        
        # Future projection (next 6 months)
        for i in range(1, 7):
            projected = float(goal.current_amount) + (monthly_contribution * i)
            if projected > float(goal.target_amount):
                projected = float(goal.target_amount)
            data.append(round(projected, 2))
            
        # Create the dataset object
        timeline_datasets.append({
            'label': goal.name,
            'data': data,
            'borderColor': get_color_for_index(i),
            'backgroundColor': get_color_for_index(i, 0.1),
            'tension': 0.1,
            'fill': False
        })
    
    # Prepare data for Completion Forecast chart
    forecast_labels = [goal.name for goal in active_goals]
    forecast_months = [goal.months_remaining or 0 for goal in active_goals]
    
    # Create auto-debit goals list with days until next debit
    auto_debit_goals = []
    for goal in active_goals.filter(auto_debit_enabled=True):
        next_debit_date = goal.next_debit_date
        if next_debit_date:
            # Instead of setting the attribute directly, create a dictionary or use a custom class
            goal_info = {
                'goal': goal,
                'days_until_next_debit': (next_debit_date - today).days
            }
            auto_debit_goals.append(goal_info)
    
    # Sort goals by days until next debit
    auto_debit_goals = sorted(auto_debit_goals, key=lambda g: g['days_until_next_debit'])
    
    # Get calendar data for current and next 3 months
    calendar_data = {}
    today = timezone.now().date()
    
    for month_offset in range(4):  # Current month + 3 future months
        current_date = today + relativedelta(months=month_offset)
        month_start = current_date.replace(day=1)
        month_end = (month_start + relativedelta(months=1) - timedelta(days=1))
        
        # Get all active goals with auto-debit enabled
        for goal in active_goals.filter(auto_debit_enabled=True):
            debit_day = min(goal.debit_day, calendar.monthrange(current_date.year, current_date.month)[1])
            debit_date = current_date.replace(day=debit_day)
            
            if month_start <= debit_date <= month_end:
                date_str = debit_date.strftime('%Y-%m-%d')
                if date_str not in calendar_data:
                    calendar_data[date_str] = {
                        'amount': 0,
                        'goals': []
                    }
                calendar_data[date_str]['amount'] += float(goal.monthly_contribution)
                calendar_data[date_str]['goals'].append({
                    'name': goal.name,
                    'amount': float(goal.monthly_contribution)
                })

    context = {
        'active_goals_count': active_goals_count,
        'total_saved': total_saved,
        'total_monthly': total_monthly,
        'total_remaining': total_remaining,
        'goal_names': json.dumps(goal_names),
        'goal_percentages': json.dumps(goal_percentages),
        'timeline_labels': json.dumps(timeline_labels),
        'timeline_datasets': json.dumps(timeline_datasets),
        'forecast_labels': json.dumps(forecast_labels),
        'forecast_months': json.dumps(forecast_months),
        'auto_debit_goals': auto_debit_goals,  # Now contains dictionaries with goal and days info
        'calendar_data': json.dumps(calendar_data, cls=DjangoJSONEncoder),
    }
    
    return render(request, 'tracker/savings_analytics.html', context)

def get_color_for_index(index, alpha=1.0):
    """Return a color based on index"""
    colors = [
        f'rgba(59, 130, 246, {alpha})',   # Blue
        f'rgba(16, 185, 129, {alpha})',   # Green
        f'rgba(139, 92, 246, {alpha})',   # Purple
        f'rgba(245, 158, 11, {alpha})',   # Amber
        f'rgba(239, 68, 68, {alpha})',    # Red
        f'rgba(6, 182, 212, {alpha})',    # Cyan
        f'rgba(236, 72, 153, {alpha})',   # Pink
        f'rgba(99, 102, 241, {alpha})',   # Indigo
        f'rgba(20, 184, 166, {alpha})',   # Teal
        f'rgba(249, 115, 22, {alpha})'    # Orange
    ]
    return colors[index % len(colors)]

@login_required
def finance_insights(request):
    """View for comprehensive financial visualizations and insights"""
    from datetime import date, timedelta
    from dateutil.relativedelta import relativedelta
    from django.db.models import Sum, Avg, Count
    
    # Current date for calculations
    today = date.today()
    start_of_month = today.replace(day=1)
    
    # Calculate savings rate (percentage of income saved)
    income_this_month = Transaction.objects.filter(
        user=request.user,
        transaction_type='income',
        date__gte=start_of_month
    ).aggregate(Sum('amount'))['amount__sum'] or 0
    
    expenses_this_month = Transaction.objects.filter(
        user=request.user,
        transaction_type='expense',
        date__gte=start_of_month
    ).aggregate(Sum('amount'))['amount__sum'] or 0
    
    # Calculate savings amount and rate
    saved_this_month = income_this_month - expenses_this_month
    savings_rate = (saved_this_month / income_this_month * 100) if income_this_month > 0 else 0
    
    # Calculate expense trend (percentage change from last month)
    last_month_start = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
    expenses_last_month = Transaction.objects.filter(
        user=request.user,
        transaction_type='expense',
        date__gte=last_month_start,
        date__lt=start_of_month
    ).aggregate(Sum('amount'))['amount__sum'] or 0
    
    expense_trend = ((expenses_this_month - expenses_last_month) / expenses_last_month * 100) if expenses_last_month > 0 else 0
    
    # Calculate average goal progress
    active_goals = SavingsGoal.objects.filter(user=request.user, completed=False)
    if active_goals.exists():
        total_progress = sum(
            (goal.current_amount / goal.target_amount * 100) 
            for goal in active_goals
            if goal.target_amount > 0
        )
        avg_goal_progress = total_progress / active_goals.count()
    else:
        avg_goal_progress = 0
    
    # Calculate budget adherence (percentage of budgets under their limits)
    budgets = Budget.objects.filter(user=request.user)
    on_track_budgets = sum(1 for budget in budgets if budget.spent <= budget.amount)
    budget_adherence = (on_track_budgets / budgets.count() * 100) if budgets.count() > 0 else 0
    
    # Generate monthly labels and data for charts (past 6 months)
    monthly_labels = []
    income_data = []
    expense_data = []
    savings_data = []
    
    for i in range(5, -1, -1):
        month_date = today - relativedelta(months=i)
        month_start = month_date.replace(day=1)
        month_end = (month_date.replace(day=1) + relativedelta(months=1) - timedelta(days=1))
        
        # Get actual data for each month
        month_income = Transaction.objects.filter(
            user=request.user,
            transaction_type='income',
            date__gte=month_start,
            date__lte=month_end
        ).aggregate(Sum('amount'))['amount__sum'] or 0
        
        month_expenses = Transaction.objects.filter(
            user=request.user,
            transaction_type='expense',
            date__gte=month_start,
            date__lte=month_end
        ).aggregate(Sum('amount'))['amount__sum'] or 0
        
        month_savings = month_income - month_expenses
        
        monthly_labels.append(month_date.strftime('%b %Y'))
        income_data.append(float(month_income))
        expense_data.append(float(month_expenses))
        savings_data.append(float(month_savings))
    
    # Get category breakdown data
    category_data = (
        Expense.objects.filter(transaction__user=request.user)
        .values('category__name')
        .annotate(total=Sum('transaction__amount'))
        .order_by('-total')
    )
    
    category_names = [item['category__name'] or 'Uncategorized' for item in category_data]
    category_amounts = [float(item['total']) for item in category_data]
    
    # Generate trend data for different periods
    def get_trend_data(months):
        end_date = today
        start_date = end_date - relativedelta(months=months)
        labels = []
        income = []
        expenses = []
        savings = []
        
        current_date = start_date
        while current_date <= end_date:
            month_start = current_date.replace(day=1)
            month_end = (current_date.replace(day=1) + relativedelta(months=1) - timedelta(days=1))
            
            month_income = Transaction.objects.filter(
                user=request.user,
                transaction_type='income',
                date__gte=month_start,
                date__lte=month_end
            ).aggregate(Sum('amount'))['amount__sum'] or 0
            
            month_expenses = Transaction.objects.filter(
                user=request.user,
                transaction_type='expense',
                date__gte=month_start,
                date__lte=month_end
            ).aggregate(Sum('amount'))['amount__sum'] or 0
            
            labels.append(current_date.strftime('%b %Y'))
            income.append(float(month_income))
            expenses.append(float(month_expenses))
            savings.append(float(month_income - month_expenses))
            
            current_date += relativedelta(months=1)
            
        return labels, income, expenses, savings
    
    # Get trend data for different periods
    trend_labels_3m, income_trend_3m, expense_trend_3m, savings_trend_3m = get_trend_data(3)
    trend_labels_6m, income_trend_6m, expense_trend_6m, savings_trend_6m = get_trend_data(6)
    trend_labels_1y, income_trend_1y, expense_trend_1y, savings_trend_1y = get_trend_data(12)
    
    # Calculate income distribution
    total_income = sum(income_data)
    total_expenses = sum(expense_data)
    total_savings = sum(savings_data)
    
    # Assuming 20% of savings goes to investments (you can modify this based on actual data)
    investment_amount = total_savings * 0.2
    savings_amount = total_savings * 0.8
    
    distribution_data = [
        float(total_expenses),
        float(savings_amount),
        float(investment_amount)
    ]
    
    # Generate personalized recommendations
    recommendations = []
    
    if savings_rate < 20:
        recommendations.append({
            'title': 'Increase Your Savings Rate',
            'description': 'Try to save at least 20% of your monthly income. Consider reviewing your expenses to find areas where you can cut back.'
        })
    
    if expense_trend > 10:
        recommendations.append({
            'title': 'Rising Expenses Alert',
            'description': 'Your expenses have increased significantly compared to last month. Review your spending patterns to identify areas for potential savings.'
        })
    
    if not budgets.exists():
        recommendations.append({
            'title': 'Set Up Budgets',
            'description': 'Creating budgets for different expense categories can help you better manage your spending and reach your financial goals.'
        })
    
    # Add these calculations near the start of the view
    # Calculate total income and expenses
    total_income = Transaction.objects.filter(
        user=request.user,
        transaction_type='income'
    ).aggregate(Sum('amount'))['amount__sum'] or 0
    
    total_expenses = Transaction.objects.filter(
        user=request.user,
        transaction_type='expense'
    ).aggregate(Sum('amount'))['amount__sum'] or 0
    
    # Get top spent category
    top_category = (
        Expense.objects.filter(transaction__user=request.user)
        .values('category__name')
        .annotate(total=Sum('transaction__amount'))
        .order_by('-total')
        .first()
    )
    
    top_category_name = top_category['category__name'] if top_category else 'No Data'
    top_category_amount = top_category['total'] if top_category else 0
    
    # Prepare calendar data
    active_goals = SavingsGoal.objects.filter(user=request.user, completed=False)
    calendar_data = prepare_calendar_data(active_goals)
    
    # Generate projection data for next 12 months
    projection_months = []
    current_date = today
    for i in range(12):
        next_month = current_date + relativedelta(months=i)
        projection_months.append(next_month.strftime('%b %Y'))

    # Create projection datasets for active goals
    projection_datasets = []
    for i, goal in enumerate(active_goals):
        monthly_contribution = float(goal.monthly_contribution)
        current_amount = float(goal.current_amount)
        target_amount = float(goal.target_amount)
        
        projection_data = []
        current_projection = current_amount
        
        # Add current amount and monthly projections for 12 months
        for _ in range(12):
            projection_data.append(round(current_projection, 2))
            current_projection = min(
                current_projection + monthly_contribution,
                target_amount
            )
        
        # Add the target amount as the final point to show the full goal
        projection_data.append(target_amount)
        projection_months.append('Goal')
        
        projection_datasets.append({
            'label': goal.name,
            'data': projection_data,
            'borderColor': get_color_for_index(i),
            'backgroundColor': get_color_for_index(i, 0.1),
            'tension': 0.1,
            'fill': True
        })

    context = {
        'savings_rate': savings_rate,
        'expense_trend': expense_trend,
        'avg_goal_progress': avg_goal_progress,
        'budget_adherence': budget_adherence,
        'monthly_labels': json.dumps(monthly_labels),
        'income_data': json.dumps(income_data),
        'expense_data': json.dumps(expense_data),
        'savings_data': json.dumps(savings_data),
        'category_names': json.dumps(category_names),
        'category_amounts': json.dumps(category_amounts),
        'trend_labels_3m': json.dumps(trend_labels_3m),
        'income_trend_3m': json.dumps(income_trend_3m),
        'expense_trend_3m': json.dumps(expense_trend_3m),
        'savings_trend_3m': json.dumps(savings_trend_3m),
        'trend_labels_6m': json.dumps(trend_labels_6m),
        'income_trend_6m': json.dumps(income_trend_6m),
        'expense_trend_6m': json.dumps(expense_trend_6m),
        'savings_trend_6m': json.dumps(savings_trend_6m),
        'trend_labels_1y': json.dumps(trend_labels_1y),
        'income_trend_1y': json.dumps(income_trend_1y),
        'expense_trend_1y': json.dumps(expense_trend_1y),
        'savings_trend_1y': json.dumps(savings_trend_1y),
        'distribution_data': json.dumps(distribution_data),
        'recommendations': recommendations,
        'total_income': total_income,
        'total_expenses': total_expenses,
        'top_category_name': top_category_name,
        'top_category_amount': top_category_amount,
        'today': timezone.now(),
        'calendar_data': json.dumps(calendar_data, cls=DjangoJSONEncoder),
        'projection_labels': json.dumps(projection_months),
        'projection_datasets': json.dumps(projection_datasets),
    }
    
    return render(request, 'tracker/finance_insights.html', context)

@login_required
def recurring_transactions(request):
    recurring_income = RecurringTransaction.objects.filter(
        user=request.user,
        transaction_type='income',
        is_active=True
    )
    
    recurring_expenses = RecurringTransaction.objects.filter(
        user=request.user,
        transaction_type='expense',
        is_active=True
    )
    
    context = {
        'recurring_income': recurring_income,
        'recurring_expenses': recurring_expenses,
        'day_range': range(1, 32),
    }
    
    return render(request, 'tracker/recurring_transactions.html', context)

@login_required
def add_recurring_transaction(request):
    if request.method == 'POST':
        RecurringTransaction.objects.create(
            user=request.user,
            name=request.POST['name'],
            amount=request.POST['amount'],
            transaction_type=request.POST['transaction_type'],
            frequency=request.POST['frequency'],
            day_of_month=request.POST['day_of_month'],
            scheduled_time=request.POST['scheduled_time'],
            start_date=request.POST['start_date'],
            description=request.POST.get('description', '')
        )
        messages.success(request, 'Recurring transaction added successfully')
        return redirect('recurring_transactions')
    
    return redirect('recurring_transactions')

@login_required
def edit_recurring_transaction(request, transaction_id):
    transaction = get_object_or_404(RecurringTransaction, id=transaction_id, user=request.user)
    
    if request.method == 'POST':
        transaction.name = request.POST['name']
        transaction.amount = request.POST['amount']
        transaction.transaction_type = request.POST['transaction_type']
        transaction.frequency = request.POST['frequency']
        transaction.day_of_month = request.POST['day_of_month']
        transaction.scheduled_time = request.POST['scheduled_time']
        transaction.start_date = request.POST['start_date']
        transaction.description = request.POST.get('description', '')
        transaction.save()
        
        messages.success(request, 'Recurring transaction updated successfully')
        return redirect('recurring_transactions')
    
    return JsonResponse({
        'name': transaction.name,
        'amount': str(transaction.amount),
        'transaction_type': transaction.transaction_type,
        'frequency': transaction.frequency,
        'day_of_month': transaction.day_of_month,
        'scheduled_time': transaction.scheduled_time.strftime('%H:%M'),
        'start_date': transaction.start_date.isoformat(),
        'description': transaction.description,
    })

@login_required
def delete_recurring_transaction(request, transaction_id):
    if request.method == 'POST':
        transaction = get_object_or_404(RecurringTransaction, id=transaction_id, user=request.user)
        transaction.is_active = False
        transaction.save()
        messages.success(request, 'Recurring transaction deleted successfully')
    return redirect('recurring_transactions')

@login_required
def mark_notification_read(request, notification_id):
    notification = get_object_or_404(TransactionNotification, id=notification_id, user=request.user)
    notification.is_read = True
    notification.save()
    return JsonResponse({'status': 'success'})

@login_required
def check_transactions(request):
    if request.method == 'POST':
        processed_transactions = []
        today = timezone.now().date()
        current_time = timezone.now().time()
        
        # Get all active recurring transactions for today
        transactions = RecurringTransaction.objects.filter(
            user=request.user,
            is_active=True,
            day_of_month=today.day,
            scheduled_time__lte=current_time
        ).exclude(last_processed=today)
        
        for transaction in transactions:
            try:
                with transaction.atomic():
                    # Create the transaction
                    transaction_obj = Transaction.objects.create(
                        user=transaction.user,
                        amount=transaction.amount,
                        description=f"Recurring {transaction.transaction_type}: {transaction.name}",
                        date=today,
                        transaction_type=transaction.transaction_type
                    )
                    
                    # Create notification
                    action_word = "credited" if transaction.transaction_type == "income" else "debited"
                    TransactionNotification.objects.create(
                        user=transaction.user,
                        transaction=transaction_obj,
                        message=f"Your {transaction.name} of ₹{transaction.amount} has been {action_word} to your account.",
                        notification_type=transaction.transaction_type
                    )
                    
                    # Update last processed date
                    transaction.last_processed = today
                    transaction.save()
                    
                    processed_transactions.append({
                        'id': transaction.id,
                        'name': transaction.name,
                        'amount': str(transaction.amount),
                        'type': transaction.transaction_type
                    })
            except Exception as e:
                logger.error(f"Error processing transaction {transaction.name}: {str(e)}")
        
        return JsonResponse({
            'status': 'success',
            'processed_transactions': processed_transactions
        })
    
    return JsonResponse({'status': 'error', 'message': 'Invalid request method'})

@login_required
def community_view(request):
    try:
        # Get total users count
        total_users = User.objects.count()
        
        # Get average savings rate across all users
        all_users_savings_rates = []
        for user in User.objects.all():
            total_income = Transaction.objects.filter(
                user=user,
                transaction_type='income'
            ).aggregate(Sum('amount'))['amount__sum'] or 0
            
            total_expenses = Transaction.objects.filter(
                user=user,
                transaction_type='expense'
            ).aggregate(Sum('amount'))['amount__sum'] or 0
            
            if total_income > 0:
                savings_rate = ((total_income - total_expenses) / total_income) * 100
                all_users_savings_rates.append(savings_rate)
        
        avg_savings_rate = round(sum(all_users_savings_rates) / len(all_users_savings_rates), 1) if all_users_savings_rates else 0
        
        # Get most popular savings goals
        popular_goals = SavingsGoal.objects.values('name').annotate(
            count=Count('name')
        ).order_by('-count')[:5]
        
        # Get most common expense categories
        common_categories = ExpenseCategory.objects.values('name').annotate(
            count=Count('name')
        ).order_by('-count')[:5]
        
        # Calculate user's savings rate
        user_total_income = Transaction.objects.filter(
            user=request.user,
            transaction_type='income'
        ).aggregate(Sum('amount'))['amount__sum'] or 0
        
        user_total_expenses = Transaction.objects.filter(
            user=request.user,
            transaction_type='expense'
        ).aggregate(Sum('amount'))['amount__sum'] or 0
        
        user_savings_rate = round(((user_total_income - user_total_expenses) / user_total_income * 100), 1) if user_total_income > 0 else 0
        
        # Calculate user's rank
        if all_users_savings_rates:
            better_than_count = sum(1 for rate in all_users_savings_rates if user_savings_rate > rate)
            percentile = round((better_than_count / len(all_users_savings_rates) * 100), 1)
        else:
            percentile = 0

        # Get recent discussions
        discussions = Discussion.objects.select_related('user').prefetch_related('comments').all()[:10]
        
        # Handle new discussion creation
        if request.method == 'POST':
            if 'create_discussion' in request.POST:
                title = request.POST.get('title')
                content = request.POST.get('content')
                if title and content:
                    Discussion.objects.create(
                        user=request.user,
                        title=title,
                        content=content
                    )
                    messages.success(request, 'Discussion created successfully!')
                    return redirect('community')
            elif 'add_comment' in request.POST:
                discussion_id = request.POST.get('discussion_id')
                content = request.POST.get('comment_content')
                if discussion_id and content:
                    discussion = Discussion.objects.get(id=discussion_id)
                    Comment.objects.create(
                        user=request.user,
                        discussion=discussion,
                        content=content
                    )
                    messages.success(request, 'Comment added successfully!')
                    return redirect('community')
        
        context = {
            'total_users': total_users,
            'avg_savings_rate': avg_savings_rate,
            'popular_goals': popular_goals,
            'common_categories': common_categories,
            'user_savings_rate': user_savings_rate,
            'user_percentile': percentile,
            'discussions': discussions,
        }
        
        return render(request, 'tracker/community.html', context)
        
    except Exception as e:
        messages.error(request, "An error occurred while loading the community page. Please try again later.")
        return redirect('dashboard')

@login_required
def manage_categories(request):
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'add':
            name = request.POST.get('name', '').strip()
            if name:
                # Check if category already exists for this user
                if not ExpenseCategory.objects.filter(user=request.user, name=name).exists():
                    # Validate category name length
                    if len(name) > 100:
                        messages.error(request, 'Category name is too long. Maximum length is 100 characters.')
                    else:
                        ExpenseCategory.objects.create(
                            user=request.user,
                            name=name
                        )
                        messages.success(request, f'Category "{name}" added successfully')
                else:
                    messages.warning(request, f'Category "{name}" already exists')
            else:
                messages.error(request, 'Please enter a category name')
        elif action == 'delete':
            category_id = request.POST.get('category_id')
            if category_id:
                try:
                    category = ExpenseCategory.objects.get(id=category_id, user=request.user)
                    # Check if category has any associated expenses
                    if Expense.objects.filter(category=category).exists():
                        messages.error(request, f'Cannot delete "{category.name}" as it has associated expenses')
                    else:
                        category.delete()
                        messages.success(request, f'Category "{category.name}" deleted successfully')
                except ExpenseCategory.DoesNotExist:
                    messages.error(request, 'Category not found')
    
    # Get all categories for the current user
    user_categories = ExpenseCategory.objects.filter(user=request.user).order_by('name')
    
    # Define default categories
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
    
    # Filter out default categories that the user already has
    existing_category_names = set(user_categories.values_list('name', flat=True))
    suggested_categories = [cat for cat in default_categories if cat not in existing_category_names]
    
    context = {
        'user_categories': user_categories,
        'suggested_categories': suggested_categories,
        'default_categories': default_categories
    }
    
    return render(request, 'tracker/manage_categories.html', context)

@login_required
def confirm_transaction(request, transaction_id):
    transaction = get_object_or_404(RecurringTransaction, id=transaction_id, user=request.user)
    
    if request.method == 'POST':
        status = request.POST.get('status')
        
        if status == 'completed':
            success, message = transaction.process_transaction()
            if success:
                messages.success(request, 'Transaction confirmed and processed successfully')
            else:
                messages.error(request, f'Error processing transaction: {message}')
        elif status == 'failed':
            transaction.status = 'failed'
            transaction.save()
            messages.warning(request, 'Transaction marked as failed')
        
        return redirect('dashboard')
    
    context = {
        'transaction': transaction,
    }
    return render(request, 'tracker/transaction_confirmation.html', context)
