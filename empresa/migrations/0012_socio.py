# Generated manually for model Socio

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('empresa', '0011_empresa_codigo_externo'),
    ]

    operations = [
        migrations.CreateModel(
            name='Socio',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nome', models.CharField(max_length=255, verbose_name='Nome')),
                ('qualificacao', models.CharField(blank=True, default='', max_length=255, verbose_name='Qualificação')),
                ('documento', models.CharField(blank=True, default='', max_length=20, verbose_name='CPF/CNPJ')),
                ('representante_legal', models.CharField(blank=True, default='', max_length=255, verbose_name='Representante Legal')),
                ('pais', models.CharField(blank=True, default='', max_length=100, verbose_name='País')),
                ('empresa', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='socios', to='empresa.empresa', verbose_name='Empresa')),
            ],
            options={
                'verbose_name': 'Sócio',
                'verbose_name_plural': 'Sócios',
                'ordering': ['nome'],
            },
        ),
        migrations.AddConstraint(
            model_name='socio',
            constraint=models.UniqueConstraint(fields=('empresa', 'nome', 'qualificacao'), name='empresa_socio_uniq_empresa_nome_qualificacao'),
        ),
    ]
