// Datos fijos de la extensión: no los cambia el servidor.

export const SERVIDOR_DEFECTO = "https://postulador.tailf6cdf1.ts.net";

// Dominios en los que el motor puede operar, por plataforma
export const DOMINIOS = {
  computrabajo: ["computrabajo.com"],
  magneto: ["magneto365.com"],
  elempleo: ["elempleo.com"],
  getonboard: ["getonbrd.com"],
  linkedin: ["linkedin.com"],
  spe: ["buscadordeempleo.gov.co"],
};

export const NOMBRES = {
  computrabajo: "Computrabajo",
  magneto: "Magneto",
  elempleo: "elempleo",
  getonboard: "GetOnBoard",
  linkedin: "LinkedIn",
  spe: "Servicio Público de Empleo",
};

// Plataformas con código propio en adaptadores/; las demás funcionan solo con los datos
// (selectores y flujo) que entrega el servidor, sin publicar otra versión de la extensión.
export const ADAPTADORES = ["computrabajo", "magneto"];

// Permiso de cada plataforma. Las que no vienen de fábrica son permisos opcionales que el
// usuario activa desde el popup cuando el servidor habilita esa plataforma.
export function origenes(plataforma) {
  return (DOMINIOS[plataforma] || []).map((d) => `https://*.${d}/*`);
}

export async function tienePermiso(plataforma) {
  const lista = origenes(plataforma);
  return lista.length > 0 && chrome.permissions.contains({ origins: lista });
}

// Páginas que el motor nunca toca, aunque los selectores lo pidan: contraseña, correo de
// acceso, privacidad, notificaciones y borrado de la cuenta.
export const PROHIBIDAS = [
  /contrase(n|ñ)a/i,
  /password/i,
  /cambiar-?correo|change-?email/i,
  /privacidad|privacy/i,
  /notificaci(o|ó)n|notification/i,
  /eliminar-?cuenta|borrar-?cuenta|delete-?account/i,
  /configuracion\/cuenta|account-?settings/i,
];

export function plataformaDeUrl(url) {
  let host;
  try {
    host = new URL(url).hostname;
  } catch {
    return null;
  }
  for (const [plataforma, dominios] of Object.entries(DOMINIOS)) {
    if (dominios.some((d) => host === d || host.endsWith("." + d))) return plataforma;
  }
  return null;
}

// El motor solo opera en los dominios del portal y fuera de las páginas prohibidas
export function paginaPermitida(url, plataforma) {
  if (plataformaDeUrl(url) !== plataforma) return false;
  const ruta = new URL(url).pathname;
  return !PROHIBIDAS.some((patron) => patron.test(ruta));
}
