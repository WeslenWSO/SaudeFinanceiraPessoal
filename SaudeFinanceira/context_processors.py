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