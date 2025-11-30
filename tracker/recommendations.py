from datetime import datetime, timedelta
from django.db.models import Avg, Sum, Count, F, Q
from django.utils import timezone
import numpy as np
from .models import Transaction, Budget, SavingsGoal, Expense
from decimal import Decimal
from sklearn.preprocessing import StandardScaler
import pandas as pd
from scipy import stats
import warnings

# Suppress numpy warnings
warnings.filterwarnings('ignore')

class FinancialRecommendationEngine:
    def __init__(self, user):
        self.user = user
        self.recommendations = []
        self.confidence_threshold = 0.7
        self.risk_scores = {
            'savings': 0,
            'spending': 0,
            'budget': 0,
            'goals': 0
        }

    def analyze_financial_health(self):
        """Analyze various financial metrics and generate recommendations"""
        try:
            self._analyze_savings_rate()
            self._analyze_expense_trends()
            self._analyze_budget_adherence()
            self._analyze_category_spending()
            self._analyze_savings_goals()
            self._analyze_spending_patterns()
            self._analyze_income_stability()
            self._analyze_emergency_fund()
            self._analyze_debt_to_income()
            self._analyze_discretionary_spending()
            self._calculate_financial_health_score()
            
            # Sort recommendations by priority and confidence
            self.recommendations.sort(key=lambda x: (x['priority'], x['confidence']), reverse=True)
            return self.recommendations
        except Exception as e:
            # Log the error and return basic recommendations
            print(f"Error in financial analysis: {str(e)}")
            return self._get_fallback_recommendations()

    def _get_fallback_recommendations(self):
        """Provide basic recommendations when advanced analysis fails"""
        # Get basic financial metrics
        total_income = Transaction.objects.filter(
            user=self.user,
            transaction_type='income'
        ).aggregate(Sum('amount'))['amount__sum'] or 0
        
        total_expenses = Transaction.objects.filter(
            user=self.user,
            transaction_type='expense'
        ).aggregate(Sum('amount'))['amount__sum'] or 0
        
        # Basic savings rate calculation
        savings_rate = ((total_income - total_expenses) / total_income * 100) if total_income > 0 else 0
        
        recommendations = []
        
        # Basic recommendations based on simple metrics
        if savings_rate < 20:
            recommendations.append({
                'title': 'Improve Savings Rate',
                'description': f'Your current savings rate is {savings_rate:.1f}%. Try to save at least 20% of your income.',
                'action': 'Review your expenses and look for areas to cut back.',
                'type': 'warning',
                'confidence': 0.8,
                'priority': 1,
                'metric': savings_rate
            })
        
        if total_expenses > total_income:
            recommendations.append({
                'title': 'Expenses Exceed Income',
                'description': 'Your expenses are higher than your income. This is unsustainable in the long term.',
                'action': 'Create a budget and identify areas to reduce spending.',
                'type': 'warning',
                'confidence': 0.9,
                'priority': 1,
                'metric': (total_expenses/total_income)*100 if total_income > 0 else 0
            })
        
        return recommendations

    def _analyze_savings_rate(self):
        """Enhanced savings rate analysis with trend detection"""
        try:
            periods = [30, 90, 180]  # Analyze multiple time periods
            savings_trends = []
            
            for days in periods:
                period_start = timezone.now() - timedelta(days=days)
                
                income = Transaction.objects.filter(
                    user=self.user,
                    transaction_type='income',
                    date__gte=period_start
                ).aggregate(Sum('amount'))['amount__sum'] or Decimal('0')

                expenses = Transaction.objects.filter(
                    user=self.user,
                    transaction_type='expense',
                    date__gte=period_start
                ).aggregate(Sum('amount'))['amount__sum'] or Decimal('0')

                if income > 0:
                    savings_rate = ((income - expenses) / income) * Decimal('100')
                    savings_trends.append(float(savings_rate))

            if savings_trends:
                current_rate = Decimal(str(savings_trends[0]))
                # Use simple difference instead of gradient for more stability
                if len(savings_trends) > 1:
                    trend = Decimal(str(savings_trends[0] - savings_trends[-1]))
                else:
                    trend = Decimal('0')
                
                # Update risk score
                self.risk_scores['savings'] = self._calculate_risk_score(float(current_rate), 20, 40)
                
                if current_rate < Decimal('20'):
                    priority = 1 if trend < 0 else 2
                    confidence = 0.9
                    self.recommendations.append({
                        'title': 'Critical: Improve Savings Rate',
                        'description': f'Your current savings rate of {current_rate:.1f}% is below recommended levels and {"declining" if trend < 0 else "stable"}.',
                        'action': self._generate_savings_action(float(current_rate), float(trend)),
                        'type': 'warning',
                        'confidence': confidence,
                        'priority': priority,
                        'metric': float(current_rate)
                    })
                elif trend < Decimal('-5'):  # Significant decline
                    self.recommendations.append({
                        'title': 'Declining Savings Rate',
                        'description': f'Your savings rate has decreased by {abs(trend):.1f}% over the analyzed period.',
                        'action': 'Review recent changes in spending patterns and income sources.',
                        'type': 'warning',
                        'confidence': 0.85,
                        'priority': 2,
                        'metric': float(trend)
                    })
        except Exception as e:
            print(f"Error in savings rate analysis: {str(e)}")
            # Fallback to basic savings rate calculation
            self._analyze_basic_savings_rate()

    def _analyze_basic_savings_rate(self):
        """Basic savings rate analysis without complex calculations"""
        try:
            # Get last 30 days of data
            period_start = timezone.now() - timedelta(days=30)
            
            income = Transaction.objects.filter(
                user=self.user,
                transaction_type='income',
                date__gte=period_start
            ).aggregate(Sum('amount'))['amount__sum'] or Decimal('0')

            expenses = Transaction.objects.filter(
                user=self.user,
                transaction_type='expense',
                date__gte=period_start
            ).aggregate(Sum('amount'))['amount__sum'] or Decimal('0')

            if income > 0:
                savings_rate = ((income - expenses) / income) * Decimal('100')
                if savings_rate < Decimal('20'):
                    self.recommendations.append({
                        'title': 'Improve Savings Rate',
                        'description': f'Your current savings rate is {savings_rate:.1f}%. Try to save at least 20% of your income.',
                        'action': 'Review your expenses and look for areas to cut back.',
                        'type': 'warning',
                        'confidence': 0.8,
                        'priority': 1,
                        'metric': float(savings_rate)
                    })
        except Exception as e:
            print(f"Error in basic savings rate analysis: {str(e)}")

    def _analyze_income_stability(self):
        """Analyze income stability and diversity"""
        six_months_ago = timezone.now() - timedelta(days=180)
        
        income_data = (
            Transaction.objects.filter(
                user=self.user,
                transaction_type='income',
                date__gte=six_months_ago
            )
            .values('date__month')
            .annotate(total=Sum('amount'))
            .order_by('date__month')
        )

        if income_data:
            # Convert all values to Decimal for consistent calculations
            monthly_incomes = [Decimal(str(entry['total'])) for entry in income_data]
            mean_income = sum(monthly_incomes) / len(monthly_incomes) if monthly_incomes else Decimal('0')
            
            if mean_income > 0:
                # Calculate standard deviation using Decimal
                squared_diff_sum = sum((income - mean_income) ** 2 for income in monthly_incomes)
                std_dev = (squared_diff_sum / len(monthly_incomes)) ** Decimal('0.5')
                cv = (std_dev / mean_income) * Decimal('100')
                
                if cv > Decimal('20'):  # High income variability
                    self.recommendations.append({
                        'title': 'Variable Income Alert',
                        'description': f'Your income shows {cv:.1f}% variability month-to-month.',
                        'action': 'Consider building a larger emergency fund and exploring additional income sources.',
                        'type': 'warning',
                        'confidence': 0.85,
                        'priority': 2,
                        'metric': float(cv)  # Convert to float for JSON serialization
                    })

    def _analyze_emergency_fund(self):
        """Analyze emergency fund adequacy"""
        three_months_expenses = (
            Transaction.objects.filter(
                user=self.user,
                transaction_type='expense',
                date__gte=timezone.now() - timedelta(days=90)
            ).aggregate(Avg('amount'))['amount__avg'] or 0
        ) * 3

        savings = Transaction.objects.filter(
            user=self.user,
            transaction_type='income'
        ).aggregate(Sum('amount'))['amount__sum'] or 0

        if savings < three_months_expenses:
            self.recommendations.append({
                'title': 'Emergency Fund Alert',
                'description': 'Your savings may not cover 3 months of expenses.',
                'action': f'Aim to save ₹{(three_months_expenses - savings):.2f} more for emergencies.',
                'type': 'warning',
                'confidence': 0.9,
                'priority': 1,
                'metric': (savings/three_months_expenses)*100 if three_months_expenses > 0 else 0
            })

    def _analyze_debt_to_income(self):
        """Analyze debt-to-income ratio"""
        monthly_income = (
            Transaction.objects.filter(
                user=self.user,
                transaction_type='income',
                date__gte=timezone.now() - timedelta(days=30)
            ).aggregate(Sum('amount'))['amount__sum'] or 0
        )

        monthly_debt = (
            Expense.objects.filter(
                transaction__user=self.user,
                category__name__icontains='debt',
                transaction__date__gte=timezone.now() - timedelta(days=30)
            ).aggregate(Sum('transaction__amount'))['transaction__amount__sum'] or 0
        )

        if monthly_income > 0:
            dti_ratio = (monthly_debt / monthly_income) * 100
            if dti_ratio > 36:
                self.recommendations.append({
                    'title': 'High Debt-to-Income Ratio',
                    'description': f'Your debt payments are {dti_ratio:.1f}% of your income.',
                    'action': 'Consider debt consolidation or refinancing options.',
                    'type': 'warning',
                    'confidence': 0.9,
                    'priority': 1,
                    'metric': dti_ratio
                })

    def _analyze_discretionary_spending(self):
        """Analyze discretionary vs. essential spending"""
        one_month_ago = timezone.now() - timedelta(days=30)
        
        essential_categories = ['housing', 'utilities', 'groceries', 'healthcare']
        discretionary_spending = (
            Expense.objects.filter(
                transaction__user=self.user,
                transaction__date__gte=one_month_ago
            ).exclude(
                category__name__in=essential_categories
            ).aggregate(Sum('transaction__amount'))['transaction__amount__sum'] or 0
        )

        total_spending = (
            Transaction.objects.filter(
                user=self.user,
                transaction_type='expense',
                date__gte=one_month_ago
            ).aggregate(Sum('amount'))['amount__sum'] or 0
        )

        if total_spending > 0:
            discretionary_ratio = (discretionary_spending / total_spending) * 100
            if discretionary_ratio > 30:
                self.recommendations.append({
                    'title': 'High Discretionary Spending',
                    'description': f'{discretionary_ratio:.1f}% of your spending is on non-essential items.',
                    'action': 'Review discretionary expenses for potential savings.',
                    'type': 'info',
                    'confidence': 0.85,
                    'priority': 3,
                    'metric': discretionary_ratio
                })

    def _calculate_financial_health_score(self):
        """Calculate overall financial health score"""
        weights = {
            'savings': 0.3,
            'spending': 0.25,
            'budget': 0.25,
            'goals': 0.2
        }
        
        total_score = sum(score * weights[category] for category, score in self.risk_scores.items())
        
        if total_score < 60:
            self.recommendations.append({
                'title': 'Financial Health Score Alert',
                'description': f'Your financial health score is {total_score:.1f}/100.',
                'action': 'Focus on improving savings rate and reducing unnecessary expenses.',
                'type': 'warning',
                'confidence': 0.95,
                'priority': 1,
                'metric': total_score
            })

    def _calculate_risk_score(self, value, min_threshold, max_threshold):
        """Calculate risk score for a metric"""
        if value < min_threshold:
            return max(0, (value / min_threshold) * 60)
        elif value > max_threshold:
            return 100
        else:
            return 60 + ((value - min_threshold) / (max_threshold - min_threshold)) * 40

    def _generate_savings_action(self, rate, trend):
        """Generate personalized savings action based on rate and trend"""
        actions = []
        if rate < 10:
            actions.append("Start with saving 1% more of your income each month")
        elif rate < 20:
            actions.append("Try to increase your savings by 2-3% through expense reduction")
        
        if trend < 0:
            actions.append("Review recent changes in spending that may have affected your savings")
        
        return " and ".join(actions) + "."

    def _analyze_expense_trends(self):
        """Enhanced expense trend analysis with seasonality detection"""
        three_months_ago = timezone.now() - timedelta(days=90)
        
        daily_expenses = (
            Transaction.objects.filter(
                user=self.user,
                transaction_type='expense',
                date__gte=three_months_ago
            )
            .values('date')
            .annotate(total=Sum('amount'))
            .order_by('date')
        )

        if daily_expenses:
            amounts = [float(entry['total']) for entry in daily_expenses]
            dates = pd.to_datetime([entry['date'] for entry in daily_expenses])
            
            # Convert to pandas series for time series analysis
            expense_series = pd.Series(amounts, index=dates)
            
            # Detect trends
            rolling_mean = expense_series.rolling(window=7).mean()
            trend = np.polyfit(range(len(amounts)), amounts, 1)[0]
            
            # Detect seasonality (weekly patterns)
            weekly_pattern = expense_series.groupby(expense_series.index.dayofweek).mean()
            max_day = weekly_pattern.idxmax()
            
            if trend > 0:
                self.recommendations.append({
                    'title': 'Increasing Expense Trend',
                    'description': f'Your daily expenses are trending upward by ₹{trend:.2f} per day.',
                    'action': 'Review your spending patterns and identify areas for reduction.',
                    'type': 'warning',
                    'confidence': 0.85,
                    'priority': 2,
                    'metric': trend
                })
            
            if weekly_pattern.max() > weekly_pattern.mean() * 1.5:
                self.recommendations.append({
                    'title': 'Weekly Spending Pattern',
                    'description': f'Your spending peaks on {["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][max_day]}s.',
                    'action': 'Consider spreading out your expenses more evenly through the week.',
                    'type': 'info',
                    'confidence': 0.8,
                    'priority': 3,
                    'metric': float(weekly_pattern.max() / weekly_pattern.mean())
                })

    def _analyze_category_spending(self):
        """Enhanced category spending analysis with peer comparison"""
        one_month_ago = timezone.now() - timedelta(days=30)
        
        user_categories = (
            Expense.objects.filter(
                transaction__user=self.user,
                transaction__date__gte=one_month_ago
            )
            .values('category__name')
            .annotate(
                total=Sum('transaction__amount'),
                count=Count('id'),
                avg_transaction=Avg('transaction__amount')
            )
            .order_by('-total')
        )

        if user_categories:
            # Calculate category distribution
            total_spending = sum(cat['total'] for cat in user_categories)
            
            for category in user_categories:
                percentage = (category['total'] / total_spending) * 100
                avg_transaction = category['avg_transaction']
                
                if percentage > 40:
                    self.recommendations.append({
                        'title': f'High Spending in {category["category__name"].title()}',
                        'description': f'This category represents {percentage:.1f}% of your spending with average transaction of ₹{avg_transaction:.2f}.',
                        'action': f'Consider setting a budget for {category["category__name"]} expenses.',
                        'type': 'warning',
                        'confidence': 0.85,
                        'priority': 2,
                        'metric': percentage
                    })
                elif avg_transaction > 100:  # High average transaction amount
                    self.recommendations.append({
                        'title': f'Large Transactions in {category["category__name"].title()}',
                        'description': f'Average transaction is ₹{avg_transaction:.2f}.',
                        'action': 'Look for ways to reduce transaction sizes or find better deals.',
                        'type': 'info',
                        'confidence': 0.75,
                        'priority': 3,
                        'metric': float(avg_transaction)
                    })

    def _analyze_savings_goals(self):
        """Analyze progress towards savings goals"""
        active_goals = SavingsGoal.objects.filter(user=self.user, completed=False)
        
        for goal in active_goals:
            if goal.percentage_complete < 10 and goal.months_remaining and goal.months_remaining < 3:
                confidence = 0.9
                self.recommendations.append({
                    'title': f'Goal at Risk: {goal.name}',
                    'description': f'You\'re only {goal.percentage_complete:.1f}% towards your goal with {goal.months_remaining} months remaining.',
                    'action': 'Consider increasing your monthly contribution or adjusting your target date.',
                    'type': 'warning',
                    'confidence': confidence,
                    'priority': 1,  # High priority for goals at risk
                    'metric': goal.percentage_complete
                })

    def _analyze_spending_patterns(self):
        """Analyze daily/weekly spending patterns"""
        one_month_ago = timezone.now() - timedelta(days=30)
        
        daily_expenses = (
            Transaction.objects.filter(
                user=self.user,
                transaction_type='expense',
                date__gte=one_month_ago
            )
            .values('date')
            .annotate(total=Sum('amount'))
            .order_by('date')
        )

        if daily_expenses:
            # Convert Decimal to float for numpy calculations
            daily_amounts = [float(entry['total']) for entry in daily_expenses]
            std_dev = np.std(daily_amounts)
            mean = np.mean(daily_amounts)
            
            # Convert to Decimal for comparison
            std_dev = Decimal(str(std_dev))
            mean = Decimal(str(mean))
            
            if std_dev > mean * Decimal('0.5'):  # High variation in daily spending
                confidence = 0.75
                variation_metric = float((std_dev/mean)*100)  # Convert back to float for display
                self.recommendations.append({
                    'title': 'Irregular Spending Pattern',
                    'description': 'Your daily spending shows high variation, which might indicate impulse purchases.',
                    'action': 'Try to maintain more consistent spending habits and plan purchases in advance.',
                    'type': 'info',
                    'confidence': confidence,
                    'priority': 3,  # Lower priority for spending pattern analysis
                    'metric': variation_metric
                })

    def _analyze_budget_adherence(self):
        """Analyze budget adherence and provide recommendations"""
        current_date = timezone.now()
        
        # Get active budgets that include the current date
        budgets = Budget.objects.filter(
            user=self.user,
            is_active=True,
            start_date__lte=current_date,
            end_date__gte=current_date
        )
        
        if not budgets.exists():
            self.recommendations.append({
                'title': 'No Active Budgets',
                'description': 'You haven\'t set up any active budgets for the current period.',
                'action': 'Create budgets for your major expense categories to track spending better.',
                'type': 'info',
                'confidence': 0.95,
                'priority': 2,
                'metric': 0
            })
            self.risk_scores['budget'] = 0
        else:
            over_budget_count = 0
            total_budgets = budgets.count()
            
            for budget in budgets:
                if budget.spent > budget.amount:
                    over_budget_count += 1
                    self.recommendations.append({
                        'title': f'Budget Overrun: {budget.category.name}',
                        'description': f'You\'ve exceeded your {budget.category.name} budget by ₹{(budget.spent - budget.amount):.2f}.',
                        'action': f'Review your {budget.category.name} expenses and adjust spending or increase budget.',
                        'type': 'warning',
                        'confidence': 0.9,
                        'priority': 1,
                        'metric': float((budget.spent / budget.amount) * 100)
                    })
            
            # Calculate overall budget adherence score
            adherence_score = ((total_budgets - over_budget_count) / total_budgets) * 100 if total_budgets > 0 else 0
            self.risk_scores['budget'] = self._calculate_risk_score(adherence_score, 70, 90)
            
            if adherence_score < 70:
                self.recommendations.append({
                    'title': 'Low Budget Adherence',
                    'description': f'You\'re over budget in {over_budget_count} out of {total_budgets} categories.',
                    'action': 'Review your spending habits and consider adjusting your budgets or reducing expenses.',
                    'type': 'warning',
                    'confidence': 0.85,
                    'priority': 2,
                    'metric': adherence_score
                }) 