from django import forms
from .models import Usuario

class UsuarioForm(forms.ModelForm):
    class Meta:
        model = Usuario
        fields = ['empresa', 'usuario', 'lastname', 'email', 'avatar']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make empresa readonly
        self.fields['empresa'].disabled = True