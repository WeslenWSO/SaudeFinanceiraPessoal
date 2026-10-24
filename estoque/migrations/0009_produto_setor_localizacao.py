from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('estoque', '0008_quantidade_por_master'),
    ]

    operations = [
        migrations.AddField(
            model_name='produtoestoque',
            name='setor_localizacao',
            field=models.CharField(
                blank=True,
                choices=[
                    ('farmacia', 'Farmácia'),
                    ('ultrasson', 'Ultrassonografia'),
                    ('eletros', 'Eletros'),
                    ('outros', 'Outros'),
                    ('sedacao', 'Sedação'),
                    ('enfermagem', 'Enfermagem'),
                    ('raio_x', 'Raio-X'),
                    ('mamografia', 'Mamografia'),
                    ('imobilizado', 'Imobilizado'),
                ],
                default='',
                help_text='Para imobilizado: setor clínico onde o bem está.',
                max_length=32,
                verbose_name='Setor (localização)',
            ),
        ),
    ]
