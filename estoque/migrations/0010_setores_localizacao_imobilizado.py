from django.db import migrations, models

_SETOR_CHOICES = [
    ('farmacia', 'Farmácia'),
    ('ultrasson', 'Ultrassonografia'),
    ('eletros', 'Eletros'),
    ('outros', 'Outros'),
    ('sedacao', 'Sedação'),
    ('enfermagem', 'Enfermagem'),
    ('raio_x', 'Raio-X'),
    ('mamografia', 'Mamografia'),
    ('imobilizado', 'Imobilizado'),
    ('recepcao', 'Recepção'),
    ('sala_espera', 'Sala de Espera'),
    ('administracao', 'Administração'),
    ('cozinha', 'Cozinha'),
]


class Migration(migrations.Migration):

    dependencies = [
        ('estoque', '0009_produto_setor_localizacao'),
    ]

    operations = [
        migrations.AlterField(
            model_name='produtoestoque',
            name='setor_localizacao',
            field=models.CharField(
                blank=True,
                choices=_SETOR_CHOICES,
                default='',
                help_text='Para imobilizado: setor clínico onde o bem está.',
                max_length=32,
                verbose_name='Setor (localização)',
            ),
        ),
        migrations.AlterField(
            model_name='requisicaoestoque',
            name='setor_consumo',
            field=models.CharField(
                blank=True,
                choices=_SETOR_CHOICES,
                default='',
                max_length=32,
                verbose_name='Setor de uso / consumo',
            ),
        ),
        migrations.AlterField(
            model_name='requisicaoestoque',
            name='setor_destino',
            field=models.CharField(
                blank=True,
                choices=_SETOR_CHOICES,
                default='',
                max_length=32,
            ),
        ),
        migrations.AlterField(
            model_name='requisicaoestoque',
            name='setor_origem',
            field=models.CharField(
                choices=_SETOR_CHOICES,
                default='farmacia',
                max_length=32,
            ),
        ),
        migrations.AlterField(
            model_name='saldoestoquesetor',
            name='setor',
            field=models.CharField(choices=_SETOR_CHOICES, max_length=32),
        ),
        migrations.AlterField(
            model_name='setorestoqueresponsavel',
            name='setor',
            field=models.CharField(choices=_SETOR_CHOICES, max_length=32),
        ),
    ]
