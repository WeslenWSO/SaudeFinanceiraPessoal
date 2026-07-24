from django import forms
from .models import Lancamento, ExtratoArquivo, ContaBancaria, Banco

class LancamentoForm(forms.ModelForm):
    class Meta:
        model = Lancamento
        fields = ["conta", "banco", "fitid", "data", "documento", "historico", "valor", "saldo", "conciliado", "idconciliacao"]

    def __init__(self, *args, **kwargs):
        empresa_id = kwargs.pop('empresa_id', None)
        super().__init__(*args, **kwargs)

        if empresa_id:
            from empresa.models import Empresa
            
            try:
                empresa_logada = Empresa.objects.get(id=empresa_id)
                # Substituir o campo por um readonly text input
                self.fields['empresa'] = forms.CharField(
                    label="Empresa",
                    initial=empresa_logada,
                    widget=forms.TextInput(attrs={'readonly': True, 'class': 'form-control'}),
                    required=False
                )
                # Definir a empresa na instância se for novo registro
                if not self.instance.pk:
                    self.instance.empresa = empresa_logada

                # Filtrar contas bancárias apenas da empresa logada
                contas_empresa = ContaBancaria.objects.filter(
                    empresa_id=empresa_id,
                    status='A'  # Apenas contas ativas
                ).order_by('banco__nome')
                self.fields['conta'].queryset = contas_empresa

                # Filtrar bancos apenas dos que têm contas ativas na empresa
                bancos_empresa = set()
                for conta in contas_empresa:
                    if hasattr(conta, 'banco'):
                        bancos_empresa.add(conta.banco)
                    elif hasattr(conta, 'nomebanco'):
                        # Se a conta tem nomebanco em vez de relacionamento banco
                        from .models import Banco
                        try:
                            banco = Banco.objects.get(nome=conta.nomebanco)
                            bancos_empresa.add(banco)
                        except Banco.DoesNotExist:
                            pass

                if bancos_empresa:
                    self.fields['banco'].queryset = self.fields['banco'].queryset.filter(
                        id__in=[b.id for b in bancos_empresa]
                    )

            except Empresa.DoesNotExist:
                pass

class UploadOFXForm(forms.ModelForm):
    class Meta:
        model = ExtratoArquivo
        fields = ["conta", "arquivo"]

    def __init__(self, *args, **kwargs):
        empresa_id = kwargs.pop('empresa_id', None)
        super().__init__(*args, **kwargs)

        if empresa_id:
            # Filtrar contas bancárias apenas da empresa logada
            contas_empresa = ContaBancaria.objects.filter(
                empresa_id=empresa_id,
                status='A'
            ).order_by('banco__nome')
            self.fields['conta'].queryset = contas_empresa

    def clean(self):
        cleaned = super().clean()
        cleaned["tipo"] = "OFX"
        return cleaned

class UploadPDFForm(forms.ModelForm):
    class Meta:
        model = ExtratoArquivo
        fields = ["conta", "arquivo"]

    def __init__(self, *args, **kwargs):
        empresa_id = kwargs.pop('empresa_id', None)
        super().__init__(*args, **kwargs)

        if empresa_id:
            # Filtrar contas bancárias apenas da empresa logada
            contas_empresa = ContaBancaria.objects.filter(
                empresa_id=empresa_id,
                status='A'
            ).order_by('banco__nome')
            self.fields['conta'].queryset = contas_empresa

    def clean(self):
        cleaned = super().clean()
        cleaned["tipo"] = "PDF"
        return cleaned

class ContaBancariaForm(forms.ModelForm):
    class Meta:
        model = ContaBancaria
        fields = [
            "banco",
            "agencia",
            "conta",
            "tipo",
            "status",
            "conta_contabil",
            "descricao",
            "saldo_inicial",
            "data_inicial_saldo",
            "sicoob_numero_conta_corrente_api",
        ]

    def __init__(self, *args, **kwargs):
        empresa_id = kwargs.pop("empresa_id", None)
        super().__init__(*args, **kwargs)
        if empresa_id:
            self.fields["banco"].queryset = Banco.objects.all().order_by("nome")
            if not self.instance.pk:
                from empresa.models import Empresa
                try:
                    self.instance.empresa = Empresa.objects.get(id=empresa_id)
                except Empresa.DoesNotExist:
                    pass


class TransferenciaForm(forms.Form):
    """Formulário para transferência baseada em lançamento do extrato bancário"""
    conta_destino = forms.ModelChoiceField(
        queryset=ContaBancaria.objects.none(),
        label="Conta de Destino",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    def __init__(self, *args, **kwargs):
        empresa_id = kwargs.pop('empresa_id', None)
        lancamento = kwargs.pop('lancamento', None)
        super().__init__(*args, **kwargs)

        if empresa_id and lancamento:
            # Filtrar contas ativas da empresa, excluindo a conta de origem (do lançamento)
            contas_ativas = ContaBancaria.objects.filter(
                empresa_id=empresa_id,
                status='A'
            ).exclude(id=lancamento.conta.id)  # Excluir a conta de origem
            self.fields['conta_destino'].queryset = contas_ativas

    def clean(self):
        cleaned_data = super().clean()
        conta_destino = cleaned_data.get('conta_destino')

        if not conta_destino:
            raise forms.ValidationError("Selecione uma conta de destino.")

        return cleaned_data
