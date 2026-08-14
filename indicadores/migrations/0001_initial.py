from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('empresa', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Indicador',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('area', models.CharField(choices=[('MUSCULACAO', 'Musculação'), ('ATENDENTE', 'Atendente')], max_length=20, verbose_name='Área')),
                ('nome', models.CharField(max_length=120, verbose_name='Indicador')),
                ('ordem', models.PositiveSmallIntegerField(default=0, verbose_name='Ordem')),
                ('ativo', models.BooleanField(default=True, verbose_name='Ativo')),
                ('empresa', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='indicadores', to='empresa.empresa', verbose_name='Empresa')),
            ],
            options={
                'verbose_name': 'Indicador',
                'verbose_name_plural': 'Indicadores',
                'ordering': ['area', 'ordem', 'nome'],
                'unique_together': {('empresa', 'area', 'nome')},
            },
        ),
    ]
