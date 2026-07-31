"""Cliente HTTP MedCloud RIS e HIS."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

import requests

from .config import MedcloudCredentials

logger = logging.getLogger(__name__)

STATUS_AGENDA_CONCLUIDA = frozenset({
    'CONCLUDED',
    'Concluído',
    'Concluido',
    'Finalizado',
    'WAITING_FOR_BILLING',
    'WAITING_FOR_CHECKOUT',
})


class MedcloudAPIError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class MedcloudRISClient:
    def __init__(self, creds: MedcloudCredentials, timeout: int = 60):
        self.creds = creds
        self.timeout = timeout
        self._token: str | None = None
        self._cache: dict[str, Any] = {}

    def _headers(self) -> dict[str, str]:
        token = self.authenticate()
        return {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        }

    def authenticate(self) -> str:
        if self._token:
            return self._token
        url = f'{self.creds.ris_base_url}/authenticate'
        payload = {
            'username': self.creds.ris_username,
            'password': self.creds.ris_password,
            'clinicIdToAccess': self.creds.ris_clinic_id,
        }
        resp = requests.post(url, json=payload, timeout=self.timeout)
        if resp.status_code != 200:
            raise MedcloudAPIError(
                f'Falha na autenticação MedCloud RIS ({resp.status_code}): {resp.text[:300]}',
                resp.status_code,
            )
        data = resp.json()
        token = data.get('token') if isinstance(data, dict) else None
        if not token:
            raise MedcloudAPIError('Resposta de autenticação sem token JWT.')
        self._token = token
        return token

    def _get_json(self, path: str, params: dict | None = None) -> Any:
        url = f'{self.creds.ris_base_url}{path}'
        resp = requests.get(url, headers=self._headers(), params=params or {}, timeout=self.timeout)
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            raise MedcloudAPIError(
                f'GET {path} falhou ({resp.status_code}): {resp.text[:300]}',
                resp.status_code,
            )
        if not resp.content:
            return None
        return resp.json()

    def get_schedule(self, schedule_id: int) -> dict | None:
        data = self._get_json(f'/schedule/{schedule_id}')
        if not data:
            return None
        if isinstance(data, dict) and 'schedule' in data:
            sched = dict(data['schedule'])
            sched['id'] = schedule_id
            return sched
        if isinstance(data, dict):
            data.setdefault('id', schedule_id)
            return data
        return None

    def list_schedules(
        self,
        data_inicio: date,
        data_fim: date,
        *,
        status: str | None = 'CONCLUDED',
        partner_id: int | None = None,
    ) -> list[dict]:
        """Lista agendas no intervalo. Depende do endpoint configurado (não documentado publicamente)."""
        params: dict[str, Any] = {
            'startDate': data_inicio.isoformat(),
            'endDate': data_fim.isoformat(),
        }
        if status is not None:
            params['status'] = status
        if partner_id is not None and partner_id > 0:
            params['partnerId'] = partner_id

        paths = [self.creds.ris_lista_agendas_path]
        if paths[0] != '/schedules':
            paths.append('/schedules')
        if paths[0] != '/schedule':
            paths.append('/schedule')

        last_error: Exception | None = None
        for path in paths:
            try:
                data = self._get_json(path, params=params)
                items = _extrair_lista_agendas(data)
                if items is not None:
                    return [_normalizar_agenda(item) for item in items if item]
            except MedcloudAPIError as exc:
                last_error = exc
                logger.debug('Listagem MedCloud em %s: %s', path, exc)
                continue
        if last_error:
            raise last_error
        return []

    def list_schedules_periodo(
        self,
        data_inicio: date,
        data_fim: date,
        *,
        partner_id: int | None = None,
    ) -> list[dict]:
        """
        Lista agendas do período em todos os status relevantes
        (concluídos, cancelados, desistência, deletados, etc.).
        """
        vistos: dict[int, dict] = {}

        def _merge(items: list[dict]) -> None:
            for item in items:
                if not item:
                    continue
                sid = item.get('id') or item.get('scheduleId')
                if sid is None:
                    vistos[id(item)] = item
                    continue
                try:
                    vistos[int(sid)] = item
                except (TypeError, ValueError):
                    vistos[id(item)] = item

        try:
            _merge(self.list_schedules(data_inicio, data_fim, status=None, partner_id=partner_id))
        except MedcloudAPIError:
            pass

        if vistos:
            return list(vistos.values())

        for status in (
            'CONCLUDED',
            'WAITING_FOR_BILLING',
            'WAITING_FOR_CHECKOUT',
            'CANCELED',
            'ONLINE_CANCELED',
            'GIVE_UP',
            'DELETED',
            'IN_PROGRESS',
            'CONFIRMED',
        ):
            try:
                _merge(self.list_schedules(
                    data_inicio, data_fim, status=status, partner_id=partner_id,
                ))
            except MedcloudAPIError:
                continue

        return list(vistos.values())

    def get_patient(self, patient_id: int) -> dict | None:
        key = f'patient:{patient_id}'
        if key in self._cache:
            return self._cache[key]
        data = self._get_json(f'/patient/{patient_id}')
        patient = None
        if isinstance(data, dict):
            patient = data.get('patient') or data
        self._cache[key] = patient
        return patient

    def get_procedure(self, procedure_id: int) -> dict | None:
        key = f'procedure:{procedure_id}'
        if key in self._cache:
            return self._cache[key]
        data = self._get_json(f'/medical-procedure/{procedure_id}')
        proc = None
        if isinstance(data, dict):
            proc = data.get('medicalProcedure') or data.get('procedure') or data
        self._cache[key] = proc
        return proc

    def get_partner(self, partner_id: int) -> dict | None:
        key = f'partner:{partner_id}'
        if key in self._cache:
            return self._cache[key]
        data = self._get_json(f'/partner/{partner_id}')
        partner = None
        if isinstance(data, dict):
            partner = data.get('partner') or data
        self._cache[key] = partner
        return partner


class MedcloudHISClient:
    def __init__(self, creds: MedcloudCredentials, timeout: int = 60):
        self.creds = creds
        self.timeout = timeout

    def gerar_links_exame(self, accession_number: str) -> dict | None:
        if not self.creds.his_api_key:
            raise MedcloudAPIError('API Key HIS não configurada.')
        url = self.creds.his_base_url
        if not url.endswith('/his'):
            url = f'{url.rstrip("/")}/his'
        resp = requests.post(
            url,
            json={'accessionNumber': accession_number},
            headers={
                'Content-Type': 'application/json',
                'X-API-key': self.creds.his_api_key,
            },
            timeout=self.timeout,
        )
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            raise MedcloudAPIError(
                f'HIS accession {accession_number} ({resp.status_code}): {resp.text[:300]}',
                resp.status_code,
            )
        return resp.json() if resp.content else None


def _extrair_lista_agendas(data: Any) -> list | None:
    if data is None:
        return []
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return None
    for key in ('schedules', 'schedule', 'data', 'items', 'results', 'content'):
        val = data.get(key)
        if isinstance(val, list):
            return val
        if isinstance(val, dict):
            nested = _extrair_lista_agendas(val)
            if nested is not None:
                return nested
    return None


def _normalizar_agenda(item: Any) -> dict:
    if not isinstance(item, dict):
        return {}
    if 'schedule' in item and isinstance(item['schedule'], dict):
        sched = dict(item['schedule'])
        if 'id' not in sched and 'scheduleId' in item:
            sched['id'] = item['scheduleId']
        if 'id' not in sched and 'id' in item:
            sched['id'] = item['id']
        return sched
    return dict(item)


def agenda_esta_concluida(schedule: dict) -> bool:
    status = (schedule.get('status') or '').strip()
    if status in STATUS_AGENDA_CONCLUIDA:
        return True
    return status.upper() in STATUS_AGENDA_CONCLUIDA
