from django.db import migrations, models


def marcar_empresas_com_conta_azul_ativa(apps, schema_editor):
    Empresa = apps.get_model('empresa', 'Empresa')
    ContaAzulConfig = apps.get_model('dashboard', 'ContaAzulConfig')
    for cfg in ContaAzulConfig.objects.filter(ativo=True):
        if (cfg.refresh_token_cifrado or '').strip():
            Empresa.objects.filter(pk=cfg.empresa_id).update(integracao_conta_azul=True)


class Migration(migrations.Migration):

    dependencies = [
        ('empresa', '0024_alter_empresa_nfse_portal_nacional_login'),
        ('dashboard', '0005_vendas_ca_conta_azul'),
    ]

    operations = [
        migrations.AddField(
            model_name='empresa',
            name='integracao_conta_azul',
            field=models.BooleanField(
                default=False,
                help_text='Financeiro (CAR/CAP etc.) via API Conta Azul — desativa geração local de CAR pela NFSe.',
                verbose_name='Integração Conta Azul',
            ),
        ),
        migrations.RunPython(marcar_empresas_com_conta_azul_ativa, migrations.RunPython.noop),
    ]
