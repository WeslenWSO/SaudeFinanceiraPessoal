# Migration 0002: Remove banco, add conta_banco (só adiciona conta_banco_id se não existir - evita duplicate em produção)
# Se no servidor existir 0002_initial que também adiciona conta_banco, apague 0002_initial.

import django.db.models.deletion
from django.db import migrations, models


def column_exists(cursor, table, column, vendor):
    if vendor == 'mysql':
        cursor.execute("""
            SELECT COUNT(1) FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = %s AND COLUMN_NAME = %s
        """, [table, column])
    elif vendor == 'sqlite':
        cursor.execute(
            "SELECT COUNT(1) FROM pragma_table_info(%s) WHERE name = %s" % (repr(table), repr(column))
        )
    else:
        cursor.execute("""
            SELECT COUNT(1) FROM information_schema.columns
            WHERE table_name = %s AND column_name = %s
        """, [table, column])
    return cursor.fetchone()[0] > 0


def add_conta_banco_if_missing(apps, schema_editor):
    from django.db import connection
    from django.db.utils import OperationalError
    table = 'contasareceber_contaareceber'
    column = 'conta_banco_id'
    with connection.cursor() as cursor:
        if column_exists(cursor, table, column, connection.vendor):
            return
    try:
        if connection.vendor == 'mysql':
            schema_editor.execute(
                "ALTER TABLE contasareceber_contaareceber ADD COLUMN conta_banco_id bigint NULL"
            )
            schema_editor.execute(
                "ALTER TABLE contasareceber_contaareceber ADD CONSTRAINT "
                "contasareceber_conta_conta_banco_id_fk FOREIGN KEY (conta_banco_id) "
                "REFERENCES extrato_contabancaria(id)"
            )
        elif connection.vendor == 'sqlite':
            schema_editor.execute(
                "ALTER TABLE contasareceber_contaareceber ADD COLUMN conta_banco_id integer NULL "
                "REFERENCES extrato_contabancaria(id)"
            )
        else:
            schema_editor.execute(
                "ALTER TABLE contasareceber_contaareceber ADD COLUMN conta_banco_id bigint NULL"
            )
            schema_editor.execute(
                "ALTER TABLE contasareceber_contaareceber ADD CONSTRAINT "
                "contasareceber_conta_conta_banco_id_fk FOREIGN KEY (conta_banco_id) "
                "REFERENCES extrato_contabancaria(id)"
            )
    except OperationalError as e:
        if 'duplicate column' in str(e).lower():
            return
        raise


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('extrato', '0001_initial'),
        ('contasareceber', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='contaareceber',
            name='banco',
        ),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name='contaareceber',
                    name='conta_banco',
                    field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='extrato.contabancaria', verbose_name='Conta/Banco'),
                ),
            ],
            database_operations=[
                migrations.RunPython(add_conta_banco_if_missing, noop_reverse),
            ],
        ),
        migrations.AddField(
            model_name='contaareceber',
            name='desconto',
            field=models.DecimalField(blank=True, decimal_places=2, default=0, max_digits=10, null=True, verbose_name='Desconto'),
        ),
        migrations.AddField(
            model_name='contaareceber',
            name='juros',
            field=models.DecimalField(blank=True, decimal_places=2, default=0, max_digits=10, null=True, verbose_name='Juros'),
        ),
        migrations.AddField(
            model_name='contaareceber',
            name='tarifas',
            field=models.DecimalField(blank=True, decimal_places=2, default=0, max_digits=10, null=True, verbose_name='Tarifas'),
        ),
        migrations.AlterField(
            model_name='contaareceber',
            name='valor_recebido',
            field=models.DecimalField(blank=True, decimal_places=2, default=0, max_digits=10, null=True, verbose_name='Valor Recebido'),
        ),
    ]
