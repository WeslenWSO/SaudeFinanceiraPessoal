"""Configura MedCloud (RIS/HIS) para a empresa Medicinarte."""

from __future__ import annotations

import os
import re
from datetime import date, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Count

from agendador_tarefas.seed_faturamento import NOME_FANTASIA_AGENDA_FATURAMENTO
from empresa.models import Empresa
from faturamento_medico.medcloud.client import MedcloudAPIError, MedcloudRISClient
from faturamento_medico.medcloud.config import (
    credenciais_da_empresa,
    gravar_api_key_his,
    gravar_senha_ris,
)
from faturamento_medico.models import FaturamentoMedico, MedcloudConfig, MedcloudConvenioParceiro
from servicos_medicos.models import Convenio

# Convênios cadastrados em servicos_medicos + extras usados no faturamento Medicinarte.
CONVENIOS_MEDICINARTE_MEDCLOUD = (
    'BRADESCO SAUDE S.A.',
    'CORPO DE BOMBEIRO',
    'FUNCIONAL HEALTH TECH  - JANSSEN ESSENCIAL',
    'FUSEX',
    'GEAP SAÚDE - AUTOESTOQUE EM SAÚDE',
    'GEAP SAÚDE - AUTOESTÃO EM SAÚDE',
    'POLICIA MILITAR - POLICLINICA',
    'POSTAL SAÚDE',
    'PP SAUDE',
    'Particular',
    'REAL CONVÊNIOS',
    'JARDEL',
    'MEDICOS PARCEIROS',
)


def _exige_laudo_convenio(nome: str) -> bool:
    """Inicialmente só GEAP exige busca de laudo liberado."""
    return 'GEAP' in (nome or '').upper()


_CONVENIO_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ('POSTAL SAÚDE', ('POSTAL',)),
    ('CORPO DE BOMBEIRO', ('BOMBEIRO',)),
    ('POLICIA MILITAR - POLICLINICA', ('POLICIA MILITAR', 'PM', 'POLÍCIA MILITAR')),
    ('FUSEX', ('FUSEX',)),
    ('FUNCIONAL HEALTH TECH  - JANSSEN ESSENCIAL', ('FUNCIONAL', 'JANSSEN')),
    ('GEAP SAÚDE - AUTOESTOQUE EM SAÚDE', ('GEAP',)),
    ('BRADESCO SAUDE S.A.', ('BRADESCO',)),
    ('PP SAUDE', ('PP SAUDE', 'PPSAUDE', 'PP SAÚDE')),
    ('CASSI', ('CASSI',)),
)


def _normalizar(texto: str) -> str:
    return re.sub(r'\s+', ' ', (texto or '').strip().upper())


def _convenios_medicinarte(empresa: Empresa) -> list[str]:
    """Nomes de convênio usados no faturamento + cadastro de serviços."""
    nomes: set[str] = set()
    for row in (
        FaturamentoMedico.objects.filter(empresa=empresa)
        .exclude(convenio__isnull=True)
        .exclude(convenio='')
        .values('convenio')
        .annotate(n=Count('id'))
        .order_by('-n')[:50]
    ):
        nomes.add(row['convenio'])
    for nome in Convenio.objects.filter(empresa=empresa).values_list('nome', flat=True):
        if nome:
            nomes.add(nome)
    return sorted(nomes, key=_normalizar)


def _casar_convenio_local(partner_nome: str, candidatos: list[str]) -> str | None:
    pn = _normalizar(partner_nome)
    for convenio, keywords in _CONVENIO_KEYWORDS:
        if convenio in candidatos:
            for kw in keywords:
                if kw in pn:
                    return convenio
    for candidato in candidatos:
        c = _normalizar(candidato)
        if c in pn or pn in c:
            return candidato
    return None


def _descobrir_partners(
    ris: MedcloudRISClient,
    candidatos: list[str],
    *,
    dias: int = 30,
) -> dict[str, int]:
    """Extrai partnerId das agendas recentes e casa com convênios locais."""
    hoje = date.today()
    inicio = hoje - timedelta(days=dias)
    schedules = ris.list_schedules(inicio, hoje, status='CONCLUDED')
    partner_ids: set[int] = set()
    for sched in schedules:
        raw = sched.get('partnerId')
        if raw is None:
            continue
        try:
            partner_ids.add(int(raw))
        except (TypeError, ValueError):
            continue

    mapping: dict[str, int] = {}
    for pid in sorted(partner_ids):
        partner = ris.get_partner(pid) or {}
        nome = partner.get('name') or partner.get('nome') or partner.get('description') or ''
        local = _casar_convenio_local(str(nome), candidatos)
        if local and local not in mapping:
            mapping[local] = pid
    return mapping


