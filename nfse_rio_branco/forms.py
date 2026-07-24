# nfse_rio_branco/forms.py
from django import forms
from .models import Company
#from SaudeFinanceira.empresa.models import Empresa


class StartDownloadForm(forms.Form):
    company = forms.ModelChoiceField(queryset=Company.objects.all())
    inicio = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    fim = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    opcao = forms.CharField(    max_length=1,     # limita a 1 caractere
    min_length=1,     # obriga ter ao menos 1
    required=True,    # não pode ficar vazio
    label="Opção"
)