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

    def handle(self, *args, **options):
        convenios = [c.strip() for c in (options["convenios"] or []) if c and c.strip()]
        cab_ids = options["cabecalho_ids"] or []
        empresa_id = options["empresa_id"]
        dry = options["dry_run"] or not options["confirmar"]

        if not convenios and not cab_ids:
            raise CommandError(
                "Informe --convenio ADRIANA --convenio ABDES e/ou --cabecalho-id 6"
            )

        cabecalhos = Cabecalho.objects.filter(empresa_id=empresa_id).select_related(
            "convenio"
        )
        filtros = Q()
        if cab_ids:
            filtros |= Q(pk__in=cab_ids)
        for nome in convenios:
            filtros |= Q(convenio__nome__iexact=nome)

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

        with transaction.atomic():
            apagados, _ = TabelaPreco.objects.filter(
                cabecalho_id__in=cabecalhos.values_list("pk", flat=True)
            ).delete()

        self.stdout.write(self.style.SUCCESS(f"Apagados: {apagados} registro(s)."))
