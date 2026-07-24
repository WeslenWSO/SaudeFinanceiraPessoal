# Generated manually for adding conta_contabil field to ContaBancaria

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('extrato', '0018_force_fix_all_constraints'),
    ]

    operations = [
        migrations.AddField(
            model_name='contabancaria',
            name='conta_contabil',
            field=models.CharField(blank=True, max_length=20, null=True, verbose_name='Conta Contábil'),
        ),
    ]