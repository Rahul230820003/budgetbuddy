import time
from datetime import datetime, timedelta
from django.utils import timezone

class AutoDebitMiddleware:
    """Middleware to check for scheduled debits on each request (max once per minute)"""
    
    def __init__(self, get_response):
        self.get_response = get_response
        self.last_check_time = {}  # Dictionary to store user's last check time
        
    def __call__(self, request):
        # Process request
        if request.user.is_authenticated:
            # Check if we need to run the debit check for this user
            self._maybe_check_debits(request)
            
        response = self.get_response(request)
        return response
    
    def _maybe_check_debits(self, request):
        """Run the debit check at most once per minute per user"""
        if not request.user.is_authenticated:
            return
        
        user_id = request.user.id
        now = timezone.now()
        
        # If this user hasn't been checked before or it's been more than 30 seconds
        if (user_id not in self.last_check_time or 
            now - self.last_check_time[user_id] > timedelta(seconds=30)):
            
            # Update the last check time first to prevent multiple checks
            self.last_check_time[user_id] = now
            
            # Import here to avoid circular import
            from .tasks import check_scheduled_debits
            
            # Check only for the current user
            check_scheduled_debits(user=request.user) 