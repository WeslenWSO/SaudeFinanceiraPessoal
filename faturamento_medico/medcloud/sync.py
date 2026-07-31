"""Sincroniza agendas concluídas e links de laudo MedCloud → faturamento médico."""

from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from faturamento_medico.models import FaturamentoMedico, ItemServico, MedcloudConvenioParceiro

from .client import MedcloudAPIError, MedcloudHISClient, MedcloudRISClient
from .config import MedcloudCredentials, credenciais_da_empresa

logger = logging.getLogger(__name__)


def _parse_data(val) -> date | None:
    if val is None:
        return None
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, str):
        d = parse_date(val[:10])
        if d:
            return d
    return None


def _parse_decimal(val) -> Decimal:
    if val is None or val == '':
        return Decimal('0')
    try:
        return Decimal(str(val).replace(',', '.'))
    except (InvalidOperation, ValueError):
        return Decimal('0')


def _texto(val, max_len: int | None = None) -> str | None:
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    if max_len:
        return s[:max_len]
    return s


def _nome_paciente(ris: MedcloudRISClient, schedule: dict) -> str | None:
    for key in ('patientName', 'patient_name', 'nomePaciente'):
        nome = _texto(schedule.get(key), 200)
        if nome:
            return nome
    patient = schedule.get('patient')
    if isinstance(patient, dict):
        return _texto(patient.get('name') or patient.get('nome'), 200)
    patient_id = schedule.get('patientId')
    if patient_id:
        p = ris.get_patient(int(patient_id))
        if p:
            return _texto(p.get('name'), 200)
    return None


def _nome_procedimento(ris: MedcloudRISClient, schedule: dict) -> str | None:
    for key in ('procedureName', 'medicalProcedureName', 'procedure'):
        val = schedule.get(key)
        if isinstance(val, dict):
            val = val.get('name') or val.get('description')
        nome = _texto(val, 200)
        if nome:
            return nome
    proc_id = schedule.get('medicalProcedureId')
    if proc_id:
        proc = ris.get_procedure(int(proc_id))
        if proc:
            return _texto(proc.get('name') or proc.get('description'), 200)
    return None


def _nome_convenio(ris: MedcloudRISClient, schedule: dict, partner_map: dict[int, str]) -> str | None:
    partner_id = schedule.get('partnerId')
    if partner_id is not None:
        try:
            pid = int(partner_id)
            if pid in partner_map:
                return partner_map[pid]
        except (TypeError, ValueError):
            pass
    partner = schedule.get('partner')
    if isinstance(partner, dict):
        return _texto(partner.get('name'), 100)
    if partner_id:
        p = ris.get_partner(int(partner_id))
        if p:
            return _texto(p.get('name'), 100)
    return None


def _accession(schedule: dict) -> str | None:
    for key in (
        'accessionNumber', 'accession_number', 'reportCode', 'report_code',
        'codigoRelatorio', 'codigo_relatorio',
    ):
        val = _texto(schedule.get(key), 50)
        if val:
            return val
    return None


def _status_agendamento_label(schedule: dict) -> str:
    status = (schedule.get('status') or '').strip()
    mapping = {
        'CONCLUDED': 'Concluído',
        'CANCELED': 'Cancelado',
        'ONLINE_CANCELED': 'Cancelado',
        'GIVE_UP': 'Desistência',
        'DELETED': 'Deletado',
        'IN_PROGRESS': 'Em andamento',
        'CONFIRMED': 'Confirmado',
        'WAITING_FOR_BILLING': 'Aguardando faturamento',
        'WAITING_FOR_CHECKOUT': 'Aguardando checkout',
    }
    return mapping.get(status.upper(), status or 'Concluído')


def _motivo_cancelamento(schedule: dict) -> str | None:
    for key in (
        'cancellationReason', 'cancelReason', 'motivoCancelamento',
        'giveUpReason', 'deleteReason', 'reason',
    ):
        val = _texto(schedule.get(key), 255)
        if val:
            return val
    return None


def _convenios_exige_laudo(cfg) -> set[str]:
    if not cfg:
        return set()
    return {
        c.convenio_nome.lower()
        for c in cfg.convenios.filter(exige_laudo=True)
    }


def _enriquecer_agenda(ris: MedcloudRISClient, schedule: dict) -> dict:
    """Busca agenda por ID se a listagem trouxe só metadados."""
    sid = schedule.get('id') or schedule.get('scheduleId')
    if sid and not schedule.get('patientId') and not schedule.get('patientName'):
        completa = ris.get_schedule(int(sid))
        if completa:
            schedule = {**completa, **schedule}
    return schedule


