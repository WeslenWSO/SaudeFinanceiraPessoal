from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def conceder_menu_todos_usuarios(apps, schema_editor):
    User = apps.get_model('auth', 'User')
    PermissaoMenuUsuario = apps.get_model('usuario', 'PermissaoMenuUsuario')
    codigos = [
        'dashboard', 'empresa', 'fornecedor', 'cliente', 'cobranca', 'categoria', 'socio',
        'regraimposto', 'regrarateio', 'usuario', 'faturamento_medico', 'agendador_tarefas',
        'convenios', 'cabecalhos', 'servicos_medicos', 'tabela_precos', 'nf_prestado',
        'dashboard_nfse', 'apuracao_nfse', 'apuracao_simples', 'import_xml', 'import_cancelamentos',
        'portal_nacional', 'portal_extensao', 'nf_entrada', 'contas_bancarias', 'contas_pagar',
        'contas_receber', 'categorizar_recebidos', 'extrato_import', 'lancamentos', 'movimentos',
        'recebiveis_maquininha', 'cartoes', 'faturas_cartao', 'emprestimos', 'fluxo_caixa',
        'planejamento', 'relatorio_mensal', 'resumo_fechamento', 'lancamentos_rateio',
        'cr_relatorio', 'cp_relatorio', 'por_categoria', 'por_socio', 'medcloud_ris',
        'conta_azul', 'cielo', 'stone',
    ]
    batch = []
    for user in User.objects.all().iterator():
        for codigo in codigos:
            batch.append(PermissaoMenuUsuario(usuario_id=user.id, codigo=codigo))
    if batch:
        PermissaoMenuUsuario.objects.bulk_create(batch, ignore_conflicts=True)


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('usuario', '0003_usuario_avatar'),
    ]

    operations = [
        migrations.CreateModel(
            name='PermissaoMenuUsuario',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('codigo', models.CharField(db_index=True, max_length=60, verbose_name='Código do menu')),
                ('usuario', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='permissoes_menu', to=settings.AUTH_USER_MODEL, verbose_name='Usuário de login')),
            ],
            options={
                'verbose_name': 'Permissão de menu',
                'verbose_name_plural': 'Permissões de menu',
                'ordering': ['usuario_id', 'codigo'],
            },
        ),
        migrations.AddConstraint(
            model_name='permissaomenuusuario',
            constraint=models.UniqueConstraint(fields=('usuario', 'codigo'), name='usuario_menu_codigo_unico'),
        ),
        migrations.RunPython(conceder_menu_todos_usuarios, migrations.RunPython.noop),
    ]
