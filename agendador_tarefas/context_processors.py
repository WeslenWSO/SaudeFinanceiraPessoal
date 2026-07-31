from agendador_tarefas.letreiro import mensagens_letreiro_usuario


def tarefas_letreiro(request):
    if not request.user.is_authenticated:
        return {'tarefas_letreiro_mensagens': []}
    try:
        return {
            'tarefas_letreiro_mensagens': mensagens_letreiro_usuario(request.user),
        }
    except Exception:
        return {'tarefas_letreiro_mensagens': []}
