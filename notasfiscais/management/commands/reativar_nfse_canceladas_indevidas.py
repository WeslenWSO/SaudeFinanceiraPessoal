"""
Reativa NFSe marcadas como canceladas indevidamente (data_cancelamento preenchida).

Útil após importação em lote com o checkbox «notas canceladas» marcado por engano
ou heurística antiga do portal nacional em XML ABRASF (Rio Branco).

Opcionalmente reimporta valores a partir dos XMLs numa pasta local.
"""
from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q

from notasfiscais.models import NotaFiscalServico
from notasfiscais.utils import _extrair_valores_nfse_scope, _parse_xml_root
import xml.etree.ElementTree as ET


class Command(BaseCommand):
    help = (
        'Remove data_cancelamento de NFSe canceladas indevidamente e, opcionalmente, '
        'atualiza valores a partir dos XMLs originais.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--empresa-id', type=int, required=True, help='ID da empresa.')
        parser.add_argument('--data-inicio', type=str, help='YYYY-MM-DD (emissão).')
        parser.add_argument('--data-fim', type=str, help='YYYY-MM-DD (emissão).')
        parser.add_argument(
            '--pasta-xml',
            type=str,
            help='Pasta com XMLs para recalcular valor_bruto/valor_liquido (opcional).',
        )
        parser.add_argument('--dry-run', action='store_true', help='Só mostra quantas seriam alteradas.')

    def handle(self, *args, **options):
        from datetime import datetime

        empresa_id = options['empresa_id']
        qs = NotaFiscalServico.objects.filter(
            empresa_id=empresa_id,
            data_cancelamento__isnull=False,
        )
        di = options.get('data_inicio')
        df = options.get('data_fim')
        if di:
            qs = qs.filter(data_emissao__gte=datetime.strptime(di, '%Y-%m-%d').date())
        if df:
            qs = qs.filter(data_emissao__lte=datetime.strptime(df, '%Y-%m-%d').date())

        pasta = (options.get('pasta_xml') or '').strip()
        xml_por_numero: dict[str, Path] = {}
        if pasta and os.path.isdir(pasta):
            for p in Path(pasta).rglob('*.xml'):
                xml_por_numero[p.name.lower()] = p

        total = qs.count()
        if total == 0:
            self.stdout.write(self.style.WARNING('Nenhuma NFSe cancelada encontrada no filtro.'))
            return

        if options.get('dry_run'):
            self.stdout.write(f'Seriam reativadas: {total} NFSe.')
            zeradas = qs.filter(Q(valor_bruto=0) | Q(valor_liquido=0)).count()
            self.stdout.write(f'Dessas, {zeradas} com valor bruto ou líquido zerado.')
            return

        reativadas = 0
        valores_atualizados = 0

        with transaction.atomic():
            for nf in qs.iterator():
                nf.data_cancelamento = None
                update_fields = ['data_cancelamento', 'data_atualizacao']

                # Tenta achar XML pelo número da nota no nome do arquivo
                if xml_por_numero:
                    candidatos = [
                        p for nome, p in xml_por_numero.items()
                        if (nf.numero_nota or '').strip() and (nf.numero_nota or '').strip() in nome
                    ]
                    if candidatos:
                        try:
                            root = _parse_xml_root(candidatos[0].read_bytes())
                            scope = root
                            for child in root.iter():
                                if child.tag.endswith('InfNfse') or 'infnfse' in child.tag.lower():
                                    scope = child
                                    break
                            bruto, liquido = _extrair_valores_nfse_scope(scope)
                            if bruto > 0:
                                nf.valor_bruto = bruto
                                update_fields.append('valor_bruto')
                            if liquido > 0:
                                nf.valor_liquido = liquido
                                update_fields.append('valor_liquido')
                            if bruto > 0 or liquido > 0:
                                valores_atualizados += 1
                        except Exception as exc:
                            self.stdout.write(
                                self.style.WARNING(f'XML {candidatos[0].name}: {exc}')
                            )
                elif (nf.valor_bruto or Decimal('0')) <= 0 and (nf.valor_liquido or Decimal('0')) <= 0:
                    pass  # valores permanecem zero — reimporte manualmente os XMLs

                nf.save(update_fields=list(dict.fromkeys(update_fields)))
                reativadas += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'Reativadas: {reativadas} NFSe. Valores recalculados de XML: {valores_atualizados}.'
            )
        )
