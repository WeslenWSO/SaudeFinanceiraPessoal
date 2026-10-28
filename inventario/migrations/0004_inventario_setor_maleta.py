from django.db import migrations, models

_SETOR_CHOICES = [
    ('farmacia', 'Farmácia'),
    ('ultrasson', 'Ultrassonografia'),
    ('eletros', 'Eletros'),
    ('outros', 'Outros'),
    ('sedacao', 'Sedação'),
    ('enfermagem', 'Enfermagem'),
    ('carrinho_urgencia', 'Carrinho de Urgência'),
    ('maleta', 'Maleta'),
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
        ('inventario', '0003_inventario_setor'),
    ]

    operations = [
        migrations.AlterField(
            model_name='inventario',
            name='setor',
            field=models.CharField(
                choices=_SETOR_CHOICES,
                default='farmacia',
                help_text='Onde a contagem física será feita (depósito farmácia ou setor clínico).',
                max_length=32,
                verbose_name='Setor inventariado',
            ),
        ),
    ]
