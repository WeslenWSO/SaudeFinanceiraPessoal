from decimal import Decimal

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('empresa', '0001_initial'),
        ('faturamento_medico', '0049_faturamentomedico_acerto_caixa'),
    ]

    operations = [
        migrations.CreateModel(
            name='AcertoCaixaFechamento',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('caixa', models.CharField(
                    choices=[
                        ('Beatriz', 'Caixa - Beatriz'),
                        ('Estela', 'Caixa - Estela'),
                        ('Vitoria', 'Caixa - Vitoria'),
                        ('Joao', 'Caixa - João'),
                        ('Marcela', 'Caixa - Marcela'),
                        ('Laura', 'Caixa - Laura'),
                        ('Thaine', 'Caixa - Thaine'),
                    ],
                    max_length=40,
                    verbose_name='Caixa',
                )),
                ('data_inicio', models.DateField(verbose_name='Data início')),
                ('data_fim', models.DateField(verbose_name='Data fim')),
                ('saldo_total', models.DecimalField(
                    decimal_places=2,
                    default=Decimal('0'),
                    max_digits=14,
                    verbose_name='Saldo (total NF)',
                )),
                ('resumo_saldos', models.JSONField(blank=True, default=list, verbose_name='Resumo por forma de pagamento')),
                ('filtros', models.JSONField(blank=True, default=dict, verbose_name='Filtros do acerto')),
                ('fechado_em', models.DateTimeField(default=django.utils.timezone.now, verbose_name='Fechado em')),
                ('reaberto_em', models.DateTimeField(blank=True, null=True, verbose_name='Reaberto em')),
                ('empresa', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='fechamentos_acerto_caixa',
                    to='empresa.empresa',
                    verbose_name='Empresa',
                )),
                ('fechado_por', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='fechamentos_acerto_caixa',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Fechado por',
                )),
                ('reaberto_por', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='reaberturas_acerto_caixa',
                    to=settings.AUTH_USER_MODEL,
                    verbose_name='Reaberto por',
                )),
            ],
            options={
                'verbose_name': 'Fechamento acerto de caixa',
                'verbose_name_plural': 'Fechamentos acerto de caixa',
                'ordering': ['-fechado_em'],
            },
        ),
        migrations.AddIndex(
            model_name='acertocaixafechamento',
            index=models.Index(
                fields=['empresa', 'caixa', 'data_inicio', 'data_fim'],
                name='faturamento_empresa_caixa_idx',
            ),
        ),
    ]
