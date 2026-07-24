import os
import uuid

from django.db import models
from django.contrib.auth.models import User


def _empresa_pfx_nacional_upload_to(instance, filename: str) -> str:
    ext = (os.path.splitext(filename)[1] or ".pfx").lower()
    if ext not in (".pfx", ".p12"):
        ext = ".pfx"
    ident = instance.pk if instance.pk else uuid.uuid4().hex[:16]
    return f"empresa/certificados/{ident}/certificado{ext}"

# Create your models here.
class Empresa(models.Model):
    STATUS_CHOICES = [
        ('Ativa', 'Ativa'),
        ('Inativa', 'Inativa'),
    ]
    razao = models.CharField(verbose_name='Razao', max_length=50)
    cnpj = models.CharField(verbose_name='CNPJ', max_length=14)
    status = models.CharField(
        verbose_name='Estatus',
        max_length=7,
        choices=STATUS_CHOICES,
        default='Ativa'
    )
    nome_fantasia = models.CharField(verbose_name='Nome Fantasia', max_length=100, blank=True, null=True)
    endereco = models.TextField(verbose_name='Endereço', blank=True, null=True)
    telefone = models.CharField(verbose_name='Telefone', max_length=20, blank=True, null=True)
    email = models.EmailField(verbose_name='Email', blank=True, null=True)
    usa_base_calculo_reduzido = models.BooleanField(verbose_name='Usa Base de Cálculo Reduzido', default=False)
    utiliza_iss_fixo = models.BooleanField(verbose_name='Utiliza ISS Fixo', default=False)

    REGIME_TRIBUTARIO_CHOICES = [
        ('LUCRO_REAL', 'Lucro Real'),
        ('LUCRO_PRESUMIDO', 'Lucro Presumido'),
        ('SIMPLES_NACIONAL', 'Simples Nacional'),
    ]
    regime_tributario = models.CharField(
        verbose_name='Regime Tributário',
        max_length=20,
        choices=REGIME_TRIBUTARIO_CHOICES,
        default='LUCRO_REAL',
        blank=True,
        null=True
    )

    TIPO_APURACAO_CHOICES = [
        ('CAIXA', 'Caixa'),
        ('COMPETENCIA', 'Competência'),
    ]
    tipo_apuracao = models.CharField(
        verbose_name='Tipo de Apuração',
        max_length=15,
        choices=TIPO_APURACAO_CHOICES,
        default='COMPETENCIA',
        blank=True,
        null=True
    )

    # Campos específicos para Simples Nacional
    anexo_i = models.BooleanField(verbose_name='Anexo I', default=False)
    anexo_ii = models.BooleanField(verbose_name='Anexo II', default=False)
    anexo_iii = models.BooleanField(verbose_name='Anexo III', default=False)
    anexo_iv = models.BooleanField(verbose_name='Anexo IV', default=False)
    anexo_v = models.BooleanField(verbose_name='Anexo V', default=False)
    tem_fator_r = models.BooleanField(
        verbose_name='Possui Fator R',
        default=False,
        help_text='Apenas para Anexos III e V'
    )

    codigo_externo = models.CharField(verbose_name='Código Externo', max_length=50, blank=True, null=True, help_text='Código externo para integração com outros sistemas')

    # NFS-e ambiente nacional (SEFIN): opcional por empresa; senha armazenada cifrada (Fernet/SECRET_KEY).
    nfse_nacional_base_url = models.CharField(
        verbose_name='URL base SEFIN (NFS-e nacional)',
        max_length=255,
        blank=True,
        default='',
        help_text='Vazio usa NFSE_NACIONAL_BASE_URL do servidor. Ex.: https://sefin.nfse.gov.br ou https://sefin.producaorestrita.nfse.gov.br',
    )
    nfse_nacional_pfx_arquivo = models.FileField(
        verbose_name="Certificado digital (.pfx)",
        upload_to=_empresa_pfx_nacional_upload_to,
        max_length=500,
        blank=True,
        help_text="Envie o arquivo pelo navegador; fica salvo no servidor (pasta media/).",
    )
    nfse_nacional_pfx_path = models.CharField(
        verbose_name="Caminho absoluto no servidor (alternativa ao arquivo acima)",
        max_length=500,
        blank=True,
        default="",
        help_text="Somente se o .pfx já estiver em disco neste servidor (ex.: path Linux). "
        "Se enviar arquivo acima, este campo pode ficar em branco.",
    )
    nfse_nacional_pfx_senha_cifrada = models.TextField(
        verbose_name='Senha do PFX (cifrada)',
        blank=True,
        default='',
        editable=False,
    )
    nfse_nacional_cert_validade = models.DateField(
        verbose_name='Validade do certificado (fim)',
        null=True,
        blank=True,
        help_text='Preenchida automaticamente ao validar o PFX com a senha.',
    )
    nfse_nacional_thumbprint_sha1 = models.CharField(
        verbose_name='Thumbprint SHA1 (referência Windows)',
        max_length=40,
        blank=True,
        default='',
        help_text='Opcional: preenchido ao escolher certificado na busca no Windows.',
    )
    nfse_nacional_codigo_ibge_municipio = models.CharField(
        verbose_name='Código IBGE do município (NFS-e nacional)',
        max_length=7,
        blank=True,
        default='',
        help_text='7 dígitos do município emissor (DPS). Obrigatório para usar “Importar NFSe — Portal Nacional” (o IBGE não é digitado naquela tela).',
    )
    nfse_nacional_dps_serie_padrao = models.CharField(
        verbose_name='Série DPS padrão (portal nacional)',
        max_length=8,
        blank=True,
        default='',
        help_text='Usada na consulta DPS quando a série for deixada em branco no portal. Ex.: 80000. Se vazio, o sistema usa 80000.',
    )
    nfse_nacional_dps_proximo_numero = models.PositiveBigIntegerField(
        verbose_name='Próximo número da DPS (portal nacional)',
        null=True,
        blank=True,
        help_text='Quando o número for deixado em branco no portal, usa este valor e avança +1 após cada tentativa que retornar nota (importada ou já existente). Vazio = começa em 1.',
    )
    nfse_adn_ultimo_nsu = models.PositiveBigIntegerField(
        verbose_name="ADN — último NSU integrado",
        null=True,
        blank=True,
        help_text=(
            "Controle da sincronização ADN por empresa. Em branco começa do NSU 0 "
            "(primeira carga). Depois da sincronização, o sistema atualiza automaticamente."
        ),
    )
    nfse_adn_data_ultima_sincronizacao = models.DateTimeField(
        verbose_name="ADN — data/hora da última sincronização",
        null=True,
        blank=True,
    )
    nfse_portal_nacional_login = models.CharField(
        verbose_name="Portal nacional (nfse.gov.br) — login",
        max_length=255,
        blank=True,
        default="",
        help_text=(
            "CPF, CNPJ ou e-mail usado em https://www.nfse.gov.br/EmissorNacional/Login (usuário/senha, certificado ou Gov.br). "
            "Referência para quem opera o navegador ou extensões de download; não substitui o certificado da API SEFIN."
        ),
    )
    nfse_portal_nacional_senha_cifrada = models.TextField(
        verbose_name="Portal nacional — senha (cifrada)",
        blank=True,
        default="",
        editable=False,
        help_text="Preenchida pelo formulário ao salvar (mesma criptografia da senha do PFX).",
    )
    nfse_xml_pasta_prestador = models.CharField(
        verbose_name='Pasta cópias XML NFSe (prestador)',
        max_length=500,
        blank=True,
        default='',
        help_text=(
            'Raiz quando a empresa é o prestador no XML. Subpastas: código externo-razão do tomador / '
            'competência (MMYYYY) / arquivo.xml. Vazio usa NFSE_XML_COPIA_PRESTADOR no servidor.'
        ),
    )
    nfse_xml_pasta_tomador = models.CharField(
        verbose_name='Pasta cópias XML NFSe (tomador)',
        max_length=500,
        blank=True,
        default='',
        help_text=(
            'Raiz quando a empresa é o tomador no XML. Subpastas: código externo-razão do prestador / '
            'competência (MMYYYY) / arquivo.xml. Vazio usa NFSE_XML_COPIA_TOMADOR no servidor.'
        ),
    )

    # API Sicoob — extrato (por empresa; senha cifrada com o mesmo Fernet do PFX NFSe).
    sicoob_client_id = models.CharField(
        verbose_name='Sicoob — Client ID (app no portal desenvolvedor)',
        max_length=80,
        blank=True,
        default='',
        help_text='Vazio usa SICOOB_CLIENT_ID do servidor.',
    )
    sicoob_chave_acesso = models.CharField(
        verbose_name='Sicoob — Chave de acesso (PJ) ou usuário (PF)',
        max_length=255,
        blank=True,
        default='',
        help_text='Enviada como username no token OAuth. Vazio usa SICOOB_CHAVE_ACESSO / SICOOB_USERNAME no servidor.',
    )
    sicoob_senha_cifrada = models.TextField(
        verbose_name='Sicoob — Senha (cifrada)',
        blank=True,
        default='',
        editable=False,
        help_text='Preenchida pelo formulário ao salvar.',
    )
    sicoob_client_secret_cifrada = models.TextField(
        verbose_name='Sicoob — Client Secret (cifrado)',
        blank=True,
        default='',
        editable=False,
        help_text='Opcional: apps confidenciais no portal. Preenchido pelo formulário ao salvar.',
    )
    sicoob_mtls_usar_pfx_nfse = models.BooleanField(
        verbose_name='Sicoob — mTLS com o mesmo PFX da NFS-e nacional',
        default=False,
        help_text=(
            'Se marcado, token e API de extrato Sicoob enviam o certificado cliente (mTLS) usando o '
            'mesmo arquivo .pfx e senha já cadastrados para a NFS-e nacional desta empresa.'
        ),
    )

    data_criacao = models.DateTimeField(verbose_name='Data de Criação', auto_now_add=True, null=True, blank=True)
    data_atualizacao = models.DateTimeField(verbose_name='Data de Atualização', auto_now=True, null=True, blank=True)

    class Meta:
        verbose_name = 'Empresa'
        verbose_name_plural = 'Empresas'
        ordering = ['razao']

    def __str__(self):
        return self.razao

    def nfse_nacional_caminho_pfx(self) -> str:
        """Caminho absoluto do .pfx: arquivo enviado ou caminho manual."""
        f = getattr(self, "nfse_nacional_pfx_arquivo", None)
        if f:
            try:
                if getattr(f, "name", None):
                    return f.path
            except (ValueError, NotImplementedError):
                pass
        return (self.nfse_nacional_pfx_path or "").strip()


