"""Adaptador del protocolo compatible con OpenAI (chat completions).

Cubre OpenAI, Groq, OpenRouter, DeepSeek, Mistral, Together, etc.: cada uno es una entrada del
catálogo con su ``base_url``. Se usa solo el subconjunto común del protocolo.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
from pydantic import BaseModel

from buscador_vacantes import config as cfg
from buscador_vacantes.asistente.ia.contrato import (
    Parte,
    Resultado,
    error_http,
    espera_retry_after,
    sin_contacto,
)
from buscador_vacantes.asistente.ia.errores import ErrorIA

AVISO_ESQUEMA = (
    "Responde únicamente con un objeto JSON que cumpla este esquema JSON, sin texto adicional "
    "ni bloques de código:\n"
)


def _parte_json(parte: Parte) -> dict[str, Any]:
    if parte.pdf is not None:
        return {
            "type": "file",
            "file": {
                "filename": "hoja_de_vida.pdf",
                "file_data": f"data:application/pdf;base64,{parte.pdf_base64()}",
            },
        }
    return {"type": "text", "text": parte.texto or ""}


def _texto(contenido: dict[str, Any]) -> str:
    try:
        return contenido["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        return ""


class AdaptadorOpenAI:
    def __init__(self, config: cfg.ProveedorIA, http: httpx.AsyncClient) -> None:
        self.config = config
        self.http = http
        # Modelos que rechazaron response_format=json_schema: se va directo al modo json_object
        self._sin_json_schema: set[str] = set()

    @staticmethod
    def _cabeceras(clave: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {clave}"}

    async def validar_clave(self, clave: str) -> bool:
        try:
            respuesta = await self.http.get("models", headers=self._cabeceras(clave))
        except httpx.HTTPError as exc:
            raise ErrorIA(
                f"No se pudo contactar a {self.config.nombre} para validar la clave"
            ) from exc
        if respuesta.status_code == 200:
            return True
        if respuesta.status_code in (401, 403):
            return False
        raise ErrorIA(f"{self.config.nombre} respondió {respuesta.status_code} al validar la clave")

    async def generar(
        self,
        modelo: str,
        clave: str,
        instruccion: str,
        partes: list[Parte],
        esquema: type[BaseModel],
        ajustes: cfg.TareaIA,
    ) -> Resultado:
        esquema_json = esquema.model_json_schema()
        if modelo not in self._sin_json_schema:
            formato = {
                "type": "json_schema",
                "json_schema": {"name": esquema.__name__, "schema": esquema_json},
            }
            respuesta = await self._post(modelo, clave, instruccion, partes, ajustes, formato)
            if respuesta.status_code != 400:
                return self._resultado(respuesta, modelo)
            # Los proveedores compatibles no soportan json_schema por igual: se cae a json_object
            recordar_modo = True
        else:
            recordar_modo = False
        instruccion_json = (
            f"{instruccion}\n\n{AVISO_ESQUEMA}{json.dumps(esquema_json, ensure_ascii=False)}"
        )
        respuesta = await self._post(
            modelo, clave, instruccion_json, partes, ajustes, {"type": "json_object"}
        )
        resultado = self._resultado(respuesta, modelo)
        if recordar_modo:  # el 400 era por json_schema: no se vuelve a intentar con este modelo
            self._sin_json_schema.add(modelo)
        return resultado

    async def _post(
        self,
        modelo: str,
        clave: str,
        instruccion: str,
        partes: list[Parte],
        ajustes: cfg.TareaIA,
        formato: dict[str, Any],
    ) -> httpx.Response:
        cuerpo = {
            "model": modelo,
            "messages": [
                {"role": "system", "content": instruccion},
                {"role": "user", "content": [_parte_json(p) for p in partes]},
            ],
            "temperature": ajustes.temperatura,
            "max_tokens": ajustes.max_tokens,
            "response_format": formato,
        }
        try:
            return await self.http.post(
                "chat/completions", json=cuerpo, headers=self._cabeceras(clave)
            )
        except httpx.HTTPError as exc:
            raise sin_contacto(self.config, exc) from exc

    def _resultado(self, respuesta: httpx.Response, modelo: str) -> Resultado:
        if respuesta.status_code != 200:
            raise error_http(
                respuesta,
                self.config,
                modelo,
                clave_rechazada=respuesta.status_code in (401, 403),
                espera_s=espera_retry_after(respuesta),
            )
        contenido = respuesta.json()
        uso = contenido.get("usage") or {}
        return Resultado(
            _texto(contenido), uso.get("prompt_tokens", 0), uso.get("completion_tokens", 0)
        )
