"""Remove linhas de TabelaPreco por convênio ou id de cabeçalho."""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from servicos_medicos.models import Cabecalho, TabelaPreco


class Command(BaseCommand):
    help = (
        "Apaga preços (TabelaPreco) de cabeçalhos/convênios. "
        "Não remove ServicosMedicos nem o cadastro de Cabeçalho."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--convenio",
            action="append",
            dest="convenios",
            metavar="NOME",
            help="Nome do convênio (pode repetir). Ex.: --convenio ADRIANA --convenio ABDES",
        )
        parser.add_argument(
            "--cabecalho-nome",
            action="append",
            dest="cabecalho_nomes",
            metavar="NOME",
            help=(
                "Nome do cabeçalho (nome_tabela). Com --convenio, restringe a esse par. "
                'Ex.: --convenio "REAL CONVÊNIOS" --cabecalho-nome "TABELA - REAL"'
            ),
        )
        parser.add_argument(
            "--cabecalho-id",
            action="append",
            dest="cabecalho_ids",
            type=int,
            metavar="ID",
            help="Id do cabeçalho (lista de Cabeçalhos). Ex.: --cabecalho-id 6",
        )
        parser.add_argument(
            "--empresa-id",
            type=int,
            default=1,
            help="Filtrar cabeçalhos/preços da empresa (padrão: 1 Medicinarte)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Só mostra quantos registros seriam apagados",
        )
        parser.add_argument(
            "--confirmar",
            action="store_true",
            help="Obrigatório para apagar de verdade (sem isso, só dry-run implícito)",
        )
        parser.add_argument(
            "--remover-cabecalho",
            action="store_true",
            help="Após apagar os preços, remove também o cadastro do Cabeçalho",
        )
        parser.add_argument(
            "--id",
            action="append",
            dest="cabecalho_ids",
            type=int,
            metavar="ID",
            help="Atalho: mesmo que --cabecalho-id",
        )

    def handle(self, *args, **options):
        convenios = [c.strip() for c in (options["convenios"] or []) if c and c.strip()]
        cab_nomes = [c.strip() for c in (options["cabecalho_nomes"] or []) if c and c.strip()]
        cab_ids = options["cabecalho_ids"] or []
        empresa_id = options["empresa_id"]
        dry = options["dry_run"] or not options["confirmar"]
        remover_cabecalho = options["remover_cabecalho"]

        if not convenios and not cab_ids and not cab_nomes:
            raise CommandError(
                "Informe --convenio, --cabecalho-nome e/ou --cabecalho-id "
                '(ex.: --convenio "REAL CONVÊNIOS" --cabecalho-nome "TABELA - REAL")'
            )

        cabecalhos = Cabecalho.objects.filter(empresa_id=empresa_id).select_related(
            "convenio"
        )
        filtros = Q()
        if cab_ids:
            filtros |= Q(pk__in=cab_ids)
        if convenios and cab_nomes:
            for conv in convenios:
                for cab_nome in cab_nomes:
                    filtros |= Q(
                        convenio__nome__iexact=conv,
                        nome_tabela__iexact=cab_nome,
                    )
        elif convenios:
            for nome in convenios:
                filtros |= Q(convenio__nome__iexact=nome)
        elif cab_nomes:
            for cab_nome in cab_nomes:
                filtros |= Q(nome_tabela__iexact=cab_nome)

        cabecalhos = cabecalhos.filter(filtros).order_by("convenio__nome", "nome_tabela")
        if not cabecalhos.exists():
            raise CommandError(
                f"Nenhum cabeçalho encontrado (empresa_id={empresa_id}, "
                f"convênios={convenios!r}, ids={cab_ids!r})."
            )

        total = 0
        for cab in cabecalhos:
            n = TabelaPreco.objects.filter(cabecalho_id=cab.pk).count()
            total += n
            self.stdout.write(
                f"  Cabeçalho id={cab.pk} | {cab.convenio.nome} — {cab.nome_tabela} | "
                f"{n} preço(s)"
            )

        self.stdout.write(f"Total: {total} linha(s) de TabelaPreco.")

        if dry:
            self.stdout.write(
                self.style.WARNING(
                    "Nada foi apagado. Use --confirmar (ou --dry-run só para simular)."
                )
            )
            return

        if total == 0:
            self.stdout.write("Nada a apagar.")
            return

        cab_pk_list = list(cabecalhos.values_list("pk", flat=True))
        with transaction.atomic():
            apagados, _ = TabelaPreco.objects.filter(cabecalho_id__in=cab_pk_list).delete()
            if remover_cabecalho:
                Cabecalho.objects.filter(pk__in=cab_pk_list).delete()

        self.stdout.write(self.style.SUCCESS(f"Apagados: {apagados} registro(s) de TabelaPreco."))
        if remover_cabecalho:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Cabeçalho(s) removido(s): {len(cab_pk_list)} "
                    f"(cadastro «Cabeçalho» excluído do combo)."
                )
            )
