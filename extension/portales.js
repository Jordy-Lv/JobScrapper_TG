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
  spe: "Servicio de Empleo",
};

// Página oficial de ingreso de cada portal: el usuario inicia sesión ahí, nunca en la extensión
export const INGRESO = {
  computrabajo: "https://candidato.co.computrabajo.com/acceso/",
  magneto: "https://web.magneto365.com/sign-in",
  elempleo: "https://www.elempleo.com/co/",
  getonboard: "https://www.getonbrd.com/",
  linkedin: "https://www.linkedin.com/login",
  spe: "https://www.buscadordeempleo.gov.co/",
};

// Página principal de cada portal (botón "abrir" del popup)
export const INICIO = {
  computrabajo: "https://co.computrabajo.com/",
  magneto: "https://www.magneto365.com/co",
  elempleo: "https://www.elempleo.com/co/",
  getonboard: "https://www.getonbrd.com/",
  linkedin: "https://www.linkedin.com/jobs/",
  spe: "https://www.buscadordeempleo.gov.co/",
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

// El motor solo opera en los dominios del portal y fuera de las páginas prohibidas. En la
// plataforma `externa`, `ambito` es el destino del trabajo (ver motivoExterno).
export function paginaPermitida(url, plataforma, ambito = null) {
  if (plataforma === "externa") return motivoExterno(url, ambito) === null;
  if (plataformaDeUrl(url) !== plataforma) return false;
  const ruta = new URL(url).pathname;
  return !PROHIBIDAS.some((patron) => patron.test(ruta));
}

// --- plataforma «externa»: la página de la empresa a la que lleva una vacante de LinkedIn ------
// Cualquier https, con el permiso opcional `https://*/*` que el usuario concede desde el popup.

export const ORIGEN_EXTERNO = "https://*/*";

export async function tienePermisoExterno() {
  return chrome.permissions.contains({ origins: [ORIGEN_EXTERNO] });
}

// Además de las prohibidas de siempre: ingreso, registro, OAuth y pagos
export const PROHIBIDAS_EXTERNA = [
  ...PROHIBIDAS,
  /(^|[/_.-])(log[-_]?in|sign[-_]?in|sign[-_]?up|register|oauth2?|authorize|checkout|payments?)([/_.-]|$)/i,
];

// Proveedores de identidad: llegar a ellos es una barrera «oauth», no un salto cualquiera
const OAUTH = /^(accounts\.google\.com|login\.microsoftonline\.com|login\.live\.com|appleid\.apple\.com)(\/|$)|\/(oauth2?|authorize)(\/|$)/i;

const SEGUNDO_NIVEL = /^(com|co|org|net|gov|gob|edu|ac|nom|mil)$/;

// Dominio registrable aproximado: empresa.com, empresa.com.co, empresa.co.uk
export function dominioBase(host) {
  const partes = host.toLowerCase().split(".");
  const n = partes.length > 2 && partes.at(-1).length === 2 && SEGUNDO_NIVEL.test(partes.at(-2)) ? 3 : 2;
  return partes.slice(-n).join(".");
}

function delPatron(host, patron) {
  const p = String(patron).toLowerCase();
  return host === p || host.endsWith("." + p);
}

// Por qué el motor no puede operar en `url` dentro del destino `ambito` ({destino,
// familias_hosts, hosts_prohibidos}), o null si puede: `oauth`, `pagina_prohibida` o
// `salto_de_dominio` (el host no es el del destino, ni de su mismo dominio, ni de una familia
// de ATS conocida, como el sitio propio que incrusta Greenhouse).
export function motivoExterno(url, ambito) {
  let u;
  try {
    u = new URL(url);
  } catch {
    return "pagina_prohibida";
  }
  if (u.protocol !== "https:") return "pagina_prohibida";
  const host = u.hostname.toLowerCase();
  const hostRuta = host + u.pathname.toLowerCase();
  if (OAUTH.test(hostRuta)) return "oauth";
  const a = ambito || {};
  for (const prohibido of a.hosts_prohibidos || []) {
    const p = String(prohibido).toLowerCase();
    const enHost = p.includes("/") ? hostRuta === p || hostRuta.startsWith(p + "/") : delPatron(host, p);
    if (enHost) return "pagina_prohibida";
  }
  if (PROHIBIDAS_EXTERNA.some((patron) => patron.test(u.pathname))) return "pagina_prohibida";
  let destino;
  try {
    destino = new URL(a.destino).hostname.toLowerCase();
  } catch {
    return "salto_de_dominio";
  }
  if (host === destino || dominioBase(host) === dominioBase(destino)) return null;
  if ((a.familias_hosts || []).some((p) => delPatron(host, p))) return null;
  return "salto_de_dominio";
}
