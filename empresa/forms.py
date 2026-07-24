import re
from datetime import date

from django import forms
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.db.models.fields.files import FieldFile

from .models import Empresa
from .nfse_nacional_crypto import criptografar_senha_pfx, descriptografar_senha_pfx
from .nfse_nacional_pfx import extrair_validade_pfx_bytes

# Sentinel: não alterar ``nfse_nacional_cert_validade`` ao salvar.
_NFSE_MANTER_VALIDADE_CERT = object()


def _limpar_cnpj(val):
    """Retorna apenas os dígitos do CNPJ."""
    if not val:
        return ""
    return re.sub(r"\D", "", str(val).strip())


class EmpresaForm(forms.ModelForm):
    class Meta:
        model = Empresa
        fields = [
            "cnpj",
            "razao",
            "nome_fantasia",
            "codigo_externo",
            "status",
            "regime_tributario",
            "anexo_i",
            "anexo_ii",
            "anexo_iii",
            "anexo_iv",
            "anexo_v",
            "tem_fator_r",
            "tipo_apuracao",
            "usa_base_calculo_reduzido",
            "utiliza_iss_fixo",
        ]
        widgets = {
            'razao': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Razão Social'
            }),
            'nome_fantasia': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Nome Fantasia'
            }),
            'cnpj': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '00.000.000/0000-00',
                'autocomplete': 'off',
                'maxlength': '18',
            }),
            'codigo_externo': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Código externo'
            }),
            'status': forms.Select(attrs={
                'class': 'form-select'
            }, choices=[
                ('Ativa', 'Ativa'),
                ('Inativa', 'Inativa')
            ]),
            'regime_tributario': forms.Select(attrs={
                'class': 'form-select',
                'id': 'id_regime_tributario'
            }),
            'anexo_i': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
                'id': 'id_anexo_i'
            }),
            'tem_fator_r': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
                'id': 'id_tem_fator_r'
            }),
            'tipo_apuracao': forms.Select(attrs={
                'class': 'form-select'
            }),
            'usa_base_calculo_reduzido': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
            'utiliza_iss_fixo': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["cnpj"].widget.attrs["maxlength"] = 18

    def clean_cnpj(self):
        """Aceita CNPJ com pontos e barra; grava apenas dígitos. Não permite CNPJ já cadastrado."""
        cnpj = self.cleaned_data.get("cnpj")
        if cnpj is None:
            return cnpj
        limpo = _limpar_cnpj(cnpj)
        if limpo and len(limpo) not in (11, 14):
            raise forms.ValidationError("Informe CNPJ com 14 dígitos ou CPF com 11 dígitos (somente números).")
        cnpj_final = limpo if limpo else cnpj

        # Não permitir salvar se já existir empresa com este documento
        if len(cnpj_final) in (11, 14):
            qs = Empresa.objects.filter(cnpj=cnpj_final)
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError(
                    "Já existe uma empresa cadastrada no sistema com este CNPJ/CPF. Não é possível salvar."
                )

        return cnpj_final


