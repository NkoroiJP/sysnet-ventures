from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm

from .models import User


class StyledAuthenticationForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'input'})


class UserForm(forms.ModelForm):
    """Create/update staff and client users (super admin only)."""
    password1 = forms.CharField(
        label='Password', strip=False, required=False,
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
        help_text='Leave blank when editing to keep the current password.',
    )
    password2 = forms.CharField(
        label='Password confirmation', strip=False, required=False,
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
    )

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'phone', 'role', 'client', 'is_active']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['client'].required = False
        for field in self.fields.values():
            css = field.widget.attrs.get('class', '')
            field.widget.attrs['class'] = (css + ' input').strip()

    def clean(self):
        cleaned = super().clean()
        role = cleaned.get('role')
        client = cleaned.get('client')
        if role == User.CLIENT and not client and not (self.instance and self.instance.pk and self.instance.client):
            raise forms.ValidationError('Client users must be linked to a client record.')
        if role != User.CLIENT and client:
            raise forms.ValidationError('Only Client-role users link to a client record.')

        password1 = cleaned.get('password1')
        password2 = cleaned.get('password2')
        if password1 or password2:
            if password1 != password2:
                raise forms.ValidationError('Passwords do not match.')
            if not self.instance.pk:
                if not password1:
                    raise forms.ValidationError('A password is required for new users.')
                from django.contrib.auth.password_validation import validate_password
                validate_password(password1)
            else:
                from django.contrib.auth.password_validation import validate_password
                validate_password(password1, self.instance)
        elif not self.instance.pk:
            raise forms.ValidationError('A password is required for new users.')
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        password = self.cleaned_data.get('password1')
        if password:
            user.set_password(password)
        if commit:
            user.save()
        return user


class StaffPasswordChangeForm(forms.Form):
    current_password = forms.CharField(widget=forms.PasswordInput)
    new_password1 = forms.CharField(widget=forms.PasswordInput, label='New password')
    new_password2 = forms.CharField(widget=forms.PasswordInput, label='Confirm new password')

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs['class'] = 'input'

    def clean_current_password(self):
        from django.contrib.auth import authenticate
        current = self.cleaned_data['current_password']
        if not self.user.check_password(current):
            raise forms.ValidationError('Current password is incorrect.')
        return current

    def clean(self):
        cleaned = super().clean()
        p1, p2 = cleaned.get('new_password1'), cleaned.get('new_password2')
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError('New passwords do not match.')
        if p1:
            from django.contrib.auth.password_validation import validate_password
            validate_password(p1, self.user)
        return cleaned

    def save(self, commit=True):
        self.user.set_password(self.cleaned_data['new_password1'])
        if commit:
            self.user.save()
        return self.user