def sincronizar_agendas_concluidas(
    empresa,
    data_inicio: date,
    data_fim: date,
    *,
    convenio_nome: str | None = None,
    partner_id: int | None = None,
    dry_run: bool = False,
) -> dict:
    """
    Importa agendas do MedCloud RIS para FaturamentoMedico (todos os status e convênios).
    Cancelados, desistências e deletados entram com status_agendamento correspondente.
    """
    creds = credenciais_da_empresa(empresa)
    if not creds:
        raise MedcloudAPIError('Credenciais MedCloud não configuradas para esta empresa.')

    ris = MedcloudRISClient(creds)
    cfg = getattr(empresa, 'medcloud_config', None)
    partner_map: dict[int, str] = {}
    convenios_cfg: list[MedcloudConvenioParceiro] = []
    convenios_laudo = _convenios_exige_laudo(cfg)
    if cfg:
        convenios_cfg = list(cfg.convenios.all())
        for c in convenios_cfg:
            if c.partner_id > 0:
                partner_map[c.partner_id] = c.convenio_nome

    filtro_partner_id = partner_id
    if convenio_nome and not filtro_partner_id and cfg:
        for c in convenios_cfg:
            if c.convenio_nome.lower() == convenio_nome.lower():
                if c.partner_id > 0:
                    filtro_partner_id = c.partner_id
                break

    stats = {
        'listadas': 0,
        'importadas': 0,
        'criadas': 0,
        'atualizadas': 0,
        'ignoradas': 0,
        'erros': 0,
    }

    try:
        agendas = ris.list_schedules_periodo(
            data_inicio,
            data_fim,
            partner_id=filtro_partner_id,
        )
    except MedcloudAPIError:
        raise

    stats['listadas'] = len(agendas)

    for raw in agendas:
        try:
            schedule = _enriquecer_agenda(ris, raw)

            data_fat = _parse_data(schedule.get('date'))
            if not data_fat:
                stats['ignoradas'] += 1
                continue
            if data_fat < data_inicio or data_fat > data_fim:
                stats['ignoradas'] += 1
                continue

            stats['importadas'] += 1
            schedule_id = schedule.get('id') or schedule.get('scheduleId')
            nome = _nome_paciente(ris, schedule) or 'Sem nome'
            procedimento = _nome_procedimento(ris, schedule) or 'Procedimento MedCloud'
            convenio = _nome_convenio(ris, schedule, partner_map) or convenio_nome or 'Particular'

            if convenio_nome and convenio.lower() != convenio_nome.lower():
                stats['ignoradas'] += 1
                continue

            accession = _accession(schedule)
            start_time = _texto(schedule.get('startTime') or schedule.get('start_time'), 20)
            end_time = _texto(schedule.get('endTime') or schedule.get('end_time'), 20)
            horario = ''
            if start_time or end_time:
                horario = f'{(start_time or "")} - {(end_time or "")}'.strip(' -')

            payment = schedule.get('patientPayment')
            payment_val = payment.get('value') if isinstance(payment, dict) else None
            valor = _parse_decimal(
                schedule.get('value') or schedule.get('totalValue') or payment_val
            )

            if dry_run:
                stats['criadas'] += 1
                continue

            with transaction.atomic():
                existente = None
                if schedule_id:
                    existente = FaturamentoMedico.objects.filter(
                        empresa=empresa,
                        medcloud_schedule_id=schedule_id,
                    ).first()
                if not existente and accession:
                    existente = FaturamentoMedico.objects.filter(
                        empresa=empresa,
                        codigo_relatorio=accession,
                    ).first()

                campos = {
                    'nome': nome,
                    'nome_associado': nome,
                    'data': data_fat,
                    'convenio': convenio,
                    'horario': horario or None,
                    'horario_inicio': start_time,
                    'horario_fim': end_time,
                    'status_agendamento': _status_agendamento_label(schedule),
                    'motivo_cancelamento': _motivo_cancelamento(schedule),
                    'agendado_via': 'MedCloud API',
                    'codigo_relatorio': accession,
                    'medcloud_schedule_id': int(schedule_id) if schedule_id else None,
                }

                if existente:
                    for k, v in campos.items():
                        if v is not None:
                            setattr(existente, k, v)
                    existente.save()
                    stats['atualizadas'] += 1
                    faturamento = existente
                else:
                    faturamento = FaturamentoMedico.objects.create(
                        empresa=empresa,
                        status='pendente',
                        **campos,
                    )
                    ItemServico.objects.create(
                        faturamento=faturamento,
                        codigo_servico='',
                        servico=procedimento,
                        modalidade=_texto(schedule.get('modality'), 20),
                        porte='',
                        qt=1,
                        valor=valor,
                        total=valor,
                    )
                    faturamento.atualizar_total()
                    stats['criadas'] += 1

                busca_laudo = (
                    accession
                    and creds.his_api_key
                    and not faturamento.link_laudo
                    and (
                        not convenios_laudo
                        or convenio.lower() in convenios_laudo
                    )
                )
                if busca_laudo:
                    try:
                        _atualizar_links_laudo(faturamento, accession, creds)
                    except MedcloudAPIError as exc:
                        logger.info('Laudo ainda indisponível schedule %s: %s', schedule_id, exc)

        except Exception:
            logger.exception('Erro ao processar agenda MedCloud')
            stats['erros'] += 1

    return stats


