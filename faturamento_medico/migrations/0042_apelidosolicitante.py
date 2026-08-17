from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('empresa', '0001_initial'),
        ('faturamento_medico', '0041_finalizar_faturamentos_extrato_baixado'),
    ]

    operations = [
        migrations.CreateModel(
            name='ApelidoSolicitante',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('apelido', models.CharField(max_length=200, verbose_name='Apelido')),
                ('grafia', models.CharField(
                    help_text='Nome exato do campo médico solicitante no faturamento.',
                    max_length=200,
                    verbose_name='Grafia no RIS',
                )),
                ('empresa', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='apelidos_solicitante',
                    to='empresa.empresa',
                    verbose_name='Empresa',
                )),
            ],
            options={
                'verbose_name': 'Apelido de solicitante',
                'verbose_name_plural': 'Apelidos de solicitante',
                'ordering': ['apelido', 'grafia'],
            },
        ),
        migrations.AddConstraint(
            model_name='apelidosolicitante',
            constraint=models.UniqueConstraint(
                fields=('empresa', 'grafia'),
                name='uniq_apelido_solicitante_empresa_grafia',
            ),
        ),
    ]
