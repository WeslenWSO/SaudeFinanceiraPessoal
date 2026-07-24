from django.core.management.base import BaseCommand
from notasfiscais.models import NotaFiscalServico
from cobranca.models import Cobranca
from django.db.models import Q
import re

class Command(BaseCommand):
    help = 'Atualiza forma de pagamento e NSU de múltiplas notas baseado em critérios'

    def add_arguments(self, parser):
        parser.add_argument(
            '--forma-pagamento',
            type=str,
            help='Descrição da forma de pagamento (ex: CARTAO DEBITO, DINHEIRO)',
            required=True
        )
        parser.add_argument(
            '--tpag',
            type=str,
            help='Código TPag da forma de pagamento (ex: CD, DH)',
            required=True
        )
        parser.add_argument(
            '--numero-nota',
            type=str,
            help='Número da nota específica (opcional)'
        )
        parser.add_argument(
            '--cliente',
            type=str,
            help='Nome do cliente para filtrar (opcional)'
        )
        parser.add_argument(
            '--data-inicio',
            type=str,
            help='Data inicial (YYYY-MM-DD) (opcional)'
        )
        parser.add_argument(
            '--data-fim',
            type=str,
            help='Data final (YYYY-MM-DD) (opcional)'
        )
        parser.add_argument(
            '--nsu',
            type=str,
            help='NSU para definir (opcional)'
        )
        parser.add_argument(
            '--extrair-nsu',
            action='store_true',
            help='Extrair NSU da discriminação automaticamente'
        )
        parser.add_argument(
            '--empresa-id',
            type=int,
            help='ID da empresa (opcional)'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Mostrar o que seria feito sem executar'
        )

    def handle(self, *args, **options):
        # Busca a forma de pagamento
        try:
            forma_pagamento = Cobranca.objects.get(
                descricao=options['forma_pagamento'],
                tpag=options['tpag']
            )
        except Cobranca.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(
                    f'Forma de pagamento "{options["forma_pagamento"]}" com TPag "{options["tpag"]}" não encontrada.'
                )
            )
            return

        # Monta o queryset base
        queryset = NotaFiscalServico.objects.all()

        # Aplica filtros
        if options['empresa_id']:
            queryset = queryset.filter(empresa_id=options['empresa_id'])

        if options['numero_nota']:
            queryset = queryset.filter(numero_nota=options['numero_nota'])

        if options['cliente']:
            queryset = queryset.filter(cliente__icontains=options['cliente'])

        if options['data_inicio']:
            queryset = queryset.filter(data_emissao__gte=options['data_inicio'])

        if options['data_fim']:
            queryset = queryset.filter(data_emissao__lte=options['data_fim'])

        # Conta as notas encontradas
        total_notas = queryset.count()

        if total_notas == 0:
            self.stdout.write(self.style.WARNING('Nenhuma nota encontrada com os critérios especificados.'))
            return

        self.stdout.write(f'Encontradas {total_notas} notas para processar.')

        if options['dry_run']:
            self.stdout.write('Modo DRY-RUN - As seguintes notas seriam atualizadas:')
            for nota in queryset[:10]:  # Mostra apenas as primeiras 10
                self.stdout.write(f'  - Nota {nota.numero_nota}: {nota.cliente}')
            if total_notas > 10:
                self.stdout.write(f'  ... e mais {total_notas - 10} notas')
            return

        # Processa as notas
        atualizadas = 0
        erros = []

        for nota in queryset:
            try:
                # Atualiza forma de pagamento
                nota.forma_pagamento = forma_pagamento

                # Define NSU se especificado
                if options['nsu']:
                    nota.nsu = options['nsu']

                # Extrai NSU da discriminação se solicitado
                elif options['extrair_nsu'] and nota.discriminacao:
                    nsu_extraido = self._extrair_nsu_discriminacao(nota.discriminacao)
                    if nsu_extraido:
                        nota.nsu = nsu_extraido
                        self.stdout.write(
                            self.style.SUCCESS(
                                f'NSU extraído da discriminação da nota {nota.numero_nota}: {nsu_extraido}'
                            )
                        )

                # Salva a nota
                nota.save()

                atualizadas += 1

                if atualizadas <= 5:  # Mostra detalhes das primeiras 5
                    nsu_info = f', NSU: {nota.nsu}' if nota.nsu else ''
                    self.stdout.write(
                        f'✅ Nota {nota.numero_nota} ({nota.cliente}) atualizada: {forma_pagamento.descricao}{nsu_info}'
                    )

            except Exception as e:
                erros.append(f'Erro na nota {nota.numero_nota}: {str(e)}')

        # Resumo final
        self.stdout.write('\n' + '='*50)
        self.stdout.write(self.style.SUCCESS(f'RESUMO:'))
        self.stdout.write(f'  - Total de notas processadas: {total_notas}')
        self.stdout.write(f'  - Notas atualizadas com sucesso: {atualizadas}')
        if erros:
            self.stdout.write(f'  - Erros encontrados: {len(erros)}')
            for erro in erros[:5]:  # Mostra apenas os primeiros 5 erros
                self.stdout.write(f'    ❌ {erro}')
            if len(erros) > 5:
                self.stdout.write(f'    ... e mais {len(erros) - 5} erros')

        if atualizadas > 5:
            self.stdout.write(f'  - {atualizadas - 5} notas adicionais foram atualizadas silenciosamente')

    def _extrair_nsu_discriminacao(self, discriminacao):
        """Extrai NSU da discriminação usando padrões similares ao views.py"""
        if not discriminacao:
            return None

        # Padrões para capturar códigos de autorização
        patterns = [
            r'\bAUT[:\s]*([A-Za-z0-9\-\/\.]+)',  # AUT seguido de : ou espaço
            r'\bAUT([A-Za-z0-9\-\/\.]+)',        # AUT colado ao código
            r'aut[:\s]*([A-Za-z0-9\-\/\.]+)',    # minúsculo
            r'autorizacao[:\s]*([A-Za-z0-9\-\/\.]+)',  # palavra completa
        ]

        for pattern in patterns:
            m = re.search(pattern, discriminacao, flags=re.IGNORECASE)
            if m:
                return m.group(1).strip()

        return None