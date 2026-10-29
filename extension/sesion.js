// Duración de la sesión de cada portal, a partir de los metadatos de sus cookies.
// Necesita el permiso opcional `cookies`. Solo se leen nombre, tipo, vencimiento y HttpOnly:
// el valor de una cookie nunca se copia, se guarda, se registra ni se envía.

import { DOMINIOS } from "./portales.js";

export const PERMISO_COOKIES = { permissions: ["cookies"] };

export async function tienePermisoCookies() {
  try {
    return await chrome.permissions.contains(PERMISO_COOKIES);
  } catch {
    return false;
  }
}

// Metadatos de todas las cookies del portal (la lista completa sirve para descubrir cuáles son
// las de autenticación). `vence` son milisegundos desde 1970, o null si la cookie es de sesión.
export async function leerCookies(plataforma) {
  const vistas = new Map();
  for (const dominio of DOMINIOS[plataforma] || []) {
    for (const c of await chrome.cookies.getAll({ domain: dominio })) {
      vistas.set(`${c.domain}|${c.path}|${c.name}`, {
        nombre: c.name,
        sesion: Boolean(c.session),
        vence: c.session || c.expirationDate == null ? null : Math.round(c.expirationDate * 1000),
        httpOnly: Boolean(c.httpOnly),
      });
    }
  }
  return [...vistas.values()].sort((a, b) => a.nombre.localeCompare(b.nombre));
}

// Clasifica la sesión con las cookies de autenticación nombradas en `sesion.cookies` del
// selector: `se_pierde` (alguna es de sesión), `dura_hasta` (todas son persistentes; vence la
// primera en vencer) o `sin_datos` (ninguna conocida o presente)
export function clasificarSesion(cookies, nombres = []) {
  const conocidas = cookies.filter((c) => nombres.includes(c.nombre));
  if (!conocidas.length) return { clasificacion: "sin_datos", hasta: null };
  if (conocidas.some((c) => c.sesion || c.vence == null)) return { clasificacion: "se_pierde", hasta: null };
  return { clasificacion: "dura_hasta", hasta: Math.min(...conocidas.map((c) => c.vence)) };
}

// Sin el permiso no se lee nada y devuelve null
export async function diagnosticarSesion(plataforma, nombres = []) {
  if (!(await tienePermisoCookies())) return null;
  const cookies = await leerCookies(plataforma);
  return { ...clasificarSesion(cookies, nombres), cookies, medido: Date.now() };
}

// Texto de la clasificación para el popup
export function textoDuracion(duracion) {
  if (!duracion) return null;
  if (duracion.clasificacion === "se_pierde") return "Se pierde al cerrar el navegador";
  if (duracion.clasificacion === "dura_hasta") {
    const hasta = new Date(duracion.hasta).toLocaleString("es-CO", { dateStyle: "medium", timeStyle: "short" });
    return `Dura hasta ${hasta}`;
  }
  return "Sin datos";
}
