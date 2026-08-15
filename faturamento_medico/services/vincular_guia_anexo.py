"""Vincula PDF de guia renomeada ao faturamento correspondente."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from django.core.files.base import ContentFile
from django.db.models import Q

from faturamento_medico.models import DocumentoAnexado, FaturamentoMedico
from faturamento_medico.services.atualizar_faturamento_convenio import (
    _normalizar_texto,
    _similaridade,
)

JANELA_DIAS_APOS_GUIA = 20
JANELA_SUGESTAO_ANTES = 7
JANELA_SUGESTAO_DEPOIS = 30
LIMITE_SUGESTOES = 5
SIMILARIDADE_SUGESTAO_MIN = 0.55
_STATUS_IGNORAR = ('Cancelado', 'Desistência', 'Deletado')


@dataclass
class SugestaoFaturamento:
    faturamento_id: int
    paciente: str
    convenio: str
    data_procedimento: str
    procedimentos: str
    score: float
    motivo: str


@dataclass
class ResultadoVinculoGuia:
    ok: bool = False
    faturamento_id: int | None = None
    paciente: str = ''
    data_procedimento: str = ''
    mensagem: str = ''
    erro: str = ''
    sugestoes: list[SugestaoFaturamento] = field(default_factory=list)


def _parse_data_guia(data_str: str) -> date | None:
    data_str = (data_str or '').strip()
    for fmt in ('%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d'):
        try:
            return datetime.strptime(data_str, fmt).date()
        except ValueError:
            continue
    return None


def _filtro_convenio_guia(convenio: str) -> Q:
    label = (convenio or '').strip().upper()
    if not label:
        return Q()
    if label == 'FUSEX':
        return Q(convenio__iexact='FUSEX')
    if label == 'PM':
        return Q(convenio__icontains='POLICIA MILITAR') | Q(convenio__icontains='PMAC')
    if label == 'BOMBEIRO':
        return Q(convenio__icontains='BOMBEIRO')
    if label == 'POSTAL':
        return Q(convenio__icontains='POSTAL')
    if label == 'BRADESCO':
        return Q(convenio__icontains='BRADESCO')
    if label == 'CASSI':
        return Q(convenio__icontains='CASSI')
    if label == 'GEAP':
        return Q(convenio__icontains='GEAP')
    return Q(convenio__icontains=label)


def _paciente_compativel_guia(nome_guia: str, fat: FaturamentoMedico) -> bool:
    paciente_norm = _normalizar_texto(nome_guia)
    if not paciente_norm:
        return False
    for candidato in (fat.nome, fat.nome_associado):
        if not candidato:
            continue
        cand_norm = _normalizar_texto(candidato)
        if cand_norm == paciente_norm:
            return True
        if _similaridade(nome_guia, candidato) >= 0.82:
            return True
    return False


def _score_faturamento(fat: FaturamentoMedico, nome_guia: str, data_guia: date) -> float:
    score = 0.0
    for candidato in (fat.nome, fat.nome_associado):
        if candidato:
            score = max(score, _similaridade(nome_guia, candidato) * 10.0)
    if fat.data and data_guia:
        delta = (fat.data - data_guia).days
        if 0 <= delta <= JANELA_DIAS_APOS_GUIA:
            score += 2.0 - (delta / JANELA_DIAS_APOS_GUIA)
    return score


def _convenio_compativel_guia(convenio_guia: str, convenio_fat: str) -> bool:
    label = (convenio_guia or '').strip().upper()
    fat = (convenio_fat or '').strip().upper()
    if not label or not fat:
        return False
    if label == 'FUSEX':
        return fat == 'FUSEX'
    if label == 'PM':
        return 'POLICIA MILITAR' in fat or 'PMAC' in fat
    if label == 'BOMBEIRO':
        return 'BOMBEIRO' in fat
    return label in fat or fat in label


def _procedimentos_resumo(fat: FaturamentoMedico, limite: int = 3) -> str:
    itens = list(fat.itens_servico.all()[:limite])
    if not itens:
        serv = (fat.servico or '').strip()
        return serv or '—'
    partes = []
    for item in itens:
        nome = (item.servico or item.codigo_servico or '').strip()
        if nome:
            partes.append(nome[:60])
    extra = fat.itens_servico.count() - len(itens)
    texto = ' · '.join(partes)
    if extra > 0:
        texto += f' (+{extra})'
    return texto or '—'


def _serializar_sugestao(fat: FaturamentoMedico, score: float, motivo: str) -> SugestaoFaturamento:
    return SugestaoFaturamento(
        faturamento_id=fat.id,
        paciente=fat.nome or '',
        convenio=fat.convenio or '',
        data_procedimento=fat.data.strftime('%d/%m/%Y') if fat.data else '',
        procedimentos=_procedimentos_resumo(fat),
        score=round(score, 2),
        motivo=motivo,
    )


def sugerir_faturamentos_proximos(
    *,
    empresa_id: int,
    nome_paciente: str,
    convenio: str,
    data_guia_str: str,
    limite: int = LIMITE_SUGESTOES,
) -> list[SugestaoFaturamento]:
    data_guia = _parse_data_guia(data_guia_str)
    if not data_guia:
        return []

    data_inicio = data_guia - timedelta(days=JANELA_SUGESTAO_ANTES)
    data_fim = data_guia + timedelta(days=JANELA_SUGESTAO_DEPOIS)
    qs = (
        FaturamentoMedico.objects.filter(
            empresa_id=empresa_id,
            data__gte=data_inicio,
            data__lte=data_fim,
        )
        .exclude(status_agendamento__in=_STATUS_IGNORAR)
        .prefetch_related('itens_servico')
        .order_by('data', 'id')
    )

    pontuados: list[tuple[float, FaturamentoMedico, str]] = []
    for fat in qs:
        score = 0.0
        motivos: list[str] = []

        sim_nome = 0.0
        for candidato in (fat.nome, fat.nome_associado):
            if candidato:
                sim_nome = max(sim_nome, _similaridade(nome_paciente, candidato))
        if sim_nome >= SIMILARIDADE_SUGESTAO_MIN:
            score += sim_nome * 8.0
            motivos.append(f'nome {int(sim_nome * 100)}%')
        elif nome_paciente and fat.nome:
            pac_norm = _normalizar_texto(nome_paciente)
            fat_norm = _normalizar_texto(fat.nome)
            if pac_norm[:4] and pac_norm[:4] in fat_norm:
                score += 2.0
                motivos.append('nome parcial')

        if _convenio_compativel_guia(convenio, fat.convenio or ''):
            score += 3.0
            motivos.append('convênio')
        elif convenio and (convenio.upper() in (fat.convenio or '').upper()):
            score += 1.5
            motivos.append('convênio parecido')

        if fat.data and data_guia:
            delta = (fat.data - data_guia).days
            if -JANELA_SUGESTAO_ANTES <= delta <= JANELA_SUGESTAO_DEPOIS:
                score += max(0.5, 2.5 - abs(delta) / 12.0)
                motivos.append(f'data {fat.data.strftime("%d/%m")}')

        if score >= 2.0:
            pontuados.append((score, fat, ', '.join(motivos)))

    pontuados.sort(key=lambda x: (-x[0], x[1].data or date.min))
    vistos: set[int] = set()
    sugestoes: list[SugestaoFaturamento] = []
    for score, fat, motivo in pontuados:
        if fat.id in vistos:
            continue
        vistos.add(fat.id)
        sugestoes.append(_serializar_sugestao(fat, score, motivo))
        if len(sugestoes) >= limite:
            break
    return sugestoes


def buscar_faturamentos_manual(
    *,
    empresa_id: int,
    termo: str = '',
    convenio: str = '',
    data_guia_str: str = '',
    limite: int = 20,
) -> list[SugestaoFaturamento]:
    qs = (
        FaturamentoMedico.objects.filter(empresa_id=empresa_id)
        .exclude(status_agendamento__in=_STATUS_IGNORAR)
        .prefetch_related('itens_servico')
        .order_by('-data', '-id')
    )

    termo = (termo or '').strip()
    if termo:
        qs = qs.filter(Q(nome__icontains=termo) | Q(nome_associado__icontains=termo))

    if convenio:
        qs = qs.filter(_filtro_convenio_guia(convenio))

    data_guia = _parse_data_guia(data_guia_str) if data_guia_str else None
    if data_guia:
        qs = qs.filter(
            data__gte=data_guia - timedelta(days=JANELA_SUGESTAO_DEPOIS),
            data__lte=data_guia + timedelta(days=JANELA_SUGESTAO_DEPOIS),
        )

    return [
        _serializar_sugestao(fat, 0.0, 'busca manual')
        for fat in qs[:limite]
    ]


def sugestao_para_dict(s: SugestaoFaturamento) -> dict:
    return {
        'faturamento_id': s.faturamento_id,
        'paciente': s.paciente,
        'convenio': s.convenio,
        'data_procedimento': s.data_procedimento,
        'procedimentos': s.procedimentos,
        'score': s.score,
        'motivo': s.motivo,
    }


def anexar_guia_por_faturamento_id(
    *,
    empresa_id: int,
    faturamento_id: int,
    pdf_bytes: bytes,
    nome_arquivo: str,
) -> ResultadoVinculoGuia:
    resultado = ResultadoVinculoGuia()
    try:
        fat = FaturamentoMedico.objects.get(pk=faturamento_id, empresa_id=empresa_id)
    except FaturamentoMedico.DoesNotExist:
        resultado.erro = 'Faturamento não encontrado.'
        return resultado

    if fat.documentos_anexados.filter(nome=nome_arquivo).exists():
        resultado.ok = True
        resultado.faturamento_id = fat.id
        resultado.paciente = fat.nome or ''
        resultado.data_procedimento = fat.data.strftime('%d/%m/%Y') if fat.data else ''
        resultado.mensagem = f'Guia já anexada ao faturamento #{fat.id}.'
        return resultado

    DocumentoAnexado.objects.create(
        faturamento=fat,
        arquivo=ContentFile(pdf_bytes, name=nome_arquivo),
        nome=nome_arquivo,
        descricao='Guia vinculada manualmente',
    )
    resultado.ok = True
    resultado.faturamento_id = fat.id
    resultado.paciente = fat.nome or ''
    resultado.data_procedimento = fat.data.strftime('%d/%m/%Y') if fat.data else ''
    resultado.mensagem = f'Anexado ao faturamento #{fat.id} ({resultado.paciente}, {resultado.data_procedimento}).'
    return resultado


def buscar_faturamento_para_guia(
    *,
    empresa_id: int,
    nome_paciente: str,
    convenio: str,
    data_guia_str: str,
) -> tuple[FaturamentoMedico | None, str]:
    data_guia = _parse_data_guia(data_guia_str)
    if not data_guia:
        return None, 'Data da guia inválida para busca no sistema.'

    data_limite = data_guia + timedelta(days=JANELA_DIAS_APOS_GUIA)
    qs = (
        FaturamentoMedico.objects.filter(
            empresa_id=empresa_id,
            data__gte=data_guia,
            data__lte=data_limite,
        )
        .exclude(status_agendamento__in=_STATUS_IGNORAR)
        .filter(_filtro_convenio_guia(convenio))
        .order_by('data', 'id')
    )

    candidatos = [fat for fat in qs if _paciente_compativel_guia(nome_paciente, fat)]
    if not candidatos:
        return None, (
            f'Nenhum procedimento encontrado para {nome_paciente} / {convenio} '
            f'entre {data_guia.strftime("%d/%m/%Y")} e {data_limite.strftime("%d/%m/%Y")}.'
        )

    if len(candidatos) == 1:
        return candidatos[0], ''

    melhor = max(candidatos, key=lambda fat: _score_faturamento(fat, nome_paciente, data_guia))
    return melhor, ''


def anexar_guia_ao_faturamento(
    *,
    empresa_id: int,
    nome_paciente: str,
    convenio: str,
    data_guia_str: str,
    pdf_bytes: bytes,
    nome_arquivo: str,
) -> ResultadoVinculoGuia:
    resultado = ResultadoVinculoGuia()
    fat, erro_busca = buscar_faturamento_para_guia(
        empresa_id=empresa_id,
        nome_paciente=nome_paciente,
        convenio=convenio,
        data_guia_str=data_guia_str,
    )
    if not fat:
        resultado.erro = erro_busca
        resultado.sugestoes = sugerir_faturamentos_proximos(
            empresa_id=empresa_id,
            nome_paciente=nome_paciente,
            convenio=convenio,
            data_guia_str=data_guia_str,
        )
        return resultado

    if fat.documentos_anexados.filter(nome=nome_arquivo).exists():
        resultado.ok = True
        resultado.faturamento_id = fat.id
        resultado.paciente = fat.nome or ''
        resultado.data_procedimento = fat.data.strftime('%d/%m/%Y') if fat.data else ''
        resultado.mensagem = f'Guia já anexada ao faturamento #{fat.id}.'
        return resultado

    DocumentoAnexado.objects.create(
        faturamento=fat,
        arquivo=ContentFile(pdf_bytes, name=nome_arquivo),
        nome=nome_arquivo,
        descricao='Guia renomeada automaticamente',
    )

    resultado.ok = True
    resultado.faturamento_id = fat.id
    resultado.paciente = fat.nome or ''
    resultado.data_procedimento = fat.data.strftime('%d/%m/%Y') if fat.data else ''
    resultado.mensagem = f'Anexado ao faturamento #{fat.id} ({resultado.paciente}, {resultado.data_procedimento}).'
    return resultado
