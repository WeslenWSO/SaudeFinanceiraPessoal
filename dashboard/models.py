from django.db import models
from django.utils import timezone

from empresa.models import Empresa


class ContaAzulConfig(models.Model):
    """Configuração OAuth Conta Azul — uma por empresa (cliente)."""

    AMBIENTE_DEV = 'DEV'
    AMBIENTE_PROD = 'PROD'
    AMBIENTE_CHOICES = [
        (AMBIENTE_DEV, 'Desenvolvimento'),
        (AMBIENTE_PROD, 'Produção'),
    ]

    REDIRECT_DEV = 'https://www.contaazul.com'
    REDIRECT_PROD = 'https://financaspessoais-eloo.onrender.com/empresa/conta-azul/oauth/callback/'

    empresa = models.OneToOneField(
        Empresa,
        on_delete=models.CASCADE,
        related_name='conta_azul_config',
        verbose_name='Empresa',
    )
    ativo = models.BooleanField(default=True, verbose_name='Integração ativa')
    ambiente = models.CharField(
        max_length=4,
        choices=AMBIENTE_CHOICES,
        default=AMBIENTE_DEV,
        verbose_name='Ambiente',
    )
    client_id = models.CharField(max_length=120, blank=True, default='', verbose_name='Client ID')
    client_secret_cifrado = models.TextField(blank=True, default='')
    redirect_uri = models.CharField(max_length=500, blank=True, default='', verbose_name='Redirect URI')
    access_token_cifrado = models.TextField(blank=True, default='')
    refresh_token_cifrado = models.TextField(blank=True, default='')
    token_expira_em = models.DateTimeField(null=True, blank=True, verbose_name='Token expira em')
    oauth_state = models.CharField(max_length=64, blank=True, default='')
    conectado_em = models.DateTimeField(null=True, blank=True, verbose_name='Conectado em')
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Configuração Conta Azul'
        verbose_name_plural = 'Configurações Conta Azul'

    def __str__(self):
        return f'Conta Azul — {self.empresa}'

    def em_desenvolvimento(self) -> bool:
        return self.ambiente == self.AMBIENTE_DEV

    def redirect_uri_efetiva(self) -> str:
        custom = (self.redirect_uri or '').strip()
        if self.em_desenvolvimento():
            # Em DEV ignore redirect de produção salvo por engano no formulário.
            if custom and custom not in (self.REDIRECT_PROD, self.REDIRECT_DEV):
                return custom
            return self.REDIRECT_DEV
        if custom:
            return custom
        return self.REDIRECT_PROD

    def redirect_uri_dev_captura(self, base_url: str) -> str:
        """URL local para capturar code em popup (cadastrar no portal Conta Azul)."""
        base = (base_url or '').rstrip('/')
        return f'{base}/empresa/conta-azul/oauth/dev/captura/'

    def credenciais_preenchidas(self) -> bool:
        return bool((self.client_id or '').strip() and (self.client_secret_cifrado or '').strip())

    def tem_refresh_token(self) -> bool:
        return bool((self.refresh_token_cifrado or '').strip())

    def token_valido(self) -> bool:
        if not self.token_expira_em:
            return False
        return self.token_expira_em > timezone.now()

    def precisa_reconectar(self) -> bool:
        """True quando não há refresh token ou a renovação automática provavelmente falhará."""
        if not self.tem_refresh_token():
            return True
        return False

    def status_conexao(self) -> str:
        if not self.credenciais_preenchidas():
            return 'sem_credenciais'
        if not self.tem_refresh_token():
            return 'nao_conectado'
        if self.token_valido():
            return 'ok'
        return 'renovar_automatico'


class GeminiConfig(models.Model):
    """Chave Gemini global (fallback quando GEMINI_API_KEY não está no ambiente)."""

    api_key = models.CharField(
        max_length=200,
        blank=True,
        default='',
        verbose_name='API Key Gemini',
        help_text='Usada em produção se a variável GEMINI_API_KEY não estiver no Render.',
    )
    model_name = models.CharField(
        max_length=80,
        blank=True,
        default='gemini-2.5-flash',
        verbose_name='Modelo Gemini',
    )
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Configuração Gemini'
        verbose_name_plural = 'Configurações Gemini'

    def __str__(self):
        return 'Gemini (global)'

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def api_key_configurada(self) -> bool:
        return bool((self.api_key or '').strip())
