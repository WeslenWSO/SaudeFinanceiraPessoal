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
    RECEPCAO = 'recepcao', 'Recepção'
    SALA_ESPERA = 'sala_espera', 'Sala de Espera'
    ADMINISTRACAO = 'administracao', 'Administração'
    COZINHA = 'cozinha', 'Cozinha'


# Setores administrativos / apoio — só localização de imobilizado (não entram em requisições).
_SETORES_APENAS_LOCALIZACAO_IMOBILIZADO = (
    SetorEstoque.RECEPCAO,
    SetorEstoque.SALA_ESPERA,
    SetorEstoque.ADMINISTRACAO,
    SetorEstoque.COZINHA,
)

SETOR_TRANSFERENCIA_DESTINOS = tuple(
    (c.value, c.label)
    for c in SetorEstoque
    if c
    not in (
        SetorEstoque.FARMACIA,
        SetorEstoque.IMOBILIZADO,
        *_SETORES_APENAS_LOCALIZACAO_IMOBILIZADO,
    )
)

# Onde o bem imobilizado está instalado / em uso (não é o depósito «Imobilizado»).
SETOR_LOCALIZACAO_IMOBILIZADO = SETOR_TRANSFERENCIA_DESTINOS + tuple(
    (c.value, c.label) for c in _SETORES_APENAS_LOCALIZACAO_IMOBILIZADO
)

# Lista cega / contagem — depósito central + setores clínicos (requisições).
SETOR_LISTA_CEGA_FARMACIA = (
    (SetorEstoque.FARMACIA.value, SetorEstoque.FARMACIA.label),
    *SETOR_TRANSFERENCIA_DESTINOS,
)
