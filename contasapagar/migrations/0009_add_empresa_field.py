# Migration 0009: adiciona empresa_id só se a coluna ainda não existir (evita "duplicate column")

from django.db import migrations, models
import django.db.models.deletion


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


def add_empresa_column_if_missing(apps, schema_editor):
    from django.db import connection
    from django.db.utils import OperationalError
    table = 'contasapagar_contasapagar'
    column = 'empresa_id'
    with connection.cursor() as cursor:
        if column_exists(cursor, table, column, connection.vendor):
            return
    try:
        if connection.vendor == 'mysql':
            schema_editor.execute(
                "ALTER TABLE contasapagar_contasapagar ADD COLUMN empresa_id bigint NULL"
            )
            schema_editor.execute(
                "ALTER TABLE contasapagar_contasapagar ADD CONSTRAINT "
                "contasapagar_contasapagar_empresa_id_fk FOREIGN KEY (empresa_id) "
                "REFERENCES empresa_empresa(id)"
            )
        elif connection.vendor == 'sqlite':
            schema_editor.execute(
                "ALTER TABLE contasapagar_contasapagar ADD COLUMN empresa_id integer NULL "
                "REFERENCES empresa_empresa(id)"
            )
        else:
            schema_editor.execute(
                "ALTER TABLE contasapagar_contasapagar ADD COLUMN empresa_id bigint NULL"
            )
            schema_editor.execute(
                "ALTER TABLE contasapagar_contasapagar ADD CONSTRAINT "
                "contasapagar_contasapagar_empresa_id_fk FOREIGN KEY (empresa_id) "
                "REFERENCES empresa_empresa(id)"
            )
    except OperationalError as e:
        if 'duplicate column' in str(e).lower():
            return
        raise


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('contasapagar', '0008_auto_20251025_1534'),
        ('empresa', '0001_initial'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name='contasapagar',
                    name='empresa',
                    field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='empresa.empresa', verbose_name='Empresa'),
                ),
            ],
            database_operations=[
                migrations.RunPython(add_empresa_column_if_missing, noop_reverse),
            ],
        ),
    ]
