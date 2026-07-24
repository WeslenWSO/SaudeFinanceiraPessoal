from django.db import models
from empresa.models import Empresa

class Usuario(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, verbose_name='Empresa', null=True, blank=True)
    usuario = models.CharField(verbose_name='usuario', max_length=50)
    lastname = models.CharField(verbose_name='lastname', max_length=50,blank=True)
    email = models.EmailField(verbose_name='email', max_length=50, blank=True)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True, verbose_name='Avatar')


def __str__(self):
        return f'{self.usuario} {self.lastname}'