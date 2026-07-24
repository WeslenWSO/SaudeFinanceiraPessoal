from django import forms

class LoginForm(forms.Form):
    username = forms.CharField(max_length=100, label='Username', 
                                widget=forms.TextInput(attrs={'class': 'form-control'})
                              )
    password = forms.CharField(max_length=10, label='Password', 
                                widget=forms.TextInput(attrs={'class': 'form-control'})
                              )