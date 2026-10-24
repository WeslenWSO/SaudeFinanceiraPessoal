"""Setores de estoque (farmácia central + unidades clínicas)."""

from django.db import models


class SetorEstoque(models.TextChoices):
    FARMACIA = 'farmacia', 'Farmácia'
    ULTRASSON = 'ultrasson', 'Ultrassonografia'
    ELETROS = 'eletros', 'Eletros'
    OUTROS = 'outros', 'Outros'
    SEDACAO = 'sedacao', 'Sedação'
    ENFERMAGEM = 'enfermagem', 'Enfermagem'
    RAIO_X = 'raio_x', 'Raio-X'
    MAMOGRAFIA = 'mamografia', 'Mamografia'
    IMOBILIZADO = 'imobilizado', 'Imobilizado'


SETOR_TRANSFERENCIA_DESTINOS = tuple(
    (c.value, c.label)
    for c in SetorEstoque
    if c not in (SetorEstoque.FARMACIA, SetorEstoque.IMOBILIZADO)
)

# Onde o bem imobilizado está instalado / em uso (não é o depósito «Imobilizado»).
SETOR_LOCALIZACAO_IMOBILIZADO = SETOR_TRANSFERENCIA_DESTINOS
