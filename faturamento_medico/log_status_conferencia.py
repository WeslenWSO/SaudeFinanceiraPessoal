"""Registro e consulta do histórico de status de conferência."""

from django.utils import timezone

from .models import LogStatusConferenciaItem


def _usuario_log(request):
    user = getattr(request, 'user', None)
    if user and user.is_authenticated:
        nome = (user.get_full_name() or '').strip() or user.get_username() or str(user.pk)
        return user, nome
    return None, 'Sistema'


def registrar_log_status_conferencia_item(request, item, status_conferencia):
    """Grava uma entrada quando o usuário altera o status de conferência."""
    status = (status_conferencia or '').strip() or 'PENDENTE'
    usuario, usuario_nome = _usuario_log(request)
    LogStatusConferenciaItem.objects.create(
        item_servico=item,
        usuario=usuario,
        usuario_nome=usuario_nome,
        status_conferencia=status,
    )


def serializar_logs_status_conferencia(logs):
    """Lista de dicts para resposta JSON (DATA — USUÁRIO — STATUS CONFERÊNCIA)."""
    resultado = []
    for log in logs:
        dt = timezone.localtime(log.data_hora)
        resultado.append({
            'data': dt.strftime('%d/%m/%Y %H:%M'),
            'usuario': log.usuario_nome or 'Sistema',
            'status_conferencia': log.status_conferencia,
        })
    return resultado
