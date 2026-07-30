from django import forms

class LoginForm(forms.Form):
    username = forms.CharField(
        max_length=100,
        label='Usuário',
        widget=forms.TextInput(attrs={'class': 'form-control', 'autocomplete': 'username'}),
    )
    password = forms.CharField(
        max_length=128,
        label='Senha',
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'autocomplete': 'current-password'}),
    )