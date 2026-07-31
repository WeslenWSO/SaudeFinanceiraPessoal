from django.conf import settings
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


class PermissaoMenuUsuario(models.Model):
    """Opções do menu principal liberadas para o usuário de login."""

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='permissoes_menu',
        verbose_name='Usuário de login',
    )
    codigo = models.CharField(max_length=60, verbose_name='Código do menu', db_index=True)

    class Meta:
        verbose_name = 'Permissão de menu'
        verbose_name_plural = 'Permissões de menu'
        constraints = [
            models.UniqueConstraint(fields=['usuario', 'codigo'], name='usuario_menu_codigo_unico'),
        ]
        ordering = ['usuario_id', 'codigo']

    def __str__(self):
        return f'{self.usuario.username} → {self.codigo}'