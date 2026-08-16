"""Silencia logs ruidosos do gRPC/Google (ALTS/absl) ao usar Gemini fora do GCP."""
from __future__ import annotations

import os


def silenciar_logs_grpc_google() -> None:
    """Deve rodar antes de importar google.generativeai ou grpc."""
    # Atribuição direta (não setdefault) para garantir mesmo com env pré-existente.
    os.environ['GRPC_VERBOSITY'] = 'NONE'
    os.environ['GRPC_TRACE'] = ''
    os.environ['GLOG_minloglevel'] = '3'
    os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
    os.environ['ABSL_MIN_LOG_LEVEL'] = '3'
    os.environ['GRPC_ENABLE_FORK_SUPPORT'] = '0'


silenciar_logs_grpc_google()
