// Datos fijos de la extensión: no los cambia el servidor.

export const SERVIDOR_DEFECTO = "https://postulador.tailf6cdf1.ts.net";

// Dominios en los que el motor puede operar, por plataforma
export const DOMINIOS = {
  computrabajo: ["computrabajo.com"],
  magneto: ["magneto365.com"],
};

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
