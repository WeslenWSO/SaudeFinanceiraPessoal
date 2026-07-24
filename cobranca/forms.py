from django import forms

class CobrancaForm(forms.Form):

    formapgto = forms.ChoiceField(widget=forms.Select(attrs={'class':'from-select'}))
    descricao =  forms.CharField(label="Descricao", widget = forms.TextInput(attrs= {'class': 'form-control'} )
                                 )