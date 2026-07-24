from django import forms
from .models import Categoria

class CategoriaForm(forms.ModelForm):
    class Meta:
        model = Categoria
        fields = ['empresa', 'nome', 'grupo', 'classificacao', 'sintetico', 'tipo']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make empresa readonly
        self.fields['empresa'].disabled = True