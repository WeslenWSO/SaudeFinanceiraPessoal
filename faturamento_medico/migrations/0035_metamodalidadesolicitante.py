from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('empresa', '0001_initial'),
        ('faturamento_medico', '0034_lote_baixado'),
    ]

    operations = [
        migrations.CreateModel(
            name='MetaModalidadeSolicitante',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('solicitante', models.CharField(max_length=200, verbose_name='Solicitante')),
                ('modalidade', models.CharField(
                    choices=[
                        ('MR', 'Ressonância'),
                        ('US', 'Ultrassonografia'),
                        ('CR', 'Raio X'),
                        ('CT', 'Tomografia'),
                        ('MG', 'Mamografia'),
                        ('EG', 'EEG'),
                    ],
                    max_length=10,
                    verbose_name='Modalidade',
                )),
                ('meta', models.PositiveIntegerField(default=0, verbose_name='Meta')),
                ('empresa', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='metas_solicitante_modalidade',
                    to='empresa.empresa',
                    verbose_name='Empresa',
                )),
            ],
            options={
                'verbose_name': 'Meta por modalidade (solicitante)',
                'verbose_name_plural': 'Metas por modalidade (solicitante)',
                'ordering': ['solicitante', 'modalidade'],
                'unique_together': {('empresa', 'solicitante', 'modalidade')},
            },
        ),
    ]
