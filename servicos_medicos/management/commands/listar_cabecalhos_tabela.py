"""Lista cabeçalhos de tabela de preço (com contagem de itens) para escolher --cabecalho-id."""
from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db.models import Count

from servicos_medicos.models import Cabecalho


class Command(BaseCommand):
    help = "Lista cabeçalhos de preço (id, convênio, nome, quantidade de linhas)."

    def add_arguments(self, parser):
        parser.add_argument("--empresa-id", type=int, default=1)
        parser.add_argument("--convenio", default="", help="Filtro parcial no nome do convênio")
        parser.add_argument("--tabela", default="", help="Filtro parcial no nome do cabeçalho")

    def handle(self, *args, **options):
        qs = Cabecalho.objects.filter(empresa_id=options["empresa_id"])
        if options["convenio"].strip():
            qs = qs.filter(convenio__nome__icontains=options["convenio"].strip())
        if options["tabela"].strip():
            qs = qs.filter(nome_tabela__icontains=options["tabela"].strip())
        qs = qs.select_related("convenio").annotate(n=Count("tabelapreco")).order_by(
            "convenio__nome", "nome_tabela"
        )
        if not qs.exists():
            self.stdout.write("Nenhum cabeçalho encontrado.")
            return
        for cab in qs:
            self.stdout.write(
                f"id={cab.pk}\t{cab.convenio.nome}\t«{cab.nome_tabela}»\t{cab.n} preços"
            )
