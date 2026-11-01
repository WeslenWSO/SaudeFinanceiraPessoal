"""Replica preços entre cabeçalhos (CLI)."""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from servicos_medicos.models import Cabecalho
from servicos_medicos.replicar_tabela_preco import replicar_tabela_preco


class Command(BaseCommand):
    help = "Copia exames/preços de um cabeçalho para outro (mesma empresa)."

    def add_arguments(self, parser):
        parser.add_argument("--origem-id", type=int, required=True)
        parser.add_argument("--destino-id", type=int, required=True)
        parser.add_argument(
            "--nao-atualizar",
            action="store_true",
            help="Não alterar linhas que já existem no destino",
        )

    def handle(self, *args, **options):
        origem = Cabecalho.objects.filter(pk=options["origem_id"]).first()
        destino = Cabecalho.objects.filter(pk=options["destino_id"]).first()
        if not origem or not destino:
            raise CommandError("Cabeçalho origem ou destino não encontrado.")

        try:
            r = replicar_tabela_preco(
                origem,
                destino,
                atualizar_existentes=not options["nao_atualizar"],
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"Origem: {r.total_origem} | criados: {r.criados} | "
                f"atualizados: {r.atualizados} | pulados: {r.pulados}"
            )
        )
