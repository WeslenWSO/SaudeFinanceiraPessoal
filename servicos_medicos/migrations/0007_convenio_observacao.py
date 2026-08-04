from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('servicos_medicos', '0006_convenio_dias_fechamento_abertura'),
    ]

    operations = [
        migrations.AddField(
            model_name='convenio',
            name='observacao',
            field=models.TextField(
                blank=True,
                default='',
                help_text='Particularidades e regras específicas deste convênio.',
                verbose_name='Observação',
            ),
        ),
    ]
