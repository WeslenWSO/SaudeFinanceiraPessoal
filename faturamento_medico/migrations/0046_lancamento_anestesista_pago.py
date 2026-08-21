from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('faturamento_medico', '0045_lancamento_anestesista_sedacao'),
    ]

    operations = [
        migrations.AddField(
            model_name='lancamentoanestesistaexame',
            name='pago',
            field=models.BooleanField(
                default=False,
                help_text='Repasse da sedação já pago ao anestesista.',
                verbose_name='Pago',
            ),
        ),
    ]
