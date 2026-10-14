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

// Latencia con el servidor: cualquier respuesta HTTP cuenta como alcanzado (un servidor sin la
// ruta nueva responde 404 y esa ida y vuelta sigue siendo la latencia real). Solo la red caída o
// el tiempo agotado es "sin respuesta". No lleva token ni cuenta como latido.
const ESPERA_PING_MS = 5000;

export async function ping() {
  const { servidor } = await ajustes();
  const control = new AbortController();
  const plazo = setTimeout(() => control.abort(), ESPERA_PING_MS);
  const inicio = performance.now();
  let resultado;
  try {
    await fetch(servidor + PREFIJO + "/ping", {
      credentials: "omit",
      cache: "no-store",
      signal: control.signal,
    });
    resultado = { ms: Math.round(performance.now() - inicio), ok: true };
  } catch {
    resultado = { ms: null, ok: false };
  } finally {
    clearTimeout(plazo);
  }
  await chrome.storage.local.set({ ping: { ...resultado, en: Date.now() } });
  return resultado;
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
