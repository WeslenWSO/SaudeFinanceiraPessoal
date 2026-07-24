from django import forms
from django.core.exceptions import ValidationError

from .cnpj_utils import limpar_cnpj, limpar_cep, limpar_telefone_br
from .models import Fornecedor

_W = "form-control"
_S = "form-select"


class FornecedorForm(forms.ModelForm):
    class Meta:
        model = Fornecedor
        fields = [
            "empresa",
            "cnpj",
            "razao",
            "codigo_externo",
            "nome_fantasia",
            "telefone",
            "atividades_cnae",
            "natureza_juridica",
            "porte",
            "data_abertura",
            "situacao_cadastral",
            "data_situacao_cadastral",
            "cidade_uf",
            "cep",
            "logradouro",
            "numero",
            "complemento",
            "bairro",
            "endereco_eletronico",
            "descricao_extrato_bancario",
        ]
        widgets = {
            "empresa": forms.Select(attrs={"class": _S}),
            "cnpj": forms.TextInput(
                attrs={
                    "class": _W,
                    "placeholder": "CNPJ 14 ou CPF 11 dígitos (só números)",
                    "autocomplete": "off",
                    "inputmode": "numeric",
                }
            ),
            "razao": forms.TextInput(attrs={"class": _W}),
            "codigo_externo": forms.TextInput(
                attrs={"class": _W, "placeholder": "Código para pasta ao salvar XML NFSe (tomador)", "autocomplete": "off"}
            ),
            "nome_fantasia": forms.TextInput(attrs={"class": _W}),
            "telefone": forms.TextInput(
                attrs={
                    "class": _W,
                    "placeholder": "DDD + número (só dígitos, até 11)",
                    "inputmode": "numeric",
                }
            ),
            "atividades_cnae": forms.Textarea(
                attrs={"class": _W, "rows": 5, "placeholder": "Um CNAE por linha (preenchido pela API)"}
            ),
            "natureza_juridica": forms.TextInput(attrs={"class": _W}),
            "porte": forms.TextInput(attrs={"class": _W}),
            "data_abertura": forms.DateInput(attrs={"class": _W, "type": "date"}),
            "situacao_cadastral": forms.TextInput(attrs={"class": _W}),
            "data_situacao_cadastral": forms.DateInput(attrs={"class": _W, "type": "date"}),
            "cidade_uf": forms.TextInput(attrs={"class": _W}),
            "cep": forms.TextInput(
                attrs={
                    "class": _W,
                    "placeholder": "8 dígitos (na lista aparece 00000-000)",
                    "inputmode": "numeric",
                }
            ),
            "logradouro": forms.TextInput(attrs={"class": _W}),
            "numero": forms.TextInput(attrs={"class": _W}),
            "complemento": forms.TextInput(attrs={"class": _W}),
            "bairro": forms.TextInput(attrs={"class": _W}),
            "endereco_eletronico": forms.EmailInput(attrs={"class": _W}),
            "descricao_extrato_bancario": forms.TextInput(
                attrs={
                    "class": _W,
                    "placeholder": "Ex.: nome fantasia ou abreviação como no banco",
                    "autocomplete": "off",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["empresa"].disabled = True
        for name in self.fields:
            if name != "empresa":
                self.fields[name].required = False
        self.fields["razao"].required = True
        self.fields["cnpj"].required = True

    def clean_cnpj(self):
        raw = self.cleaned_data.get("cnpj", "")
        limpo = limpar_cnpj(raw)
        if len(limpo) not in (11, 14):
            raise ValidationError(
                "Informe CPF com 11 dígitos ou CNPJ com 14 dígitos (apenas números)."
            )
        return limpo

    def clean_cep(self):
        return limpar_cep(self.cleaned_data.get("cep", ""))

    def clean_telefone(self):
        return limpar_telefone_br(self.cleaned_data.get("telefone", ""))

    def clean(self):
        cleaned_data = super().clean()
        cnpj = cleaned_data.get("cnpj")
        empresa = cleaned_data.get("empresa")
        if not empresa and self.instance and self.instance.pk and self.instance.empresa_id:
            empresa = self.instance.empresa
        if not empresa and self.initial.get("empresa"):
            from empresa.models import Empresa

            try:
                empresa = Empresa.objects.get(pk=self.initial["empresa"])
            except (Empresa.DoesNotExist, TypeError, ValueError):
                empresa = None
        if cnpj and empresa:
            qs = Fornecedor.objects.filter(empresa=empresa, cnpj=cnpj)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise ValidationError(
                    {
                        "cnpj": "Já existe um fornecedor com este CNPJ cadastrado para esta empresa.",
                    }
                )
        return cleaned_data
