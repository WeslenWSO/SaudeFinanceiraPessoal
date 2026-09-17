"""Inspeciona JSON de serviços Conta Azul para mapear campos fiscais."""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from dashboard.conta_azul.client import ContaAzulAPIError, ContaAzulClient
from dashboard.conta_azul.servicos import chaves_fiscais_presentes, extrair_fiscal_de_resposta
from empresa.models import Empresa


class Command(BaseCommand):
    help = 'Lista serviços Conta Azul e exibe chaves fiscais (cClassTrib, NBS, IBS/CBS) do JSON real.'

    def add_arguments(self, parser):
        parser.add_argument('--empresa-id', type=int, required=True)
        parser.add_argument('--limite', type=int, default=3, help='Quantos serviços detalhar (default: 3).')
        parser.add_argument('--id', dest='servico_id', help='UUID de um serviço específico.')

    def handle(self, *args, **options):
        empresa = Empresa.objects.filter(pk=options['empresa_id']).first()
        if not empresa:
            raise CommandError('Empresa não encontrada.')

        try:
            client = ContaAzulClient.para_empresa(empresa)
        except ContaAzulAPIError as exc:
            raise CommandError(str(exc)) from exc

        servico_id = (options.get('servico_id') or '').strip()
        if servico_id:
            det = client.buscar_servico_por_id(servico_id)
            self._imprimir_servico(det)
            return

        try:
            data = client.get('/v1/servicos', {'pagina': 1, 'tamanho_pagina': max(options['limite'], 1)})
        except ContaAzulAPIError as exc:
            raise CommandError(str(exc)) from exc

        itens = data.get('itens') or data.get('data') or []
        self.stdout.write(f'Total na página: {len(itens)}')
        for item in itens[: options['limite']]:
            sid = item.get('id')
            if not sid:
                continue
            det = client.buscar_servico_por_id(str(sid))
            self._imprimir_servico(det)

    def _imprimir_servico(self, item: dict) -> None:
        if not item:
            self.stdout.write(self.style.WARNING('Serviço vazio ou não encontrado.'))
            return
        self.stdout.write('')
        self.stdout.write(self.style.HTTP_INFO(f"=== {item.get('codigo', '?')} — {item.get('descricao', '')[:80]} ==="))
        self.stdout.write(f"ID: {item.get('id')}")
        self.stdout.write('Chaves fiscais detectadas:')
        for campo, caminho in chaves_fiscais_presentes(item).items():
            self.stdout.write(f'  {campo}: {caminho or "(não encontrado)"}')
        self.stdout.write('Valores extraídos:')
        self.stdout.write(json.dumps(extrair_fiscal_de_resposta(item), indent=2, ensure_ascii=False, default=str))
        self.stdout.write('Todas as chaves do JSON:')
        self.stdout.write(', '.join(sorted(item.keys())))
