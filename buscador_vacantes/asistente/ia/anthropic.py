"""Adaptador del protocolo de Anthropic (Messages API) con herramienta forzada para el JSON."""

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

VERSION_API = "2023-06-01"
HERRAMIENTA = "entregar_resultado"


def _parte_json(parte: Parte) -> dict[str, Any]:
    if parte.pdf is not None:
        return {
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": "application/pdf",
                "data": parte.pdf_base64(),
            },
        }
    return {"type": "text", "text": parte.texto or ""}


def _texto(contenido: dict[str, Any]) -> str:
    """El JSON viaja como ``input`` de la herramienta forzada."""
    bloques = contenido.get("content")
    if not isinstance(bloques, list):
        return ""
    for bloque in bloques:
        if isinstance(bloque, dict) and bloque.get("type") == "tool_use":
            return json.dumps(bloque.get("input", {}), ensure_ascii=False)
    return ""


class AdaptadorAnthropic:
    def __init__(self, config: cfg.ProveedorIA, http: httpx.AsyncClient) -> None:
        self.config = config
        self.http = http

    @staticmethod
    def _cabeceras(clave: str) -> dict[str, str]:
        return {"x-api-key": clave, "anthropic-version": VERSION_API}

    async def validar_clave(self, clave: str) -> bool:
        try:
            respuesta = await self.http.get(
                "models", params={"limit": 1}, headers=self._cabeceras(clave)
            )
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
        cuerpo = {
            "model": modelo,
            "max_tokens": ajustes.max_tokens,
            "temperature": ajustes.temperatura,
            "system": instruccion,
            "messages": [{"role": "user", "content": [_parte_json(p) for p in partes]}],
            "tools": [
                {
                    "name": HERRAMIENTA,
                    "description": "Entrega el resultado final con la estructura pedida.",
                    "input_schema": esquema.model_json_schema(),
                }
            ],
            "tool_choice": {"type": "tool", "name": HERRAMIENTA},
        }
        try:
            respuesta = await self.http.post(
                "messages", json=cuerpo, headers=self._cabeceras(clave)
            )
        except httpx.HTTPError as exc:
            raise sin_contacto(self.config, exc) from exc
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
        return Resultado(_texto(contenido), uso.get("input_tokens", 0), uso.get("output_tokens", 0))
