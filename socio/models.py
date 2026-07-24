from django.db import models
from django.utils import module_loading
from empresa.models import Empresa

# Create your models here.
class Socio(models.Model):
    socio = models.CharField(verbose_name='Socio', max_length=50)
    lastname = models.CharField(verbose_name='lastname', max_length=50,blank=True)
    email = models.EmailField(verbose_name='email', max_length=50, blank=True)
    cpf = models.CharField(verbose_name='CPF', max_length=14, blank=True, null=True)
    tipo = models.CharField(verbose_name='tipo', max_length=50)
    avatarsoc = models.ImageField(blank=True, upload_to='avatar/%Y/', null=True, verbose_name='Imagem')
    # Empresa
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, verbose_name='Empresa', null=True, blank=True)
    
 
    def __str__(self):
        return f'{self.socio} {self.lastname}'
    
   