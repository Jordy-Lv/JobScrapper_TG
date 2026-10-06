"""Adaptador del protocolo de Gemini (Google): ``generateContent`` con ``responseSchema``."""

from __future__ import annotations

import json
import re
from typing import Any

import httpx
from pydantic import BaseModel

from buscador_vacantes import config as cfg
from buscador_vacantes.asistente.ia.contrato import Parte, Resultado, error_http, sin_contacto
from buscador_vacantes.asistente.ia.errores import ErrorIA


def esquema_gemini(modelo: type[BaseModel]) -> dict[str, Any]:
    """Convierte el JSON Schema de pydantic al subconjunto OpenAPI que acepta responseSchema."""
    raiz = modelo.model_json_schema()
    definiciones = raiz.get("$defs", {})

    def convertir(nodo: dict[str, Any]) -> dict[str, Any]:
        if "$ref" in nodo:
            return convertir(definiciones[nodo["$ref"].split("/")[-1]])
        if "anyOf" in nodo:
            opciones = [o for o in nodo["anyOf"] if o.get("type") != "null"]
            resultado = convertir(opciones[0])
            if len(opciones) < len(nodo["anyOf"]):
                resultado["nullable"] = True
            return resultado
        salida: dict[str, Any] = {}
        tipo = nodo.get("type")
        if tipo:
            salida["type"] = tipo.upper()
        if "enum" in nodo:
            salida["type"] = "STRING"
            salida["enum"] = [str(v) for v in nodo["enum"]]
        if "description" in nodo:
            salida["description"] = nodo["description"]
        if tipo == "object":
            propiedades = nodo.get("properties", {})
            salida["properties"] = {k: convertir(v) for k, v in propiedades.items()}
            if nodo.get("required"):
                salida["required"] = nodo["required"]
            salida["propertyOrdering"] = list(propiedades)
        if tipo == "array":
            salida["items"] = convertir(nodo.get("items", {"type": "string"}))
        return salida

    return convertir(raiz)


def _espera_429(respuesta: httpx.Response) -> float | None:
    try:
        detalles = respuesta.json()["error"].get("details", [])
    except (ValueError, KeyError, TypeError, AttributeError):
        return None
    for detalle in detalles:
        demora = detalle.get("retryDelay") if isinstance(detalle, dict) else None
        if demora and (m := re.fullmatch(r"(\d+(?:\.\d+)?)s", demora)):
            return float(m.group(1))
    return None


def _es_error_de_clave(respuesta: httpx.Response) -> bool:
    if respuesta.status_code in (401, 403):
        return True
    if respuesta.status_code != 400:
        return False
    try:
        error = respuesta.json()["error"]
    except (ValueError, KeyError, TypeError):
        return False
    texto = json.dumps(error)
    return "API_KEY_INVALID" in texto or "API key not valid" in texto


def _parte_json(parte: Parte) -> dict[str, Any]:
    if parte.pdf is not None:
        return {"inlineData": {"mimeType": "application/pdf", "data": parte.pdf_base64()}}
    return {"text": parte.texto or ""}


def _texto_candidato(datos_respuesta: dict[str, Any]) -> str:
    try:
        partes = datos_respuesta["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError, TypeError):
        return ""
    # Los modelos que razonan pueden devolver partes de pensamiento: no son la respuesta
    return "".join(
        p.get("text", "") for p in partes if isinstance(p, dict) and not p.get("thought")
    )


class AdaptadorGemini:
    def __init__(self, config: cfg.ProveedorIA, http: httpx.AsyncClient) -> None:
        self.config = config
        self.http = http

    async def validar_clave(self, clave: str) -> bool:
        try:
            respuesta = await self.http.get(
                "models", params={"pageSize": 1}, headers={"x-goog-api-key": clave}
            )
        except httpx.HTTPError as exc:
            raise ErrorIA(
                f"No se pudo contactar a {self.config.nombre} para validar la clave"
            ) from exc
        if respuesta.status_code == 200:
            return True
        if respuesta.status_code in (400, 401, 403):
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
        configuracion: dict[str, Any] = {
            "temperature": ajustes.temperatura,
            "maxOutputTokens": ajustes.max_tokens,
            "responseMimeType": "application/json",
            "responseSchema": esquema_gemini(esquema),
        }
        if ajustes.pensamiento:
            configuracion["thinkingConfig"] = {"thinkingLevel": ajustes.pensamiento}
        cuerpo = {
            "systemInstruction": {"parts": [{"text": instruccion}]},
            "contents": [{"role": "user", "parts": [_parte_json(p) for p in partes]}],
            "generationConfig": configuracion,
        }
        try:
            respuesta = await self.http.post(
                f"models/{modelo}:generateContent", json=cuerpo, headers={"x-goog-api-key": clave}
            )
        except httpx.HTTPError as exc:
            raise sin_contacto(self.config, exc) from exc
        if respuesta.status_code != 200:
            raise error_http(
                respuesta,
                self.config,
                modelo,
                clave_rechazada=_es_error_de_clave(respuesta),
                espera_s=_espera_429(respuesta) if respuesta.status_code == 429 else None,
            )
        contenido = respuesta.json()
        uso = contenido.get("usageMetadata", {})
        return Resultado(
            _texto_candidato(contenido),
            uso.get("promptTokenCount", 0),
            uso.get("candidatesTokenCount", 0),
        )
