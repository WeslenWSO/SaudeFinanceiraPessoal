from agendador_tarefas.letreiro import mensagens_letreiro_usuario


def tarefas_letreiro(request):
    if not request.user.is_authenticated:
        return {'tarefas_letreiro_mensagens': []}
    empresa_id = request.session.get('empresa_id')
    return {
        'tarefas_letreiro_mensagens': mensagens_letreiro_usuario(
            request.user,
            empresa_id=empresa_id,
        ),
    }
