# Migration 0009 convertida em no-op para evitar KeyError no servidor.
# O modelo BaixaContaAReceber já tem conta_banco em 0003; esta migration não altera estado nem banco.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('contasareceber', '0003_baixacontaareceber'),
    ]

    operations = []