class EmpresaIntegracaoForm(forms.ModelForm):
    """NFS-e nacional (SEFIN), cópias XML, portal e API Sicoob — tela dedicada."""

    nfse_nacional_pfx_senha = forms.CharField(
        label="Senha do arquivo .pfx",
        required=False,
        widget=forms.PasswordInput(
            render_value=False,
            attrs={"class": "form-control", "autocomplete": "new-password", "placeholder": "Deixe em branco para não alterar"},
        ),
        help_text="Ao enviar o .pfx com a senha correta, a validade do certificado é gravada automaticamente.",
    )
    sicoob_senha = forms.CharField(
        label="Sicoob — Senha do cooperado",
        required=False,
        widget=forms.PasswordInput(
            render_value=False,
            attrs={
                "class": "form-control",
                "autocomplete": "new-password",
                "placeholder": "Deixe em branco para não alterar a senha gravada",
            },
        ),
        help_text="PJ: senha da chave de acesso no canal digital. Gravada cifrada. Vazio mantém a senha já salva (se houver).",
    )
    sicoob_client_secret = forms.CharField(
        label="Sicoob — Client Secret (app no portal)",
        required=False,
        widget=forms.PasswordInput(
            render_value=False,
            attrs={
                "class": "form-control font-monospace",
                "autocomplete": "new-password",
                "placeholder": "Obrigatório se o app for confidencial — vazio mantém o gravado",
            },
        ),
        help_text="Mesmo Client Secret exibido no Dashboard do Portal Developers. Gravado cifrado. "
        "Se o token retornar HTTP 403, inclua este campo ou defina SICOOB_CLIENT_SECRET no servidor.",
    )
    nfse_portal_nacional_senha = forms.CharField(
        label="Portal nacional (site) — senha",
        required=False,
        widget=forms.PasswordInput(
            render_value=False,
            attrs={
                "class": "form-control",
                "autocomplete": "new-password",
                "placeholder": "Deixe em branco para não alterar a senha gravada",
            },
        ),
        help_text=(
            "Senha do acesso em https://www.nfse.gov.br/EmissorNacional/Login (usuário/senha ou Gov.br). "
            "Gravada cifrada. Não é a senha do certificado .pfx."
        ),
    )

    class Meta:
        model = Empresa
        fields = [
            "nfse_nacional_base_url",
            "nfse_nacional_pfx_arquivo",
            "nfse_nacional_thumbprint_sha1",
            "nfse_nacional_codigo_ibge_municipio",
            "nfse_nacional_dps_serie_padrao",
            "nfse_nacional_dps_proximo_numero",
            "nfse_adn_ultimo_nsu",
            "nfse_xml_pasta_prestador",
            "nfse_xml_pasta_tomador",
            "nfse_portal_nacional_login",
            "sicoob_client_id",
            "sicoob_chave_acesso",
            "sicoob_mtls_usar_pfx_nfse",
        ]
        widgets = {
            "nfse_nacional_base_url": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Vazio = URL do servidor (NFSE_NACIONAL_BASE_URL)",
                }
            ),
            "nfse_nacional_pfx_arquivo": forms.ClearableFileInput(
                attrs={
                    "class": "form-control",
                    "accept": ".pfx,.p12,application/x-pkcs12",
                }
            ),
            "nfse_nacional_thumbprint_sha1": forms.TextInput(
                attrs={
                    "class": "form-control font-monospace text-uppercase",
                    "placeholder": "Opcional — preenchido pela busca no Windows",
                    "maxlength": "40",
                }
            ),
            "nfse_nacional_codigo_ibge_municipio": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "7 dígitos — ex.: 1200401",
                    "maxlength": "7",
                    "inputmode": "numeric",
                    "autocomplete": "off",
                }
            ),
            "nfse_nacional_dps_serie_padrao": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Ex.: 80000 — usado no portal se série em branco",
                    "maxlength": "8",
                    "inputmode": "numeric",
                    "autocomplete": "off",
                }
            ),
            "nfse_nacional_dps_proximo_numero": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Vazio = 1 na primeira consulta automática",
                    "min": "1",
                }
            ),
            "nfse_adn_ultimo_nsu": forms.NumberInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Vazio = iniciar do NSU 0",
                    "min": "0",
                    "step": "1",
                }
            ),
            "nfse_xml_pasta_prestador": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Ex.: D:\\NFSe\\Emitidas — vazio = variável NFSE_XML_COPIA_PRESTADOR",
                    "autocomplete": "off",
                }
            ),
            "nfse_xml_pasta_tomador": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Ex.: D:\\NFSe\\Recebidas — vazio = variável NFSE_XML_COPIA_TOMADOR",
                    "autocomplete": "off",
                }
            ),
            "nfse_portal_nacional_login": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "CPF, CNPJ ou e-mail (login em EmissorNacional/Login)",
                    "autocomplete": "username",
                }
            ),
            "sicoob_client_id": forms.TextInput(
                attrs={
                    "class": "form-control font-monospace",
                    "placeholder": "UUID do app no portal Sicoob — vazio = variável do servidor",
                    "spellcheck": "false",
                }
            ),
            "sicoob_chave_acesso": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "PJ: chave de acesso · PF: usuário (ex. CPF)",
                    "autocomplete": "off",
                }
            ),
            "sicoob_mtls_usar_pfx_nfse": forms.CheckboxInput(
                attrs={"class": "form-check-input", "id": "id_sicoob_mtls_usar_pfx_nfse"}
            ),
        }

    def clean_nfse_nacional_codigo_ibge_municipio(self):
        raw = (self.cleaned_data.get("nfse_nacional_codigo_ibge_municipio") or "").strip()
        if not raw:
            return ""
        d = re.sub(r"\D", "", raw)
        if len(d) != 7:
            raise forms.ValidationError("Informe exatamente 7 dígitos do código IBGE do município.")
        return d

    def clean_nfse_adn_ultimo_nsu(self):
        nsu = self.cleaned_data.get("nfse_adn_ultimo_nsu")
        if nsu is None:
            return None
        if int(nsu) < 0:
            raise forms.ValidationError("NSU não pode ser negativo.")
        return int(nsu)

    def clean(self):
        cleaned = super().clean()
        senha_form = (cleaned.get("nfse_nacional_pfx_senha") or "").strip()

        senha_efetiva = senha_form
        if not senha_efetiva and getattr(self.instance, "pk", None):
            senha_efetiva = descriptografar_senha_pfx(
                getattr(self.instance, "nfse_nacional_pfx_senha_cifrada", "") or ""
            ).strip()

        arquivo_field = cleaned.get("nfse_nacional_pfx_arquivo")
        has_new_upload = isinstance(arquivo_field, UploadedFile) and bool(getattr(arquivo_field, "name", None))
        arquivo_limpo = arquivo_field is False
        tem_arquivo_salvo = isinstance(arquivo_field, FieldFile) and bool(arquivo_field.name)

        if has_new_upload:
            if not senha_efetiva:
                raise ValidationError(
                    {
                        "nfse_nacional_pfx_senha": "Informe a senha do PFX para validar o certificado enviado."
                    }
                )
            dados = b"".join(arquivo_field.chunks())
            validade = extrair_validade_pfx_bytes(dados, senha_efetiva)
            if validade is None:
                raise ValidationError(
                    {
                        "nfse_nacional_pfx_arquivo": "Não foi possível abrir o PFX (arquivo inválido ou senha incorreta)."
                    }
                )
            cleaned["_nfse_validade_computada"] = validade
            cleaned["_nfse_enviou_arquivo"] = True
        elif arquivo_limpo:
            cleaned["_nfse_validade_computada"] = None
        elif tem_arquivo_salvo:
            cleaned["_nfse_validade_computada"] = _NFSE_MANTER_VALIDADE_CERT
        else:
            cleaned["_nfse_validade_computada"] = None

        return cleaned

    def save(self, commit=True):
        obj = super().save(commit=False)
        if self.cleaned_data.get("_nfse_enviou_arquivo"):
            obj.nfse_nacional_pfx_path = ""
        senha = (self.cleaned_data.get("nfse_nacional_pfx_senha") or "").strip()
        if senha:
            obj.nfse_nacional_pfx_senha_cifrada = criptografar_senha_pfx(senha)
        vd = self.cleaned_data.get("_nfse_validade_computada")
        if vd is _NFSE_MANTER_VALIDADE_CERT:
            pass
        elif isinstance(vd, date):
            obj.nfse_nacional_cert_validade = vd
        else:
            obj.nfse_nacional_cert_validade = None
        senha_sicoob = (self.cleaned_data.get("sicoob_senha") or "").strip()
        if senha_sicoob:
            obj.sicoob_senha_cifrada = criptografar_senha_pfx(senha_sicoob)
        cs_sicoob = (self.cleaned_data.get("sicoob_client_secret") or "").strip()
        if cs_sicoob:
            obj.sicoob_client_secret_cifrada = criptografar_senha_pfx(cs_sicoob)
        senha_portal = (self.cleaned_data.get("nfse_portal_nacional_senha") or "").strip()
        if senha_portal:
            obj.nfse_portal_nacional_senha_cifrada = criptografar_senha_pfx(senha_portal)
        if commit:
            obj.save()
        return obj
