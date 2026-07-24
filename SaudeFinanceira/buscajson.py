from django.shortcuts import render, get_object_or_404, redirect
from django.http import Http404
from django.core.paginator import Paginator
from django.db.models import Q, Value
from django.db.models.functions import Concat
from django.contrib import messages
import urllib
import re
import json
import requests
import logging


logger = logging.getLogger(__name__)


def cotacao(request):
    return "5.20"


def cnpj(request, cnpj):
    url = "https://www.receitaws.com.br/v1/cnpj/"
    dados = url + str(cnpj)

    try:
        requi_cnpj = requests.get(dados, timeout=10)
        requi_cnpj.raise_for_status()  # Levanta erro para códigos de status HTTP ruins
        dados_cnpj = requi_cnpj.json()
        logger.debug("Resposta CNPJ recebida com sucesso para %s", cnpj)
        return dados_cnpj
    except requests.exceptions.RequestException as e:
        logger.error("Erro na requisição de CNPJ %s: %s", cnpj, e)
        return {
            "erro": "Falha ao consultar CNPJ. Verifique a conexão ou tente novamente."
        }
    except json.JSONDecodeError as e:
        logger.error("Erro ao decodificar JSON da consulta CNPJ %s: %s", cnpj, e)
        return {"erro": "Resposta inválida da API."}