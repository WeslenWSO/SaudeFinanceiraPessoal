from agendador_tarefas.letreiro import (
    SESSION_POPUP_TAREFAS,
    mensagens_letreiro_usuario,
)


def tarefas_letreiro(request):
    if not request.user.is_authenticated:
        return {'tarefas_letreiro_popup': None}
    if not request.session.pop(SESSION_POPUP_TAREFAS, False):
        return {'tarefas_letreiro_popup': None}
    try:
        mensagens = mensagens_letreiro_usuario(request.user)
    except Exception:
        return {'tarefas_letreiro_popup': None}
    if not mensagens:
        return {'tarefas_letreiro_popup': None}
    return {'tarefas_letreiro_popup': mensagens}