def _link_expirado(faturamento: FaturamentoMedico) -> bool:
    if not faturamento.laudo_expires_at:
        return False
    return faturamento.laudo_expires_at <= timezone.now()


def _atualizar_links_laudo(
    faturamento: FaturamentoMedico,
    accession_number: str,
    creds: MedcloudCredentials,
) -> bool:
    his = MedcloudHISClient(creds)
    data = his.gerar_links_exame(accession_number)
    if not data:
        return False

    report = data.get('reportLink') or data.get('report_link')
    viewer = data.get('viewerLink') or data.get('viewer_link')
    fast = data.get('link')
    expires_raw = data.get('expiresAt') or data.get('expires_at')
    expires_at = parse_datetime(expires_raw) if expires_raw else None
    if expires_at and timezone.is_naive(expires_at):
        expires_at = timezone.make_aware(expires_at)

    if not report and not viewer and not fast:
        return False

    faturamento.codigo_relatorio = accession_number
    if report:
        faturamento.link_laudo = report[:500]
    if viewer:
        faturamento.link_viewer = viewer[:500]
    if fast:
        faturamento.link_fastshare = fast[:500]
    faturamento.laudo_expires_at = expires_at
    faturamento.save(update_fields=[
        'codigo_relatorio', 'link_laudo', 'link_viewer', 'link_fastshare', 'laudo_expires_at',
    ])
    return True


def sincronizar_links_laudos(
    empresa,
    data_inicio: date,
    data_fim: date,
    *,
    convenio_nome: str | None = None,
    apenas_convenios_exige_laudo: bool = True,
    dry_run: bool = False,
) -> dict:
    """
    Busca links de laudo liberados (HIS) para faturamentos do período.
    Filtra convênios configurados com exige_laudo=True quando aplicável.
    """
    creds = credenciais_da_empresa(empresa)
    if not creds:
        raise MedcloudAPIError('Credenciais MedCloud não configuradas para esta empresa.')
    if not creds.his_api_key:
        raise MedcloudAPIError('API Key HIS não configurada.')

    cfg = getattr(empresa, 'medcloud_config', None)
    convenios_laudo: set[str] = set()
    if cfg and apenas_convenios_exige_laudo:
        convenios_laudo = {
            c.convenio_nome.lower()
            for c in cfg.convenios.filter(exige_laudo=True)
        }

    qs = FaturamentoMedico.objects.filter(
        empresa=empresa,
        data__gte=data_inicio,
        data__lte=data_fim,
    ).exclude(codigo_relatorio__isnull=True).exclude(codigo_relatorio='')

    if convenio_nome:
        qs = qs.filter(convenio__iexact=convenio_nome)
    elif convenios_laudo:
        filtro_conv = Q()
        for nome in convenios_laudo:
            filtro_conv |= Q(convenio__iexact=nome)
        qs = qs.filter(filtro_conv)

    stats = {
        'candidatos': qs.count(),
        'atualizados': 0,
        'sem_laudo': 0,
        'erros': 0,
        'pulados_link_valido': 0,
    }

    for fat in qs.iterator():
        if fat.link_laudo and not _link_expirado(fat):
            stats['pulados_link_valido'] += 1
            continue
        accession = (fat.codigo_relatorio or '').strip()
        if not accession:
            stats['sem_laudo'] += 1
            continue
        if dry_run:
            stats['atualizados'] += 1
            continue
        try:
            ok = _atualizar_links_laudo(fat, accession, creds)
            if ok:
                stats['atualizados'] += 1
            else:
                stats['sem_laudo'] += 1
        except MedcloudAPIError as exc:
            if exc.status_code == 404:
                stats['sem_laudo'] += 1
            else:
                logger.warning('HIS %s: %s', accession, exc)
                stats['erros'] += 1
        except Exception:
            logger.exception('Erro ao buscar laudo %s', accession)
            stats['erros'] += 1

    return stats
