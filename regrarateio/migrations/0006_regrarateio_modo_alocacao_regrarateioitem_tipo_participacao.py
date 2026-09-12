from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('regrarateio', '0005_alter_regrarateio_options_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='regrarateio',
            name='modo_alocacao',
            field=models.CharField(
                choices=[('P', 'Percentual fixo'), ('V', 'Valor na aplicação')],
                default='P',
                help_text='Percentual fixo: usa % cadastrados nos itens. Valor na aplicação: informe quanto vai para o sócio manual em cada título; o restante fica com o(s) sócio(s) residual.',
                max_length=1,
                verbose_name='Modo de alocação',
            ),
        ),
        migrations.AddField(
            model_name='regrarateioitem',
            name='tipo_participacao',
            field=models.CharField(
                choices=[
                    ('P', 'Percentual fixo'),
                    ('M', 'Valor manual na aplicação'),
                    ('R', 'Residual (restante)'),
                ],
                default='P',
                max_length=1,
                verbose_name='Tipo de participação',
            ),
        ),
    ]
