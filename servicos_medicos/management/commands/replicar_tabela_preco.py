"""Replica preços entre cabeçalhos (CLI)."""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from servicos_medicos.models import Cabecalho
from servicos_medicos.replicar_tabela_preco import (
    contagem_faltantes_no_destino,
    contagem_linhas_origem,
    replicar_tabela_preco,
)


class Command(BaseCommand):
    help = "Copia exames/preços de um cabeçalho para outro (mesma empresa)."

    def add_arguments(self, parser):
        parser.add_argument("--origem-id", type=int, required=True)
        parser.add_argument("--destino-id", type=int, required=True)
        parser.add_argument(
            "--atualizar-existentes",
            action="store_true",
            help="Atualizar preços que já existem no destino (padrão: só incluir os que faltam)",
        )
        parser.add_argument(
            "--nao-atualizar",
            action="store_true",
            help="(Obsoleto) Mesmo efeito do padrão — só serviços faltantes",
        )

    def handle(self, *args, **options):
        origem = Cabecalho.objects.filter(pk=options["origem_id"]).first()
        destino = Cabecalho.objects.filter(pk=options["destino_id"]).first()
        if not origem or not destino:
            raise CommandError("Cabeçalho origem ou destino não encontrado.")

        n_origem = contagem_linhas_origem(origem)
        self.stdout.write(
            f"Origem id={origem.pk} ({origem.convenio} — {origem.nome_tabela}): "
            f"{n_origem} preço(s) detectado(s)."
        )
        if n_origem == 0:
            raise CommandError(
                "Origem sem preços. Rode importar_tabela_jardel (ou equivalente) "
                "ou escolha outro cabeçalho."
            )

        falt, ja = contagem_faltantes_no_destino(origem, destino)
        self.stdout.write(
            f"Destino id={destino.pk}: faltam {falt} serviço(s), já possui {ja} da origem."
        )

        atualizar = bool(options["atualizar_existentes"]) and not options["nao_atualizar"]

        try:
            r = replicar_tabela_preco(
                origem,
                destino,
                atualizar_existentes=atualizar,
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"Origem: {r.total_origem} | criados: {r.criados} | "
                f"atualizados: {r.atualizados} | pulados: {r.pulados}"
            )
        )
