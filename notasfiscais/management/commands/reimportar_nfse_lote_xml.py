"""
Reimporta/atualiza NFSe a partir de um XML de lote (ConsultarNfseLote / ListaNfse).

Atualiza notas já existentes com valores, retenções, alíquota ISS, NSU e reativa canceladas indevidas.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from empresa.models import Empresa
from notasfiscais.models import NotaFiscalServico
from notasfiscais.utils import (
    _local,
    _parse_xml_root,
    aplicar_nfse_importada_em_existente,
    import_nfse_individual,
)


class Command(BaseCommand):
    help = 'Reimporta lote XML ABRASF atualizando NFSe existentes (valores e retenções).'

    def add_arguments(self, parser):
        parser.add_argument('--empresa-id', type=int, required=True)
        parser.add_argument('--arquivo', type=str, required=True, help='Caminho do XML de lote.')
        parser.add_argument('--mes', type=int, help='Filtrar por mês de emissão (1-12).')
        parser.add_argument('--ano', type=int, help='Filtrar por ano de emissão.')
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument(
            '--criar-ausentes',
            action='store_true',
            help='Cria NFSe que ainda não existem no banco.',
        )

    def handle(self, *args, **options):
        path = Path(options['arquivo'])
        if not path.is_file():
            raise CommandError(f'Arquivo não encontrado: {path}')

        empresa = Empresa.objects.filter(pk=options['empresa_id']).first()
        if not empresa:
            raise CommandError(f'Empresa {options["empresa_id"]} não encontrada.')

        user = User.objects.filter(is_superuser=True).first() or User.objects.first()
        if not user:
            raise CommandError('Nenhum usuário no banco para registrar importação.')

        root = _parse_xml_root(path.read_bytes())
        mes = options.get('mes')
        ano = options.get('ano')

        stats = {
            'processadas': 0,
            'atualizadas': 0,
            'criadas': 0,
            'ignoradas_filtro': 0,
            'erros': 0,
        }

        elementos = [e for e in root.iter() if _local(e.tag) == 'infnfse']

        if options.get('dry_run'):
            self.stdout.write(f'InfNfse no arquivo: {len(elementos)}')
            if mes and ano:
                self.stdout.write(f'Filtro: {mes:02d}/{ano}')
            return

        with transaction.atomic():
            for elem in elementos:
                try:
                    parsed = import_nfse_individual(
                        elem, user, empresa, importar_canceladas=False,
                    )
                except Exception as exc:
                    stats['erros'] += 1
                    self.stdout.write(self.style.WARNING(f'Erro ao parsear nota: {exc}'))
                    continue

                nfses = parsed if isinstance(parsed, list) else [parsed]
                stats['processadas'] += len(nfses)

                for nf_parsed in nfses:
                    if mes and nf_parsed.data_emissao and nf_parsed.data_emissao.month != mes:
                        stats['ignoradas_filtro'] += 1
                        continue
                    if ano and nf_parsed.data_emissao and nf_parsed.data_emissao.year != ano:
                        stats['ignoradas_filtro'] += 1
                        continue

                    existente = NotaFiscalServico.objects.filter(
                        empresa=empresa,
                        numero_nota=nf_parsed.numero_nota,
                    ).order_by('-pk').first()

                    if existente:
                        aplicar_nfse_importada_em_existente(existente, nf_parsed)
                        from contasareceber.models import ContaAReceber
                        ContaAReceber.objects.filter(nota_id=existente.pk).update(
                            valor_a_receber=existente.valor_liquido,
                            observacao=existente.discriminacao,
                        )
                        stats['atualizadas'] += 1
                    elif options.get('criar_ausentes'):
                        nf_parsed.save()
                        stats['criadas'] += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'Processadas: {stats["processadas"]} | Atualizadas: {stats["atualizadas"]} | '
                f'Criadas: {stats["criadas"]} | Fora do filtro: {stats["ignoradas_filtro"]} | '
                f'Erros: {stats["erros"]}'
            )
        )
