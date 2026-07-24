# Corrige FK de contasareceber_baixacontaareceber.conta_banco_id:
# Deve referenciar extrato_contabancaria(id), não contabanco_contabanco
from django.db import migrations, connection


def fix_fk(apps, schema_editor):
    if connection.vendor != "mysql":
        return
    with connection.cursor() as cursor:
        # Buscar nome da FK atual em conta_banco_id
        cursor.execute("""
            SELECT CONSTRAINT_NAME FROM information_schema.KEY_COLUMN_USAGE
            WHERE TABLE_SCHEMA = DATABASE()
            AND TABLE_NAME = 'contasareceber_baixacontaareceber'
            AND COLUMN_NAME = 'conta_banco_id'
            AND REFERENCED_TABLE_NAME IS NOT NULL;
        """)
        row = cursor.fetchone()
        fk_name = row[0] if row else None

        cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")
        try:
            if fk_name:
                cursor.execute(
                    f"ALTER TABLE contasareceber_baixacontaareceber DROP FOREIGN KEY `{fk_name}`;"
                )
        except Exception:
            pass
        try:
            cursor.execute(
                "ALTER TABLE contasareceber_baixacontaareceber "
                "ADD CONSTRAINT fk_baixa_conta_banco_extrato "
                "FOREIGN KEY (conta_banco_id) REFERENCES extrato_contabancaria(id);"
            )
        except Exception as e:
            err = str(e).lower()
            if "duplicate" not in err and "1061" not in err and "errno 1826" not in err:
                raise
        cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('extrato', '0022_lancamento_extrato_arquivo_status_importacao'),
    ]

    operations = [
        migrations.RunPython(fix_fk, noop_reverse),
    ]
