from datetime import date

from django.db import migrations, models


def atribuir_mes_metas_existentes(apps, schema_editor):
    Meta = apps.get_model('faturamento_medico', 'MetaModalidadeSolicitante')
    hoje = date.today()
    Meta.objects.filter(ano__isnull=True).update(ano=hoje.year, mes=hoje.month)


class Migration(migrations.Migration):

    dependencies = [
        ('faturamento_medico', '0035_metamodalidadesolicitante'),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name='metamodalidadesolicitante',
            unique_together=set(),
        ),
        migrations.AddField(
            model_name='metamodalidadesolicitante',
            name='ano',
            field=models.PositiveIntegerField(null=True, verbose_name='Ano'),
        ),
        migrations.AddField(
            model_name='metamodalidadesolicitante',
            name='mes',
            field=models.PositiveIntegerField(null=True, verbose_name='Mês'),
        ),
        migrations.RunPython(atribuir_mes_metas_existentes, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='metamodalidadesolicitante',
            name='ano',
            field=models.PositiveIntegerField(verbose_name='Ano'),
        ),
        migrations.AlterField(
            model_name='metamodalidadesolicitante',
            name='mes',
            field=models.PositiveIntegerField(verbose_name='Mês'),
        ),
        migrations.AlterUniqueTogether(
            name='metamodalidadesolicitante',
            unique_together={('empresa', 'solicitante', 'ano', 'mes', 'modalidade')},
        ),
    ]
