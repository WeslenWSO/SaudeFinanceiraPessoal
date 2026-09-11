def cotacao_context(request):
    from django.db.utils import DatabaseError

    from empresa.models import Empresa

    empresa = None
    if request.session.get('empresa_id'):
        try:
            empresa = Empresa.objects.get(id=request.session['empresa_id'])
        except (Empresa.DoesNotExist, DatabaseError):
            pass
    return {
        'cotacao': "5.20",
        'empresa_atual': empresa
    }


def vencimentos_dia_popup(request):
    """Popup one-shot após login/seleção de empresa com despesas vencendo hoje."""
    if not request.user.is_authenticated or not request.session.get('empresa_id'):
        return {'vencimentos_dia_popup': None}

    from SaudeFinanceira.services.vencimentos_dia import (
        SESSION_POPUP_VENCIMENTOS,
        despesas_vencendo_hoje,
    )

    if not request.session.pop(SESSION_POPUP_VENCIMENTOS, False):
        return {'vencimentos_dia_popup': None}

    try:
        dados = despesas_vencendo_hoje(request.session['empresa_id'])
    except Exception:
        return {'vencimentos_dia_popup': None}

    if not dados['itens']:
        return {'vencimentos_dia_popup': None}
    return {'vencimentos_dia_popup': dados}