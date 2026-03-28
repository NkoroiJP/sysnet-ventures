from django.shortcuts import render, redirect
from django.contrib import messages
from billing.models import ContactMessage

def home(request):
    return render(request, 'home.html')

def contact(request):
    """Handle contact form submissions"""
    if request.method == 'POST':
        first_name = request.POST.get('first-name', '')
        last_name = request.POST.get('last-name', '')
        email = request.POST.get('email', '')
        message_text = request.POST.get('message', '')
        
        # Save to database
        ContactMessage.objects.create(
            first_name=first_name,
            last_name=last_name,
            email=email,
            message=message_text
        )
        
        messages.success(request, f'Thank you {first_name}! Your message has been sent. We will get back to you at {email}.')
        return redirect('home')
    
    return redirect('home')
