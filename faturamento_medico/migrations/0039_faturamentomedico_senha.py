from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('faturamento_medico', '0038_alter_faturamentomedico_guia_lancada_protocolo'),
    ]

    operations = [
        migrations.AddField(
            model_name='faturamentomedico',
            name='senha',
            field=models.CharField(blank=True, default='', max_length=50, verbose_name='Senha'),
        ),
    ]
