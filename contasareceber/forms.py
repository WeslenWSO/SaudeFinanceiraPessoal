from django import forms
from django.utils import timezone
from .models import BaixaContaAReceber, ContaAReceber
from extrato.models import ContaBancaria, Lancamento


class EscolhaContaBaixaForm(forms.Form):
    """Uma conta a receber; a baixa com vários lançamentos de extrato fica em contasareceber:baixar."""

    conta = forms.ModelChoiceField(
        queryset=ContaAReceber.objects.none(),
        label='Conta a receber',
        required=True,
        help_text='Escolha um título. Na próxima tela você seleciona lançamentos do extrato e trata diferenças.',
        widget=forms.Select(attrs={'class': 'form-select', 'size': 12}),
    )

    def __init__(self, *args, empresa_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        if empresa_id:
            qs = (
                ContaAReceber.objects.filter(empresa_id=empresa_id, status__in=['pendente', 'vencido'])
                .select_related('nota')
                .order_by('data_vencimento', 'cliente')
            )
            self.fields['conta'].queryset = qs

        def label_conta(obj):
            nf = obj.nota.numero_nota if obj.nota else '—'
            return f'{obj.cliente} — NF {nf} — pend. R$ {obj.get_valor_pendente():.2f} — venc. {obj.data_vencimento:%d/%m/%Y}'

        self.fields['conta'].label_from_instance = label_conta


class BaixaContaIndividualForm(forms.ModelForm):
    """Formulário para baixa de uma única conta a receber"""

    # Campo para descrição do movimento
    descricao = forms.CharField(
        required=False,
        label="Descrição do Movimento",
        help_text="Descrição que aparecerá no extrato",
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )

    # Campo para seleção de lançamentos do extrato para conciliação
    lancamentos_extrato_ids = forms.CharField(
        required=False,
        label="IDs dos Lançamentos Selecionados",
        widget=forms.HiddenInput()
    )

    # Quando extrato ≠ baixa: igual | juros_desconto | nova_conta | outro_extrato (preenchido via JS)
    resolucao_diferenca_extrato = forms.CharField(
        required=False,
        initial='igual',
        widget=forms.HiddenInput(),
    )

    class Meta:
        model = BaixaContaAReceber
        fields = [
            'data_recebimento', 'valor_recebido', 'desconto', 'juros', 'tarifas',
            'conta_banco', 'tipo_baixa', 'observacao'
        ]
        widgets = {
            'data_recebimento': forms.DateInput(attrs={'type': 'date'}),
            'observacao': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        empresa_id = kwargs.pop('empresa_id', None)
        conta = kwargs.pop('conta', None)
        conta_banco_id = kwargs.pop('conta_banco_id', None)
        data_inicio = kwargs.pop('data_inicio', None)
        data_fim = kwargs.pop('data_fim', None)
        super().__init__(*args, **kwargs)

        if empresa_id:
            # Filtra contas bancárias da empresa
            self.fields['conta_banco'].queryset = ContaBancaria.objects.filter(
                empresa_id=empresa_id,
                status='A'
            )

        # Define lançamentos disponíveis baseado na conta bancária selecionada
        # Primeiro tenta conta_banco_id passado, senão tenta do data do form
        conta_banco_id_to_use = conta_banco_id
        if not conta_banco_id_to_use and self.data:
            conta_banco_id_to_use = self.data.get('conta_banco')

        if conta_banco_id_to_use and empresa_id:
            try:
                conta_banco = ContaBancaria.objects.get(id=conta_banco_id_to_use, empresa_id=empresa_id)
                # Busca lançamentos não conciliados da conta bancária baseado em agencia e conta
                lancamentos_query = Lancamento.objects.filter(
                    empresa_id=empresa_id,
                    conta__agencia=conta_banco.agencia,
                    conta__conta=conta_banco.conta,
                    conciliado=False
                )

                # Aplicar filtros de período se fornecidos
                if data_inicio:
                    lancamentos_query = lancamentos_query.filter(data__gte=data_inicio)
                if data_fim:
                    lancamentos_query = lancamentos_query.filter(data__lte=data_fim)

                # Removido: self.fields['lancamentos_extrato'].queryset = lancamentos_query.order_by('-data')
            except ContaBancaria.DoesNotExist:
                pass
        else:
            # Removido: self.fields['lancamentos_extrato'].queryset = Lancamento.objects.none()
            pass

        # Define valores padrão
        if not self.instance.pk:
            self.fields['data_recebimento'].initial = timezone.now().date()
            if conta:
                # Saldo nominal (parcela − já recebido), não o líquido já ajustado na conta.
                self.fields['valor_recebido'].initial = conta.get_saldo_nominal_pendente()
                self.fields['valor_recebido'].help_text = (
                    'Total líquido do título: se já recebido = valor recebido; se não = valor a receber − tarifa − desconto + juros. '
                    'Na baixa (em aberto): saldo nominal − tarifa − desconto + juros = valor recebido (ex.: 350−100−0+0=250). '
                    'Com extrato, o valor recebido costuma ser o líquido creditado. Conciliação: extrato vs valor recebido + juros − desconto.'
                )
                self.fields['tipo_baixa'].initial = 'total'

                # Gera descrição pré-preenchida
                numero_nota = conta.nota.numero_nota if conta.nota else "Sem Nota"
                parcela = conta.parcela if conta.parcela else "1/1"
                descricao = f"VLR REF A NF {numero_nota} - {parcela} - {conta.cliente}"
                self.fields['descricao'].initial = descricao