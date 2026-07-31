# MedCloud integration (RIS/HIS)

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('empresa', '0024_alter_empresa_nfse_portal_nacional_login'),
        ('faturamento_medico', '0030_extratopagamentoconvenio_lote_faturamento'),
    ]

    operations = [
        migrations.AddField(
            model_name='faturamentomedico',
            name='medcloud_schedule_id',
            field=models.BigIntegerField(blank=True, db_index=True, null=True, verbose_name='ID Agendamento MedCloud'),
        ),
        migrations.AddField(
            model_name='faturamentomedico',
            name='link_laudo',
            field=models.URLField(blank=True, max_length=500, null=True, verbose_name='Link do Laudo'),
        ),
        migrations.AddField(
            model_name='faturamentomedico',
            name='link_viewer',
            field=models.URLField(blank=True, max_length=500, null=True, verbose_name='Link Viewer DICOM'),
        ),
        migrations.AddField(
            model_name='faturamentomedico',
            name='link_fastshare',
            field=models.URLField(blank=True, max_length=500, null=True, verbose_name='Link FastShare'),
        ),
        migrations.AddField(
            model_name='faturamentomedico',
            name='laudo_expires_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Expiração do Link do Laudo'),
        ),
        migrations.CreateModel(
            name='MedcloudConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ativo', models.BooleanField(default=True, verbose_name='Integração ativa')),
                ('ris_base_url', models.URLField(default='https://api.ris.medcloud.co', max_length=255, verbose_name='URL base RIS')),
                ('ris_username', models.CharField(blank=True, default='', max_length=100, verbose_name='Usuário RIS')),
                ('ris_password_cifrada', models.TextField(blank=True, default='', verbose_name='Senha RIS (cifrada)')),
                ('ris_clinic_id', models.PositiveIntegerField(default=0, verbose_name='ID da clínica (clinicIdToAccess)')),
                ('ris_lista_agendas_path', models.CharField(default='/schedules', help_text='GET com query startDate, endDate, status, partnerId. Confirme com a MedCloud.', max_length=255, verbose_name='Path listagem de agendas')),
                ('his_base_url', models.URLField(default='https://his.medcloud.co/v1/his', max_length=255, verbose_name='URL base HIS')),
                ('his_api_key_cifrada', models.TextField(blank=True, default='', verbose_name='API Key HIS (cifrada)')),
                ('empresa', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='medcloud_config', to='empresa.empresa', verbose_name='Empresa')),
            ],
            options={
                'verbose_name': 'Configuração MedCloud',
                'verbose_name_plural': 'Configurações MedCloud',
            },
        ),
        migrations.CreateModel(
            name='MedcloudConvenioParceiro',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('convenio_nome', models.CharField(help_text='Deve coincidir com o campo convênio do faturamento médico.', max_length=100, verbose_name='Nome do convênio (faturamento)')),
                ('partner_id', models.PositiveIntegerField(verbose_name='Partner ID MedCloud')),
                ('exige_laudo', models.BooleanField(default=True, help_text='Convênios marcados entram na busca diária de links de laudo.', verbose_name='Exige laudo liberado')),
                ('config', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='convenios', to='faturamento_medico.medcloudconfig', verbose_name='Configuração MedCloud')),
            ],
            options={
                'verbose_name': 'Convênio MedCloud',
                'verbose_name_plural': 'Convênios MedCloud',
                'ordering': ['convenio_nome'],
                'unique_together': {('config', 'convenio_nome')},
            },
        ),
    ]
