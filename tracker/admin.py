from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User
from .models import (
    Transaction, ExpenseCategory, Expense, UserProfile,
    Budget, SavingsGoal, RecurringTransaction,
    TransactionNotification, Discussion, Comment
)

class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'User Profile'
    fk_name = 'user'

class CustomUserAdmin(UserAdmin):
    inlines = (UserProfileInline,)
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_staff', 'date_joined')
    list_filter = ('is_staff', 'is_superuser', 'is_active', 'groups')
    search_fields = ('username', 'first_name', 'last_name', 'email')
    ordering = ('-date_joined',)

class TransactionAdmin(admin.ModelAdmin):
    list_display = ('user', 'amount', 'description', 'date', 'transaction_type')
    list_filter = ('transaction_type', 'date', 'user')
    search_fields = ('description', 'user__username')
    date_hierarchy = 'date'
    ordering = ('-date',)

class ExpenseCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'user')
    list_filter = ('user',)
    search_fields = ('name', 'user__username')
    ordering = ('name',)

class ExpenseAdmin(admin.ModelAdmin):
    list_display = ('transaction', 'category', 'get_amount', 'get_date', 'get_user')
    list_filter = ('category', 'transaction__date', 'transaction__user')
    search_fields = ('transaction__description', 'category__name', 'transaction__user__username')
    date_hierarchy = 'transaction__date'
    ordering = ('-transaction__date',)

    def get_amount(self, obj):
        return obj.transaction.amount
    get_amount.short_description = 'Amount'

    def get_date(self, obj):
        return obj.transaction.date
    get_date.short_description = 'Date'

    def get_user(self, obj):
        return obj.transaction.user
    get_user.short_description = 'User'

class BudgetAdmin(admin.ModelAdmin):
    list_display = ('user', 'category', 'amount', 'start_date', 'end_date', 'is_active', 'get_spent', 'get_remaining')
    list_filter = ('is_active', 'start_date', 'end_date', 'user', 'category')
    search_fields = ('user__username', 'category__name')
    date_hierarchy = 'start_date'
    ordering = ('-created_at',)

    def get_spent(self, obj):
        return obj.spent
    get_spent.short_description = 'Spent'

    def get_remaining(self, obj):
        return obj.remaining
    get_remaining.short_description = 'Remaining'

class SavingsGoalAdmin(admin.ModelAdmin):
    list_display = ('user', 'name', 'target_amount', 'current_amount', 'monthly_contribution', 
                   'start_date', 'target_date', 'completed', 'auto_debit_enabled', 'get_next_debit')
    list_filter = ('completed', 'auto_debit_enabled', 'start_date', 'target_date', 'user')
    search_fields = ('name', 'user__username')
    date_hierarchy = 'start_date'
    ordering = ('-created_at',)

    def get_next_debit(self, obj):
        return obj.formatted_next_debit
    get_next_debit.short_description = 'Next Debit'

class RecurringTransactionAdmin(admin.ModelAdmin):
    list_display = ('user', 'name', 'amount', 'transaction_type', 'frequency', 
                   'start_date', 'day_of_month', 'scheduled_time', 'is_active', 'last_processed')
    list_filter = ('transaction_type', 'frequency', 'is_active', 'start_date', 'user')
    search_fields = ('name', 'user__username', 'description')
    date_hierarchy = 'start_date'
    ordering = ('-created_at',)

class TransactionNotificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'transaction', 'message', 'notification_type', 'is_read', 'created_at')
    list_filter = ('notification_type', 'is_read', 'created_at', 'user')
    search_fields = ('message', 'user__username', 'transaction__description')
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)

class CommentInline(admin.TabularInline):
    model = Comment
    extra = 1

class DiscussionAdmin(admin.ModelAdmin):
    list_display = ('user', 'title', 'created_at', 'updated_at', 'get_likes_count')
    list_filter = ('created_at', 'updated_at', 'user')
    search_fields = ('title', 'content', 'user__username')
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)
    inlines = [CommentInline]

    def get_likes_count(self, obj):
        return obj.likes.count()
    get_likes_count.short_description = 'Likes'

class CommentAdmin(admin.ModelAdmin):
    list_display = ('discussion', 'user', 'content', 'created_at', 'updated_at')
    list_filter = ('created_at', 'updated_at', 'user')
    search_fields = ('content', 'user__username', 'discussion__title')
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)

# Unregister the default User admin and register our custom one
admin.site.unregister(User)
admin.site.register(User, CustomUserAdmin)

# Register all other models
admin.site.register(Transaction, TransactionAdmin)
admin.site.register(ExpenseCategory, ExpenseCategoryAdmin)
admin.site.register(Expense, ExpenseAdmin)
admin.site.register(Budget, BudgetAdmin)
admin.site.register(SavingsGoal, SavingsGoalAdmin)
admin.site.register(RecurringTransaction, RecurringTransactionAdmin)
admin.site.register(TransactionNotification, TransactionNotificationAdmin)
admin.site.register(Discussion, DiscussionAdmin)
admin.site.register(Comment, CommentAdmin)
