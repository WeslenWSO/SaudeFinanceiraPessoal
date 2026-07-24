"""
Comando de depuração: valida Cobranca no banco e testa se forma_pagamento
é preenchido ao salvar NotaFiscalServico com discriminacao típica (PIX, CC AUT:...).
Uso: python manage.py debug_nfse_forma_pagamento
     NFS_IMPORT_DEBUG=1 python manage.py debug_nfse_forma_pagamento  # com logs detalhados
"""
import logging
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.utils import timezone
from cobranca.models import Cobranca
from empresa.models import Empresa
from notasfiscais.models import NotaFiscalServico

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Depuração: valida Cobranca e testa forma_pagamento na importação NFSe"

    def handle(self, *args, **options):
        self.stdout.write("=== DEBUG NFSe forma_pagamento ===\n")

        # D) Validar o banco: Cobranca
        count = Cobranca.objects.count()
        self.stdout.write(f"1) Cobranca.objects.count() = {count}")
        amostra = list(Cobranca.objects.values_list("id", "descricao", "tpag")[:50])
        self.stdout.write(f"2) Cobranca (id, descricao, tpag) até 50: {amostra}\n")

        empresa = Empresa.objects.first()
        if not empresa:
            self.stdout.write(self.style.ERROR("Nenhuma Empresa no banco. Crie uma empresa primeiro."))
            return

        # C) Teste rápido: criar nota com discriminacao PIX e outra com CC AUT
        discriminacoes = [
            ("Forma de pagamento: PIX", "DEBUG-PIX-1"),
            ("Forma de pagamento: CC AUT:123456", "DEBUG-CC-1"),
        ]
        resultados = []
        for discriminacao, numero_nota in discriminacoes:
            self.stdout.write(f"\n--- Teste: discriminacao={discriminacao[:50]}... ---")
            nfse = NotaFiscalServico(
                empresa=empresa,
                numero_nota=numero_nota,
                serie="1",
                data_emissao=timezone.now().date(),
                valor_bruto=Decimal("100.00"),
                valor_liquido=Decimal("100.00"),
                cliente="Cliente Teste Debug",
                cnpj_cpf="00000000000000",
                discriminacao=discriminacao,
            )
            forma_id_antes = getattr(nfse.forma_pagamento, "pk", None)
            nfse.save()
            forma_id_depois = getattr(nfse.forma_pagamento, "pk", None)
            nsu_depois = getattr(nfse, "nsu", None)
            self.stdout.write(
                f"  forma_pagamento_id antes save: {forma_id_antes}, depois save: {forma_id_depois}, nsu: {nsu_depois}"
            )
            resultados.append(
                {
                    "discriminacao": discriminacao[:60],
                    "numero_nota": numero_nota,
                    "forma_pagamento_id": forma_id_depois,
                    "nsu": nsu_depois,
                }
            )
            # Remove nota de teste para não poluir o banco
            nfse.delete()

        self.stdout.write("\n=== Resultado dos testes ===")
        for r in resultados:
            ok = "OK" if r["forma_pagamento_id"] else "FALHOU"
            self.stdout.write(
                f"  {r['numero_nota']}: forma_pagamento_id={r['forma_pagamento_id']}, nsu={r['nsu']} -> {ok}"
            )

        self.stdout.write("\n=== Relatório (responder no PR) ===")
        self.stdout.write("1) discriminacao vem preenchida? (ver logs NFS_IMPORT_DEBUG ou XML)")
        self.stdout.write("2) extract_payment_method_from_description retorna? (ver logs save())")
        self.stdout.write("3) _get_cobranca_by_forma_normalizada encontra Cobranca? (ver logs save())")
        self.stdout.write("4) Conflito de import Cobranca? (views: apenas cobranca.models)")
        self.stdout.write("5) save/update_fields/rollback impedindo? (ver exceção em gerar_contas_a_receber)")
        self.stdout.write(self.style.SUCCESS("\nComando concluído. Ative NFS_IMPORT_DEBUG=1 para logs detalhados."))
