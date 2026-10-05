// Cliente de la API v1 del servidor. Lo usan el service worker, el popup y las opciones.

import { SERVIDOR_DEFECTO } from "./portales.js";

const PREFIJO = "/api/v1";

export class ErrorApi extends Error {
  constructor(estado, detalle) {
    super(`HTTP ${estado}: ${detalle}`);
    this.estado = estado;
  }
}

export async function ajustes() {
  return chrome.storage.local.get({
    servidor: SERVIDOR_DEFECTO,
    token: null,
    pausado: false,
    nombre: null,
  });
}

export function version() {
  return chrome.runtime.getManifest().version;
}

export async function llamar(metodo, ruta, cuerpo, { sinToken = false, binario = false } = {}) {
  const { servidor, token } = await ajustes();
  const cabeceras = {};
  if (!sinToken) {
    if (!token) throw new ErrorApi(401, "navegador sin vincular");
    cabeceras.Authorization = `Bearer ${token}`;
  }
  if (cuerpo !== undefined) cabeceras["Content-Type"] = "application/json";
  const url = ruta.startsWith(PREFIJO) ? servidor + ruta : servidor + PREFIJO + ruta;
  let respuesta;
  try {
    respuesta = await fetch(url, {
      method: metodo,
      headers: cabeceras,
      body: cuerpo === undefined ? undefined : JSON.stringify(cuerpo),
      credentials: "omit",
      cache: "no-store",
    });
  } catch (error) {
    throw new ErrorApi(0, "servidor fuera de línea");
  }
  if (respuesta.status === 401 && !sinToken) {
    // Token revocado desde el bot (/navegadores): el navegador queda desvinculado
    await chrome.storage.local.set({ token: null });
  }
  if (!respuesta.ok) {
    let detalle = "";
    try {
      detalle = (await respuesta.json()).detail || "";
    } catch {
      // sin cuerpo JSON
    }
    throw new ErrorApi(respuesta.status, detalle);
  }
  return binario ? respuesta.arrayBuffer() : respuesta.json();
}

export async function vincular(codigo) {
  const limpio = String(codigo).toUpperCase().replace(/[^A-Z0-9]/g, "");
  const nombre = navegadorNombre();
  const { token } = await llamar(
    "POST",
    "/vincular",
    { codigo: limpio, nombre, version: version() },
    { sinToken: true },
  );
  await chrome.storage.local.set({ token, nombre, vinculado_en: Date.now() });
  return true;
}

function navegadorNombre() {
  const ua = navigator.userAgent;
  const nav = /Edg\//.test(ua) ? "Edge" : /Brave/.test(ua) ? "Brave" : "Chrome";
  const so = /Windows/.test(ua) ? "Windows" : /Mac OS/.test(ua) ? "Mac" : /Linux/.test(ua) ? "Linux" : "";
  return so ? `${nav} en ${so}` : nav;
}
