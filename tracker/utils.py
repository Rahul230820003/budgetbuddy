from django.core.mail import send_mail
from django.conf import settings
from django.template.loader import render_to_string

def send_otp_email(user, otp):
    subject = 'Verify Your Email - BudgetBuddy'
    html_message = render_to_string('tracker/email/verify_email.html', {
        'user': user,
        'otp': otp
    })
    plain_message = f'Your verification code is: {otp}'
    
    send_mail(
        subject,
        plain_message,
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        html_message=html_message,
        fail_silently=False,
    ) 