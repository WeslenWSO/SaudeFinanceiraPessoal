from django.forms import ModelForm, TextInput
from django.db import models
from django import forms
from django.contrib.admin import widgets


# Create your models here.
class Cobranca(models.Model):
     
    formapgto =  models.CharField(verbose_name='Tipo', max_length=1,  default='0',
                             choices=(
                                        ('0', 'A VISTA'),
                                        ('1', 'A PRAZO'),
                                          ))
    descricao = models.CharField(verbose_name='Descricao',  max_length=50)
    tpag  = models.CharField(verbose_name='Tipo Pagto', max_length=3)
    intervaloparcelas = models.IntegerField(verbose_name='Intervalo Parcelas (dias)', default=30, help_text='Intervalo em dias entre parcelas para pagamentos a prazo')
    
    # widgets = {
    #    'descricao': TextInput(attrs={'class':'from-control'})
    # }
    
    def __str__(self):
        return f'{self.formapgto} {self.tpag} {self.descricao}'
      
class CobModelForm(ModelForm):
    class Meta:
      model = Cobranca
      fields = '__all__'
      widgets = {
       'descricao': TextInput(attrs={'class':'from-control'})
     }