class Command(BaseCommand):
    help = (
        'Cria ou atualiza MedcloudConfig da Medicinarte e mapeia convênios. '
        'Credenciais via argumentos ou variáveis MEDCLOUD_*.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--ris-user',
            default=os.environ.get('MEDCLOUD_RIS_USERNAME', ''),
            help='Usuário RIS (ou MEDCLOUD_RIS_USERNAME).',
        )
        parser.add_argument(
            '--ris-password',
            default=os.environ.get('MEDCLOUD_RIS_PASSWORD', ''),
            help='Senha RIS (ou MEDCLOUD_RIS_PASSWORD).',
        )
        parser.add_argument(
            '--clinic-id',
            type=int,
            default=int(os.environ.get('MEDCLOUD_RIS_CLINIC_ID') or 0),
            help='clinicIdToAccess (ou MEDCLOUD_RIS_CLINIC_ID).',
        )
        parser.add_argument(
            '--his-api-key',
            default=os.environ.get('MEDCLOUD_HIS_API_KEY', ''),
            help='API Key HIS (ou MEDCLOUD_HIS_API_KEY).',
        )
        parser.add_argument(
            '--partner',
            action='append',
            default=[],
            metavar='NOME=ID',
            help='Mapeamento convênio→partner_id (pode repetir). Ex.: "GEAP SAÚDE - AUTOESTOQUE EM SAÚDE=42"',
        )
        parser.add_argument(
            '--discover-partners',
            action='store_true',
            help='Descobre partner_id via API RIS (exige credenciais RIS).',
        )
        parser.add_argument(
            '--discover-days',
            type=int,
            default=30,
            help='Dias retroativos para descoberta de partners (padrão: 30).',
        )
        parser.add_argument(
            '--skip-convenios',
            action='store_true',
            help='Não cria/atualiza MedcloudConvenioParceiro.',
        )
        parser.add_argument(
            '--seed-convenios',
            action='store_true',
            help=(
                'Cadastra convênios da Medicinarte (servicos_medicos + faturamento) '
                'com partner_id=0 para preencher no admin ou via --discover-partners.'
            ),
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Mostra o que seria gravado sem salvar.',
        )

    def handle(self, *args, **options):
        empresa = Empresa.objects.filter(
            nome_fantasia__iexact=NOME_FANTASIA_AGENDA_FATURAMENTO,
        ).first()
        if not empresa:
            raise CommandError(f'Empresa "{NOME_FANTASIA_AGENDA_FATURAMENTO}" não encontrada.')

        ris_user = (options['ris_user'] or '').strip()
        ris_password = (options['ris_password'] or '').strip()
        clinic_id = int(options['clinic_id'] or 0)
        his_api_key = (options['his_api_key'] or '').strip()
        dry = options['dry_run']

        self.stdout.write(f'Empresa: {empresa.nome_fantasia} (id={empresa.id})')

        cfg = MedcloudConfig.objects.filter(empresa=empresa).first()
        criar = cfg is None
        if criar:
            cfg = MedcloudConfig(empresa=empresa)

        if ris_user:
            cfg.ris_username = ris_user
        if clinic_id:
            cfg.ris_clinic_id = clinic_id
        cfg.ativo = True

        if dry:
            self.stdout.write(self.style.WARNING('DRY-RUN — nada será gravado.'))
        else:
            with transaction.atomic():
                cfg.save()
                if ris_password:
                    gravar_senha_ris(cfg, ris_password)
                    cfg.save(update_fields=['ris_password_cifrada'])
                if his_api_key:
                    gravar_api_key_his(cfg, his_api_key)
                    cfg.save(update_fields=['his_api_key_cifrada'])

        self.stdout.write(
            f'MedcloudConfig: {"criado" if criar else "atualizado"} '
            f'(ativo={cfg.ativo}, user={cfg.ris_username or "—"}, clinic={cfg.ris_clinic_id})'
        )
        self.stdout.write(
            f'Admin: /admin/faturamento_medico/medcloudconfig/{cfg.pk}/change/'
            if cfg.pk and not dry
            else 'Admin: /admin/faturamento_medico/medcloudconfig/'
        )

        if options['skip_convenios']:
            self._report_credentials(cfg, empresa, ris_password, his_api_key)
            return

        candidatos = _convenios_medicinarte(empresa)
        partner_map: dict[str, int] = {}

        if options['seed_convenios']:
            nomes_seed = list(
                Convenio.objects.filter(empresa=empresa)
                .order_by('nome')
                .values_list('nome', flat=True)
            )
            for extra in CONVENIOS_MEDICINARTE_MEDCLOUD:
                if extra not in nomes_seed:
                    nomes_seed.append(extra)
            if not nomes_seed:
                nomes_seed = candidatos[:12]
            criados = atualizados = 0
            for nome in nomes_seed:
                if dry:
                    self.stdout.write(f'  [dry] seed {nome!r}')
                    continue
                exige = _exige_laudo_convenio(nome)
                obj, created = MedcloudConvenioParceiro.objects.update_or_create(
                    config=cfg,
                    convenio_nome=nome,
                    defaults={
                        'partner_id': 0,
                        'exige_laudo': exige,
                    },
                )
                if created:
                    criados += 1
                else:
                    atualizados += 1
            if not dry:
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Seed convênios: {criados} criados, {atualizados} já existiam '
                        f'(partner_id=0 — atualize no admin ou use --discover-partners).'
                    )
                )
            self._report_credentials(cfg, empresa, ris_password, his_api_key)
            return

        for item in options['partner']:
            if '=' not in item:
                raise CommandError(f'--partner inválido: {item!r} (use NOME=ID)')
            nome, pid_raw = item.split('=', 1)
            nome = nome.strip()
            try:
                partner_map[nome] = int(pid_raw.strip())
            except ValueError as exc:
                raise CommandError(f'partner_id inválido em {item!r}') from exc

        if options['discover_partners']:
            creds = credenciais_da_empresa(empresa)
            if not creds:
                raise CommandError(
                    'Credenciais RIS incompletas. Informe --ris-user, --ris-password e --clinic-id '
                    'ou configure MEDCLOUD_RIS_* antes de --discover-partners.'
                )
            try:
                ris = MedcloudRISClient(creds)
                descobertos = _descobrir_partners(
                    ris, candidatos, dias=options['discover_days'],
                )
                partner_map.update(descobertos)
                self.stdout.write(
                    self.style.SUCCESS(f'Partners descobertos: {len(descobertos)}')
                )
            except MedcloudAPIError as exc:
                raise CommandError(str(exc)) from exc

        if not partner_map:
            self.stdout.write(
                self.style.WARNING(
                    'Nenhum convênio mapeado (use --partner NOME=ID ou --discover-partners). '
                    f'Convênios locais ({len(candidatos)}):'
                )
            )
            for nome in candidatos[:15]:
                self.stdout.write(f'  - {nome}')
            self._report_credentials(cfg, empresa, ris_password, his_api_key)
            return

        criados = atualizados = 0
        for convenio_nome, partner_id in sorted(partner_map.items(), key=lambda x: x[0]):
            if dry:
                self.stdout.write(f'  [dry] {convenio_nome!r} → partner {partner_id}')
                continue
            obj, created = MedcloudConvenioParceiro.objects.update_or_create(
                config=cfg,
                convenio_nome=convenio_nome,
                defaults={
                    'partner_id': partner_id,
                    'exige_laudo': True,
                },
            )
            if created:
                criados += 1
            else:
                atualizados += 1
            self.stdout.write(f'  {convenio_nome!r} → partner {obj.partner_id}')

        if not dry:
            self.stdout.write(
                self.style.SUCCESS(
                    f'Convênios MedCloud: {criados} criados, {atualizados} atualizados.'
                )
            )

        self._report_credentials(cfg, empresa, ris_password, his_api_key)

    def _report_credentials(self, cfg, empresa, ris_password, his_api_key):
        creds = credenciais_da_empresa(empresa) if cfg.pk else None
        if creds and cfg.ris_username and cfg.ris_clinic_id:
            self.stdout.write(self.style.SUCCESS('Credenciais RIS: OK'))
        else:
            self.stdout.write(
                self.style.WARNING(
                    'Credenciais RIS incompletas — preencha no admin ou rode o comando com '
                    '--ris-user, --ris-password e --clinic-id.'
                )
            )
        if creds and creds.his_api_key:
            self.stdout.write(self.style.SUCCESS('API Key HIS: OK'))
        elif his_api_key:
            self.stdout.write(self.style.SUCCESS('API Key HIS: informada nesta execução'))
        else:
            self.stdout.write(
                self.style.WARNING(
                    'API Key HIS ausente — necessária para sync de laudos.'
                )
            )
