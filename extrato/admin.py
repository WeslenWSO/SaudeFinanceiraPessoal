from django.contrib import admin
from django import forms
from .models import Empresa, Banco, ContaBancaria, ExtratoArquivo, Lancamento, Conciliacao, ExtratoMovimento


class ExtratoMovimentoForm(forms.ModelForm):
    class Meta:
        model = ExtratoMovimento
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Filtrar conta_banco para apenas contas existentes
        self.fields['conta_banco'].queryset = ContaBancaria.objects.all()

    def clean_conta_banco(self):
        conta_banco = self.cleaned_data.get('conta_banco')
        if conta_banco and not ContaBancaria.objects.filter(id=conta_banco.id).exists():
            raise forms.ValidationError("Conta bancária selecionada não existe.")
        return conta_banco


@admin.register(Banco)
class BancoAdmin(admin.ModelAdmin):
    search_fields = ["nome"]

@admin.register(ContaBancaria)
class ContaBancariaAdmin(admin.ModelAdmin):
    list_display = ["__str__", "empresa", "banco", "tipo", "agencia", "conta", "descricao", "status"]
    list_filter = ["status", "empresa", "banco", "tipo"]
    search_fields = ["empresa__razao", "empresa__nome_fantasia", "banco__nome", "agencia", "conta"]

@admin.register(ExtratoArquivo)
class ExtratoArquivoAdmin(admin.ModelAdmin):
    list_display = ["conta", "tipo", "periodo_inicio", "periodo_fim", "enviado_em"]
    list_filter = ["tipo", "conta__empresa", "conta__banco"]

@admin.register(Lancamento)
class LancamentoAdmin(admin.ModelAdmin):
    list_display = ["data", "empresa", "conta", "historico", "valor", "conciliado", "idconciliacao"]
    list_filter = ["empresa", "conta", "conciliado", "origem", "data"]
    search_fields = ["historico", "documento", "hash_unico"]

@admin.register(Conciliacao)
class ConciliacaoAdmin(admin.ModelAdmin):
    list_display = ["id", "criado_em", "criado_por", "observacao"]
    search_fields = ["id", "observacao"]

@admin.register(ExtratoMovimento)
class ExtratoMovimentoAdmin(admin.ModelAdmin):
    list_display = ["data_baixa", "empresa", "descricao", "situacao", "valor", "saldo"]
    list_filter = ["empresa", "situacao", "data_baixa"]
    search_fields = ["descricao", "empresa__razao", "empresa__nome_fantasia"]

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'conta_banco':
            kwargs['queryset'] = ContaBancaria.objects.all()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)
