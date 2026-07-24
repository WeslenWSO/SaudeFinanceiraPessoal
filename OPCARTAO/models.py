from django.db import models

# Create your models here.
class Opcartao(models.Model):
    tband =  models.CharField(verbose_name='tband', max_length=2 )
    descricao = models.CharField(verbose_name='Descricao', max_length=50)
    
    
    def __str__(self):
        return f'{self.tband} {self.descricao}'