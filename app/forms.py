from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.models import User
from .models import Investor


class SignUpForm(UserCreationForm):
    email = forms.EmailField(
        max_length=254, help_text="Required. Inform a valid email address."
    )

    class Meta:
        model = User
        fields = (
            "username",
            "email",
            "password1",
            "password2",
        )

    # def __init__(self, *args, **kwargs):
    #     self.fields['username'].widget.attrs.update({'class':'form-control','placeholder':'Username'})
    #     self.fields['email'].widget.attrs.update({'class':'form-control','placeholder':'Email'})
    #     self.fields['password'].widget.attrs.update({'class':'form-control','placeholder':'Password'})


class UserLoginForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super(UserLoginForm, self).__init__(*args, **kwargs)

    username = forms.CharField(
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "", "id": "username"}
        )
    )
    password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={"class": "form-control", "placeholder": "", "id": "password",}
        )
    )


class ProfileForm(forms.Form):
    attrs = {"class": "form-control"}
    first_name = forms.CharField(
        label="First name",
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs=attrs),
    )
    last_name = forms.CharField(
        label="Last name",
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs=attrs),
    )
    uitheme = forms.ChoiceField(
        label="Theme",
        choices=Investor.THEMES,
        required=False,
        widget=forms.Select(attrs=attrs),
    )
