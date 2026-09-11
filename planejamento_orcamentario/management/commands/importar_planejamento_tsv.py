"""Importa planejamento orçamentário a partir de TSV (colunas da planilha)."""

import csv
import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from categoria.models import Categoria
from empresa.models import Empresa
from planejamento_orcamentario.models import ItemOrcamento
from planejamento_orcamentario.services.parse_planilha_orcamento import (
    gerar_lancamentos_intervalo,
    montar_item_da_linha,
)


class Command(BaseCommand):
    help = (
        'Gera ItemOrcamento + lançamentos a partir de TSV '
        '(dia, fornecedor, valor_mensal, como_gerar, categoria, observacao).'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--empresa-id',
            type=int,
            default=16,
            help='ID da empresa (Medicinarte = 16).',
        )
        parser.add_argument(
            '--arquivo',
            type=str,
            default='scripts/dados/planejamento_medicinarte_dll.tsv',
            help='Caminho do arquivo TSV.',
        )
        parser.add_argument(
            '--substituir',
            action='store_true',
            help='Remove itens com o mesmo nome antes de importar.',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Apenas simula, sem gravar no banco.',
        )

    _ALIASES_CATEGORIA = {
        'CSLL': ['CSLL'],
        'IRPJ': ['IRPJ'],
        'PIS': ['PIS 8109', 'PIS'],
        'COFINS': ['COFINS'],
        'ISS': ['ISS SOBRE FATURAMENTO'],
        'FGTS': ['FGTS E MULTA DE FGTS', 'FGTS'],
        'INSS': ['INSS SOBRE SALÁRIOS - GPS', 'INSS SOBRE SALARIOS - GPS'],
    }

    def _buscar_categoria(self, empresa_id: int, texto: str):
        texto = (texto or '').strip()
        if not texto:
            return None
        qs = Categoria.objects.filter(empresa_id=empresa_id)
        cat = qs.filter(nome__iexact=texto).first()
        if cat:
            return cat
        cat = qs.filter(classificacao__iexact=texto).first()
        if cat:
            return cat
        chave = texto.upper().split()[0]
        for termo in self._ALIASES_CATEGORIA.get(chave, []):
            cat = qs.filter(nome__icontains=termo).order_by('nome').first()
            if cat:
                return cat
        if len(texto) >= 4:
            cat = qs.filter(nome__icontains=texto[:40]).first()
            if cat:
                return cat
        numeros = re.findall(r'\d{5,}', texto)
        for num in numeros:
            cat = qs.filter(nome__icontains=num).first()
            if cat:
                return cat
        if 'DLL' in texto.upper():
            return qs.filter(nome__icontains='DLL').order_by('nome').first()
        return None

    @staticmethod
    def _col(row: dict, *nomes: str, default='') -> str:
        for nome in nomes:
            if nome in row and (row[nome] or '').strip():
                return row[nome].strip()
        return default

    def handle(self, *args, **options):
        empresa_id = options['empresa_id']
        try:
            empresa = Empresa.objects.get(pk=empresa_id)
        except Empresa.DoesNotExist as exc:
            raise CommandError(f'Empresa id={empresa_id} não encontrada.') from exc

        path = Path(options['arquivo']).expanduser().resolve()
        if not path.is_file():
            raise CommandError(f'Arquivo não encontrado: {path}')

        self.stdout.write(f'Empresa: {empresa.id} — {empresa.razao}')
        self.stdout.write(f'Arquivo: {path}')

        linhas = []
        with path.open(encoding='utf-8-sig', newline='') as fh:
            reader = csv.DictReader(fh, delimiter='\t')
            for row in reader:
                if not any((v or '').strip() for v in row.values()):
                    continue
                linhas.append(row)

        if not linhas:
            raise CommandError('Nenhuma linha no TSV.')

        criados = 0
        lancamentos = 0
        ordem = (
            ItemOrcamento.objects.filter(empresa=empresa).order_by('-ordem').values_list('ordem', flat=True).first()
            or 0
        )

        with transaction.atomic():
            for idx, row in enumerate(linhas, start=1):
                dados = montar_item_da_linha(
                    dia=int(self._col(row, 'dia', 'dia_estimado')),
                    fornecedor=self._col(row, 'fornecedor'),
                    valor_mensal=self._col(row, 'valor_mensal', 'media_mensal'),
                    como_gerar=self._col(row, 'como_gerar', 'dias'),
                    categoria_nome=self._col(row, 'categoria'),
                    observacao=self._col(row, 'observacao'),
                    ocorrencias=self._col(row, 'ocorrencias', default='MENSAL'),
                    impostos=self._col(row, 'impostos'),
                )
                cat = self._buscar_categoria(empresa_id, dados['categoria_busca'])
                if not cat:
                    self.stdout.write(self.style.WARNING(
                        f'Linha {idx}: categoria não encontrada — {dados["categoria_busca"]!r}'
                    ))

                intervalo = dados.get('intervalo_meses', 1)
                self.stdout.write(
                    f'  {dados["nome"]}: R$ {dados["valor_mensal"]} · '
                    f'{dados["data_inicio"].strftime("%d/%m/%Y")} · '
                    f'{dados["qtd_meses"]} meses · intervalo {intervalo} · {dados["tipo"]}'
                )

                if options['dry_run']:
                    continue

                if options['substituir']:
                    ItemOrcamento.objects.filter(
                        empresa=empresa,
                        nome__iexact=dados['nome'],
                    ).delete()

                ordem += 1
                item = ItemOrcamento.objects.create(
                    empresa=empresa,
                    categoria=cat,
                    tipo=dados['tipo'],
                    nome=dados['nome'],
                    observacao=dados['observacao'],
                    forma_calculo=dados['forma_calculo'],
                    valor_mensal=dados['valor_mensal'],
                    data_inicio=dados['data_inicio'],
                    qtd_meses=dados['qtd_meses'],
                    ordem=ordem,
                    ativo=True,
                )
                if intervalo > 1:
                    n = gerar_lancamentos_intervalo(item, intervalo)
                else:
                    n = item.gerar_lancamentos()
                criados += 1
                lancamentos += n

            if options['dry_run']:
                transaction.set_rollback(True)

        if options['dry_run']:
            self.stdout.write(self.style.WARNING('Dry-run — nada gravado.'))
        else:
            self.stdout.write(self.style.SUCCESS(
                f'Concluído: {criados} item(ns), {lancamentos} lançamento(s) gerado(s).'
            ))