class Socio(models.Model):
    """Sócio da empresa (QSA), vinculado ao cadastro de empresa."""
    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.CASCADE,
        related_name="socios",
        verbose_name="Empresa",
    )
    nome = models.CharField(verbose_name="Nome", max_length=255)
    qualificacao = models.CharField(
        verbose_name="Qualificação",
        max_length=255,
        blank=True,
        default="",
    )
    documento = models.CharField(
        verbose_name="CPF/CNPJ",
        max_length=20,
        blank=True,
        default="",
    )
    representante_legal = models.CharField(
        verbose_name="Representante Legal",
        max_length=255,
        blank=True,
        default="",
    )
    pais = models.CharField(
        verbose_name="País",
        max_length=100,
        blank=True,
        default="",
    )

    class Meta:
        verbose_name = "Sócio"
        verbose_name_plural = "Sócios"
        ordering = ["nome"]
        constraints = [
            models.UniqueConstraint(
                fields=["empresa", "nome", "qualificacao"],
                name="empresa_socio_uniq_empresa_nome_qualificacao",
            ),
        ]

    def __str__(self):
        return f"{self.nome} ({self.empresa.razao})"


class UsuarioEmpresa(models.Model):
    """Relacionamento entre usuário e empresa"""
    usuario = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='Usuário')
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, verbose_name='Empresa')
    ativo = models.BooleanField(verbose_name='Ativo', default=True)
    data_criacao = models.DateTimeField(verbose_name='Data de Criação', auto_now_add=True)
    
    class Meta:
        verbose_name = 'Usuário Empresa'
        verbose_name_plural = 'Usuários Empresas'
        unique_together = ['usuario', 'empresa']
        ordering = ['usuario', 'empresa']

    def __str__(self):
        return f"{self.usuario.username} - {self.empresa.razao}"