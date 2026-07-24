from django import forms
import requests
from .models import Socio

from django.forms.widgets import ClearableFileInput

class SocioForm(forms.ModelForm):
    avatarsoc = forms.ImageField(widget=ClearableFileInput)
    id = forms.IntegerField()

    class Meta:
          model = Socio
          fields  = '__all__'
        #   fields = ['id','avatarsoc']
        #   exclude = ['lastname','tipo','email']
    

   

   