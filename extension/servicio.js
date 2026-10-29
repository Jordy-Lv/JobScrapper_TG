// Service worker: latido con el servidor, vinculación y ejecución de la cola del usuario.
// Coordina el flujo entre páginas; cada paso lo ejecuta motor.js dentro de la pestaña.

import { ajustes, llamar, version, vincular, ErrorApi } from "./api.js";
import { ADAPTADORES, INGRESO, motivoExterno, paginaPermitida, plataformaDeUrl, tienePermiso,
  tienePermisoExterno } from "./portales.js";
import { diagnosticarSesion } from "./sesion.js";

const ALARMA = "latido";
const REVISION_MAX_MS = 6 * 60 * 60 * 1000; // estado de los portales: se revisa cada 6 h
const REVISION_SIN_CORREO_MS = 10 * 60 * 1000; // con sesión y sin correo: se reintenta pronto
const CARGA_MS = 45000;
const PREDETERMINADOS = {
  sondeo_captcha_ms: 10000, verificacion_max_ms: 2 * 60 * 60 * 1000,
  sondeo_sesion_ms: 2000, espera_sesion_max_ms: 10 * 60 * 1000, // 10 min para iniciar sesión
  llenado_max_ms: 30000, // tope del llenado de un formulario dentro de la pestaña
  resultado_ms: 25000, // espera del resultado tras avanzar o enviar en el bucle genérico
};
// Topes del bucle genérico si el trabajo no los trae (servidor sin motor_generico)
const TOPES_GENERICO = { max_pantallas: 12, max_pantallas_una_pregunta: 40, max_minutos: 10 };
const REPETICIONES_MAX = 3; // la misma pantalla sin cambios

let ocupado = false;
let enCurso = null; // latido en curso: quien llama mientras tanto recibe el mismo

// --- arranque y alarma ----------------------------------------------------------------------

// Si el service worker se reinició, ninguna vigilancia sigue viva: sin esto la bandera quedaba
// puesta para siempre y la tarjeta se quedaba en "Iniciando sesión…"
chrome.storage.local.set({ vigilando: {} }).catch(() => {});
chrome.runtime.onInstalled.addListener(() => programar());
chrome.runtime.onStartup.addListener(() => programar());
chrome.alarms.onAlarm.addListener((alarma) => {
  if (alarma.name === ALARMA) latido();
});

async function programar(segundos = 30) {
  await chrome.alarms.create(ALARMA, { periodInMinutes: Math.max(segundos, 30) / 60 });
  latido();
}

async function guardarEstado(cambios) {
  const { estado = {} } = await chrome.storage.local.get("estado");
  await chrome.storage.local.set({ estado: { ...estado, ...cambios } });
}

async function opciones() {
  const { pruebas = {} } = await chrome.storage.local.get("pruebas");
  return { ...PREDETERMINADOS, ...pruebas };
}

// --- latido -------------------------------------------------------------------------------

// Lo llaman la alarma, el arranque y el oyente de pestañas sin esperar el resultado: un error
// queda como latido fallido (null), igual que sin token, y no como rechazo sin capturar
function latido(opciones = {}) {
  if (!enCurso) {
    enCurso = latidoUnico(opciones).catch(() => null).finally(() => (enCurso = null));
  }
  return enCurso;
}

async function latidoUnico({ forzarRevision = false } = {}) {
  const { token, pausado } = await ajustes();
  if (!token) return null;
  ocupado = true;
  try {
    if (!pausado) await retomarBucle();
    let portales = await estadoPortales(forzarRevision);
    let respuesta = await enviarLatido(portales);
    if (!respuesta) return null;
    // Plataforma recién habilitada en el servidor: se revisa ya, sin esperar al próximo latido
    const nuevas = [];
    for (const p of Object.keys(respuesta.selectores || {})) {
      if (!portales[p] && (await tienePermiso(p))) nuevas.push(p);
    }
    if (nuevas.length) {
      portales = await estadoPortales(false);
      respuesta = (await enviarLatido(portales)) || respuesta;
    }
    if (respuesta.trabajo && !pausado && !respuesta.actualizar) {
      // Antes de cada trabajo se relee la sesión y el correo de la cuenta del portal
      const plataforma = respuesta.trabajo.plataforma;
      portales = await estadoPortales(false, plataforma);
      respuesta = await enviarLatido(portales);
      const trabajo = respuesta && respuesta.trabajo;
      if (trabajo && respuesta.cuentas[trabajo.plataforma]) {
        await ejecutar(trabajo);
      }
    }
    return respuesta;
  } catch (error) {
    await guardarEstado({ en_linea: false, error: String(error.message || error) });
    return null;
  } finally {
    ocupado = false;
  }
}

async function enviarLatido(portales) {
  const { pausado } = await ajustes();
  const cuerpo = { version: version(), portales: {}, pausado: Boolean(pausado) };
  for (const [plataforma, p] of Object.entries(portales)) {
    cuerpo.portales[plataforma] = { estado: p.estado, correo: p.correo || null,
      pagina_correo: p.pagina_correo || null, motivo: p.motivo || null };
  }
  // Páginas de las empresas (vacantes externas de LinkedIn): no tienen sesión ni cuenta, solo
  // el permiso. El servidor lo lee para decidir si las abre (Nucleo.permiso_externo).
  if (await tienePermisoExterno()) cuerpo.portales.externa = { estado: "listo", correo: null };
  try {
    const r = await llamar("POST", "/latido", cuerpo);
    await chrome.storage.local.set({
      selectores_version: r.selectores || {}, enlaces: r.enlaces || {},
      motor_generico_version: r.motor_generico || null,
      familias_ats_version: r.familias_ats || null,
    });
    await guardarEstado({
      en_linea: true, ultimo_latido: Date.now(), actualizar: r.actualizar,
      version_minima: r.version_minima, cuentas: r.cuentas, error: null,
    });
    if (r.latido_s && r.latido_s !== 30) await chrome.alarms.create(ALARMA, { periodInMinutes: r.latido_s / 60 });
    return r;
  } catch (error) {
    await guardarEstado({ en_linea: false, error: error instanceof ErrorApi ? error.message : String(error) });
    return null;
  }
}

// --- selectores (datos versionados del servidor) -------------------------------------------

async function selectores(plataforma) {
  const { selectores_version = {}, selectores_cache = {} } =
    await chrome.storage.local.get(["selectores_version", "selectores_cache"]);
  const guardado = selectores_cache[plataforma];
  if (guardado && guardado.version === selectores_version[plataforma]) return guardado.selectores;
  const r = await llamar("GET", `/selectores/${plataforma}`);
  selectores_cache[plataforma] = r;
  await chrome.storage.local.set({ selectores_cache });
  return r.selectores;
}

// Reglas del motor genérico (datos versionados): se piden cuando cambia la versión del latido
async function reglasMotor() {
  const { motor_generico_version = null, motor_generico_cache = null } =
    await chrome.storage.local.get(["motor_generico_version", "motor_generico_cache"]);
  if (motor_generico_cache && motor_generico_cache.version === motor_generico_version) {
    return motor_generico_cache.reglas;
  }
  const r = await llamar("GET", "/motor_generico");
  await chrome.storage.local.set({ motor_generico_cache: r });
  return r.reglas;
}

// Datos de las familias de ATS (CV, botón de enviar, señal de éxito), por la versión del latido.
// Un servidor sin ellos deja el motor con sus reglas genéricas.
async function familiasAts() {
  const { familias_ats_version = null, familias_ats_cache = null } =
    await chrome.storage.local.get(["familias_ats_version", "familias_ats_cache"]);
  if (familias_ats_cache && familias_ats_cache.version === familias_ats_version) {
    return familias_ats_cache.familias;
  }
  try {
    const r = await llamar("GET", "/familias_ats");
    await chrome.storage.local.set({ familias_ats_cache: r });
    return r.familias || {};
  } catch (error) {
    return {};
  }
}

// --- estado de los portales ----------------------------------------------------------------

async function estadoPortales(forzar, soloPlataforma = null) {
  const { portales = {} } = await chrome.storage.local.get("portales");
  // Solo las plataformas que el servidor habilitó (tienen selectores) y con permiso del usuario
  const { selectores_version = {} } = await chrome.storage.local.get("selectores_version");
  for (const plataforma of Object.keys(portales)) {
    if (!(plataforma in selectores_version)) delete portales[plataforma];
  }
  for (const plataforma of Object.keys(selectores_version)) {
    if (!(await tienePermiso(plataforma))) {
      delete portales[plataforma];
      continue;
    }
    const previo = portales[plataforma];
    const edad = previo ? Date.now() - previo.revisado : Infinity;
    const vencido = edad > REVISION_MAX_MS
      || (previo.estado !== "sin_sesion" && !previo.correo && edad > REVISION_SIN_CORREO_MS);
    if (soloPlataforma ? plataforma === soloPlataforma : forzar || vencido) {
      try {
        portales[plataforma] = { ...(await revisarPortal(plataforma)), revisado: Date.now() };
        await anotarDuracion(portales[plataforma], plataforma);
      } catch (error) {
        if (!previo) portales[plataforma] = { estado: "sin_sesion", revisado: Date.now() };
      }
    }
  }
  await chrome.storage.local.set({ portales });
  return portales;
}

// Duración de la sesión según las cookies del portal (solo metadatos, con el permiso opcional
// `cookies`): se guarda junto al estado del portal y no viaja al servidor (enviarLatido solo
// toma estado, correo, página y motivo). Sin sesión o sin permiso no hay duración.
async function anotarDuracion(portal, plataforma) {
  delete portal.duracion;
  if (portal.estado === "sin_sesion") return;
  try {
    const sel = await selectores(plataforma);
    const duracion = await diagnosticarSesion(plataforma, (sel.sesion || {}).cookies || []);
    if (duracion) portal.duracion = duracion;
  } catch (error) {
    // El diagnóstico es informativo: un fallo no cambia el estado del portal
  }
}

// Vuelve a medir la duración de un portal sin visitarlo (el popup lo pide al conceder el permiso)
async function medirDuracion(plataforma) {
  const { portales = {} } = await chrome.storage.local.get("portales");
  if (!portales[plataforma]) return false;
  await anotarDuracion(portales[plataforma], plataforma);
  await chrome.storage.local.set({ portales });
  return true;
}

// Revisa el portal en una ventana minimizada: primero la sesión en la página principal (donde
// el botón "Ingresar" delata que no hay sesión) y luego el correo de la cuenta, en las páginas
// de cuenta conocidas o siguiendo los enlaces "Mi cuenta", "Mi perfil"… del propio portal.
const MAX_PAGINAS_CORREO = 5;

// Una página de cuenta puede llevar el perfil del usuario (`{perfil}`): LinkedIn no abre el
// contacto en /in/me/, redirige al perfil real; `cuenta.perfil` es la expresión que lo extrae de
// la URL en la que terminó la página de inicio
// LinkedIn salta de /in/me/ al perfil con JavaScript, ya cargada la página: se espera a que la
// pestaña esté en una URL con usuario real antes de armar la página de cuenta
async function esperarPerfil(tabId, cuenta, tab, esperaMs = 10000) {
  const limite = Date.now() + esperaMs;
  while (!conPerfil("{perfil}", cuenta, tab.url) && Date.now() < limite) {
    await new Promise((resolver) => setTimeout(resolver, 500));
    tab = await chrome.tabs.get(tabId);
  }
  return tab;
}

function conPerfil(url, cuenta, actual) {
  if (!url.includes("{perfil}")) return url;
  const m = cuenta.perfil ? actual.match(new RegExp(cuenta.perfil)) : null;
  return m ? url.replace("{perfil}", m[0]) : null;
}

async function revisarPortal(plataforma) {
  const sel = await selectores(plataforma);
  const sesion = sel.sesion || {};
  const cuenta = sel.cuenta || {};
  const inicio = sesion.url || cuenta.url || (cuenta.urls || [])[0];
  if (!inicio) throw new Error(`sin página para revisar ${plataforma}`);
  const pestana = await abrirPestana(inicio);
  try {
    let tab = await chrome.tabs.get(pestana.id);
    if (plataformaDeUrl(tab.url) !== plataforma) {
      return { estado: "sin_sesion", correo: null, motivo: "fuera_del_portal" };
    }
    // Un portal que salta a otra página mientras se lee (LinkedIn: /in/me/ → perfil) destruye el
    // contexto del script: se reintenta sobre la página en la que quedó
    let s;
    for (let intento = 1; ; intento++) {
      try {
        await inyectar(pestana.id, plataforma);
        s = await enPestana(
          pestana.id, (ss) => globalThis.__asistente.revisar(ss, { secciones: false }), sel,
        );
        if (!s) throw new Error("la página cambió mientras se leía");  // sin resultado: navegó
        break;
      } catch (error) {
        if (intento >= 4) throw error;
        await new Promise((resolver) => setTimeout(resolver, 1500));
        tab = await chrome.tabs.get(pestana.id);
      }
    }
    if (s.estado === "sin_sesion") return { estado: "sin_sesion", correo: null, motivo: s.motivo };
    let correo = s.correo;
    let origen = correo ? tab.url : null;
    // Primero el correo del HTML del portal (cuenta.html), que no depende de que la pestaña en
    // segundo plano pinte nada; su motivo es el que se informa si al final no hay correo
    let motivo = null;
    if (!correo && cuenta.html) {
      const h = await (async () => {
        await inyectar(pestana.id, plataforma);
        return enPestana(pestana.id, (ss) => globalThis.__asistente.correoPorHtml(ss), sel);
      })().catch(() => null);
      if (h && h.correo) {
        correo = h.correo;
        origen = new URL(h.ruta, tab.url).href;
      } else {
        motivo = (h && h.motivo) || "sin_correo";
      }
    }
    if (!correo && (cuenta.urls || []).some((u) => u.includes("{perfil}"))) {
      tab = await esperarPerfil(pestana.id, cuenta, tab);
    }
    const pendientes = [...(cuenta.urls || (cuenta.url ? [cuenta.url] : []))]
      .map((u) => conPerfil(u, cuenta, tab.url)).filter(Boolean);
    pendientes.push(...(await enPestana(
      pestana.id, (ss) => globalThis.__asistente.enlacesCuenta(ss), sel,
    )));
    const vistas = new Set([tab.url.split("#")[0]]);
    for (let i = 0; !correo && i < pendientes.length && vistas.size <= MAX_PAGINAS_CORREO; i++) {
      const url = pendientes[i].split("#")[0];
      if (vistas.has(url) || !paginaPermitida(url, plataforma)) continue;
      vistas.add(url);
      try {
        await navegar(pestana.id, url);
      } catch (error) {
        continue;
      }
      tab = await chrome.tabs.get(pestana.id);
      if (!paginaPermitida(tab.url, plataforma)) continue;
      await inyectar(pestana.id, plataforma);
      await enPestana(pestana.id, (ss) => globalThis.__asistente.abrirCuenta(ss), sel);
      await enPestana(pestana.id, (ss) => globalThis.__asistente.esperarCorreo(ss), sel);
      const r = await enPestana(pestana.id, (ss) => globalThis.__asistente.buscarCorreo(ss), sel);
      if (!r) continue;  // la página navegó mientras se leía
      if (r.sin_sesion) return { estado: "sin_sesion", correo: null };
      if (r.correo) {
        correo = r.correo;
        origen = tab.url;
      } else {
        pendientes.push(...r.enlaces);
      }
    }
    // Dónde se encontró el correo (solo la ruta): sirve para fijar el selector en el servidor
    const pagina_correo = origen ? new URL(origen).pathname : null;
    return { estado: "listo", correo: correo || null, pagina_correo, motivo: correo ? null : motivo };
  } finally {
    await cerrarPestana(pestana);
  }
}

// --- pestañas -----------------------------------------------------------------------------

// Pestaña en segundo plano: se crea vacía y luego navega, así la carga es igual a cualquier
// navegación posterior (y las pruebas pueden servir las páginas del portal)
// Pestaña en segundo plano en la ventana del usuario: tiene el tamaño real de la ventana, así
// el portal muestra su versión de escritorio (una ventana minimizada lo pasa a la versión móvil
// y oculta la cabecera y los botones). Si el portal pide una verificación, se activa.
async function abrirPestana(url) {
  const pestana = await crearPestana({ active: false });
  try {
    await navegar(pestana.id, url);
  } catch (error) {
    await cerrarPestana(pestana);
    throw error;
  }
  return pestana;
}

// Una carga lenta o descartada es transitoria: se vuelve a abrir antes de dar la postulación por
// fallida, para que salga a la primera sin que el usuario tenga que tocar nada
async function abrirPestanaConReintentos(url, intentos = 3, pausaMs = 3000) {
  for (let intento = 1; ; intento++) {
    try {
      return await abrirPestana(url);
    } catch (error) {
      if (intento >= intentos) throw error;
      await new Promise((resolver) => setTimeout(resolver, pausaMs * intento));
    }
  }
}

// Una pestaña nueva carga about:blank por su cuenta. Si se navega antes de que esa carga
// termine, Chrome puede descartar la navegación (la pestaña queda en "unloaded" aunque el
// portal respondió) y la espera agota su plazo: pasa sobre todo con el navegador ocupado.
async function crearPestana(propiedades) {
  const pestana = await chrome.tabs.create({ ...propiedades, url: "about:blank" });
  await new Promise((resolver) => {
    const fin = setTimeout(listo, 5000);
    function listo() {
      clearTimeout(fin);
      chrome.tabs.onUpdated.removeListener(oyente);
      resolver();
    }
    function oyente(id, cambio) {
      if (id === pestana.id && cambio.status === "complete") listo();
    }
    chrome.tabs.onUpdated.addListener(oyente);
    chrome.tabs.get(pestana.id).then((tab) => tab.status === "complete" && listo(), listo);
  });
  return pestana;
}

function cerrarPestana(pestana) {
  return chrome.tabs.remove(pestana.id).catch(() => {});
}

async function navegar(tabId, url) {
  const carga = esperarCargaNueva(tabId);
  await chrome.tabs.update(tabId, { url });
  await carga;
}

// Espera una navegación que empieza después de llamar a esta función. Con `inicioMs`, si la
// página no empieza a cargar en ese plazo se da por hecho que el paso no navegó (envío por
// AJAX o el portal marcó errores) y se sigue sin esperar el plazo completo.
function esperarCargaNueva(tabId, ms = CARGA_MS, inicioMs = null) {
  return new Promise((resolver, rechazar) => {
    let cargando = false;
    const fin = setTimeout(() => {
      chrome.tabs.onUpdated.removeListener(oyente);
      rechazar(new Error("la página no cargó"));
    }, ms);
    if (inicioMs) {
      setTimeout(() => {
        if (cargando) return;
        clearTimeout(fin);
        chrome.tabs.onUpdated.removeListener(oyente);
        resolver();
      }, inicioMs);
    }
    function oyente(id, cambio, tab) {
      if (id !== tabId) return;
      // La carga inicial de una ventana o pestaña nueva (about:blank) no cuenta
      if (tab && tab.url === "about:blank") return;
      if (cambio.status === "loading") cargando = true;
      if (cargando && cambio.status === "complete") {
        clearTimeout(fin);
        chrome.tabs.onUpdated.removeListener(oyente);
        resolver();
      }
    }
    chrome.tabs.onUpdated.addListener(oyente);
  });
}

async function inyectar(tabId, plataforma) {
  await chrome.scripting.executeScript({
    target: { tabId },
    files: ADAPTADORES.includes(plataforma) ? ["motor.js", `adaptadores/${plataforma}.js`] : ["motor.js"],
  });
}

async function enPestana(tabId, func, ...args) {
  const [resultado] = await chrome.scripting.executeScript({ target: { tabId }, func, args });
  if (resultado && resultado.error) throw new Error(resultado.error.message || "error en la página");
  return resultado ? resultado.result : null;
}

// --- ejecución de un trabajo ----------------------------------------------------------------

// Modo ensayo: el trabajo llena y avanza como siempre y se detiene justo antes de registrar el
// envío. `pantalla` es la última que se leyó (o el paso declarado), para decir dónde se trabaría.
let ensayoEnCurso = null;
const SIN_TRABA = ["enviada", "ensayada", "ya_postulada", "vacante_cerrada", "esperando_sesion",
  "cuenta_distinta", "completado"];

// `tipo`: "boton" (el bucle genérico, un botón que envía) o "paso" (un flujo declarado, cuyo
// paso ya envía la postulación al pulsarse)
async function ensayada(contexto, nombre, tipo) {
  const { id } = contexto.trabajo;
  await reportar(id, "ensayo_boton", nombre);
  await terminar(id, "ensayada", { motivo: `${tipo}:${String(nombre).slice(0, 100)}` });
  return { fin: true };
}

async function ejecutar(trabajo) {
  const { id, plataforma, tipo } = trabajo;
  const sel = await selectores(plataforma);
  const pasos = tipo === "completar_perfil" ? ((sel.perfil || {}).completar || []) : (sel.postular || []);
  const url = tipo === "completar_perfil" ? (sel.perfil || {}).url : trabajo.url;
  try {
    await llamar("POST", `/postulaciones/${id}/tomar`);
  } catch (error) {
    return; // otro navegador la tomó o ya no está disponible
  }
  await guardarEstado({ trabajo_actual: { id, titulo: trabajo.titulo, plataforma, inicio: Date.now() } });
  if (plataforma === "linkedin" && tipo === "postular") {
    await ejecutarLinkedin(trabajo, sel);
    return;
  }
  // Una plataforma sin pasos de postular (un ATS sin declarar) va directo al bucle genérico
  const generico = tipo === "postular" && !pasos.length && Boolean(trabajo.motor_generico);
  if ((!pasos.length && !generico) || !url) {
    await terminar(id, "formulario_desconocido", { motivo: `sin flujo de ${tipo} para ${plataforma}` });
    return;
  }
  let pestana;
  try {
    pestana = await abrirPestanaConReintentos(url);
  } catch (error) {
    await terminar(id, "fallida", { motivo: "la página de la vacante no cargó" });
    return;
  }
  let cerrar = true;
  const contexto = { trabajo, sel, cv: null, cv_nombre: null, inicio: Date.now(), envio: false };
  ensayoEnCurso = trabajo.ensayo ? { id, pantalla: 0 } : null;
  try {
    await reportar(id, "abrir", trabajo.titulo || url);
    if (generico) {
      cerrar = (await bucleGenerico(pestana.id, contexto)).cerrar !== false;
      return;
    }
    for (let i = 0; i < pasos.length; i++) {
      const paso = pasos[i];
      const tab = await chrome.tabs.get(pestana.id);
      if (!paginaPermitida(tab.url, plataforma)) {
        // Fuera del portal o en una página prohibida: el motor se niega a operar
        await terminar(id, "formulario_desconocido", { motivo: `página no permitida: ${new URL(tab.url).host}${new URL(tab.url).pathname}` });
        return;
      }
      await inyectar(pestana.id, plataforma);
      if (ensayoEnCurso) ensayoEnCurso.pantalla = i + 1;
      const r = await ejecutarPaso(pestana.id, paso, contexto);
      if (r.fin) {
        cerrar = r.cerrar !== false;
        return;
      }
    }
    await terminar(id, tipo === "completar_perfil" ? "completado" : "incierta", { motivo: "el flujo terminó sin confirmación" });
  } catch (error) {
    await terminar(id, "fallida", { motivo: String(error.message || error).slice(0, 400) });
  } finally {
    ensayoEnCurso = null;
    await guardarEstado({ trabajo_actual: null });
    if (cerrar) await cerrarPestana(pestana);
  }
}

// --- LinkedIn --------------------------------------------------------------------------------
// La vacante se abre una vez con la sesión del usuario y se clasifica con linkedin.json. En una
// externa nunca se pulsa «Solicitar»: se lee el destino del enlace /safety/go, el servidor lo
// limpia y decide, y la misma pestaña navega a la página de la empresa (plataforma `externa`).
// En una sencilla se pulsa «Solicitud sencilla» y el bucle genérico trabaja dentro del modal.
// Un destino ya resuelto por otro usuario se abre directo, sin pasar por LinkedIn.

async function ejecutarLinkedin(trabajo, sel) {
  const { id } = trabajo;
  if (!trabajo.motor_generico) {
    await terminar(id, "formulario_desconocido", { motivo: "LinkedIn necesita el motor genérico" });
    return;
  }
  const destino = trabajo.destino || null;
  let pestana;
  try {
    pestana = await abrirPestana(destino ? destino.url : trabajo.url);
  } catch (error) {
    await terminar(id, "fallida", { motivo: "la página de la vacante no cargó" });
    return;
  }
  let cerrar = true;
  const contexto = { trabajo, sel, cv: null, cv_nombre: null, inicio: Date.now(), envio: false };
  ensayoEnCurso = trabajo.ensayo ? { id, pantalla: 0 } : null;
  try {
    await reportar(id, "abrir", trabajo.titulo || trabajo.url);
    let r;
    if (destino) {
      await reportar(id, "destino_guardado", destino.familia || null);
      r = await paginaExterna(pestana.id, contexto, { accion: "abrir", ...destino });
    } else {
      r = await vacanteLinkedin(pestana.id, contexto);
    }
    cerrar = (r || {}).cerrar !== false;
  } catch (error) {
    await terminar(id, "fallida", { motivo: String(error.message || error).slice(0, 400) });
  } finally {
    ensayoEnCurso = null;
    await guardarEstado({ trabajo_actual: null });
    if (cerrar) await cerrarPestana(pestana);
  }
}

// Qué solicitud tiene la vacante: corre dentro de la pestaña con el motor ya inyectado
async function leerVacante(sel, ms) {
  const a = globalThis.__asistente.api;
  const t = sel.textos || {};
  const tipo = sel.tipo || {};
  const enUrl = (lista) => (lista || []).some((p) => location.href.includes(p));
  const limite = Date.now() + ms;
  for (;;) {
    // El muro de ingreso (/authwall) también dice «Verificación de seguridad» (visto el
    // 2026-10-27): la URL sin sesión se mira antes que los textos del aviso de seguridad
    if (enUrl((sel.sesion || {}).url_sin_sesion)) return { tipo: "sin_sesion" };
    if (enUrl((sel.seguridad || {}).url) || a.hayTexto(t.seguridad)) return { tipo: "seguridad" };
    const enlace = a.buscar(tipo.externa || [], { ocultos: true });
    if (enlace) {
      // Solo el enlace «Solicitar en el sitio web de la empresa»: hay otros /safety/go (el aviso
      // de privacidad de la empresa) que no son el destino
      const def = tipo.externa_destino || {};
      let url = null;
      try {
        const u = new URL(enlace.href);
        url = u.pathname.startsWith(def.ruta || "/safety/go") ? u.searchParams.get(def.param || "url") : u.href;
      } catch {
        url = null;
      }
      return { tipo: "externa", url };
    }
    if (a.buscar(tipo.sencilla || [])) return { tipo: "sencilla" };
    if (a.hayTexto(t.pausada)) return { tipo: "pausada" };
    if (a.hayTexto(t.cerrada)) return { tipo: "cerrada" };
    if (Date.now() >= limite) return { tipo: "desconocida" };
    await a.dormir(300);
  }
}

async function vacanteLinkedin(tabId, contexto) {
  const { trabajo, sel } = contexto;
  const { id } = trabajo;
  await inyectar(tabId, "linkedin");
  const vista = await enPestana(tabId, leerVacante, sel, 10000);
  await reportar(id, "linkedin_tipo", vista.tipo);
  if (vista.tipo === "seguridad") {
    // El servidor pausa LinkedIn 24 h para este usuario y le avisa
    await terminar(id, "bloqueada", { motivo: "aviso_seguridad" });
    return { fin: true };
  }
  if (vista.tipo === "sin_sesion") {
    await terminar(id, "esperando_sesion", { motivo: "no hay sesión iniciada en LinkedIn" });
    return { fin: true };
  }
  if (vista.tipo === "cerrada" || vista.tipo === "pausada") {
    await terminar(id, "vacante_cerrada", { motivo: vista.tipo });
    return { fin: true };
  }
  if (vista.tipo === "externa") {
    if (!vista.url) {
      await terminar(id, "formulario_desconocido", { motivo: "el enlace de la vacante externa no trae destino" });
      return { fin: true };
    }
    const r = await llamar("POST", `/postulaciones/${id}/destino`, { tipo: "externa", url: vista.url });
    return paginaExterna(tabId, contexto, r);
  }
  if (vista.tipo === "sencilla") {
    const r = await llamar("POST", `/postulaciones/${id}/destino`, { tipo: "sencilla" });
    if (r.accion !== "sencilla") {
      await terminar(id, "formulario_desconocido", { motivo: r.motivo || "respaldo" });
      return { fin: true };
    }
    return solicitudSencilla(tabId, contexto);
  }
  const html = await enPestana(tabId, () => globalThis.__asistente.html()).catch(() => null);
  await terminar(id, "formulario_desconocido", { motivo: "no se reconoció el tipo de solicitud de LinkedIn", html });
  return { fin: true };
}

// Respuesta de /destino (o el destino guardado): respaldo, esperar al usuario o abrir la página
// de la empresa en la misma pestaña y seguir con el bucle genérico como plataforma `externa`
async function paginaExterna(tabId, contexto, r) {
  const { trabajo, sel } = contexto;
  const { id } = trabajo;
  if (r.esperar_usuario) {
    await reportar(id, "esperando_usuario", "faltan datos que solo tú sabes");
    return { fin: true };
  }
  if (r.accion !== "abrir" || !r.url) {
    await terminar(id, "formulario_desconocido", { motivo: r.motivo || "respaldo" });
    return { fin: true };
  }
  const familias = r.familia ? await familiasAts() : {};
  contexto.trabajo = {
    ...trabajo,
    plataforma: "externa",
    origen: trabajo.plataforma,
    externa: {
      destino: r.url, familia: r.familia || null, familias_hosts: r.familias_hosts || [],
      hosts_prohibidos: sel.hosts_prohibidos || [],
      datos: r.familia_datos || familias[r.familia] || null,
    },
    ...(r.esquema ? { esquema: r.esquema } : {}),
    ...(r.receta ? { receta: r.receta } : {}),
  };
  const ambito = contexto.trabajo.externa;
  const motivo = motivoExterno(r.url, ambito);
  if (motivo) {
    await terminar(id, "formulario_desconocido", { motivo });
    return { fin: true };
  }
  const actual = (await chrome.tabs.get(tabId)).url;
  if (actual.split("#")[0] !== r.url.split("#")[0]) await navegar(tabId, r.url);
  await reportar(id, "destino", `${r.familia || "generico"}: ${new URL(r.url).host}`);
  return bucleGenerico(tabId, contexto);
}

async function solicitudSencilla(tabId, contexto) {
  const { trabajo, sel } = contexto;
  const { id } = trabajo;
  const modal = sel.modal || {};
  const abierto = await enPestana(tabId, async (s) => {
    const a = globalThis.__asistente.api;
    const boton = a.buscar((s.tipo || {}).sencilla || []);
    if (!boton) return false;
    boton.click();
    const contenedor = (s.modal || {}).contenedor || [];
    if (!(await a.esperar(contenedor, 10000))) return false;
    // El contenido del modal llega después del marco: se espera a que traiga sus botones
    await a.esperar(contenedor.map((c) => `${c} footer button`), 5000);
    return true;
  }, sel);
  if (!abierto) {
    const html = await enPestana(tabId, () => globalThis.__asistente.html()).catch(() => null);
    await terminar(id, "formulario_desconocido", { motivo: "no se abrió el modal de la Solicitud sencilla", html });
    return { fin: true };
  }
  contexto.trabajo = { ...trabajo, modal: true };
  try {
    return await bucleGenerico(tabId, contexto);
  } finally {
    // Sin envío (ensayo, respaldo, error) el modal se cierra con «Descartar», nunca «Guardar»
    if (!contexto.envio) {
      await enPestana(tabId, (d) => globalThis.__asistente.generico.descartarModal(d),
        defModal(modal)).catch(() => null);
    }
  }
}

// Lo que el motor necesita del modal de linkedin.json
function defModal(modal) {
  return {
    contenedor: modal.contenedor || [],
    cerrar: modal.cerrar || [],
    aviso: (modal.confirmar_cierre || {}).contenedor || [],
    descartar: (modal.confirmar_cierre || {}).descartar || "descartar",
    desmarcar: (modal.seguir_empresa || {}).selector || [],
    cv_grupo: (modal.cv || {}).grupo || [],
    cv_subir: (modal.cv || {}).subir || "",
  };
}

// Reglas del motor ajustadas al trabajo: los datos de la familia de ATS del destino van antes
// que las reglas genéricas y, en la Solicitud sencilla, todo se lee dentro del modal
function reglasDelTrabajo(base, trabajo, sel) {
  const reglas = { ...base, textos: { ...(base.textos || {}) } };
  const sumar = (clave, lista) => {
    if (!lista || !lista.length) return;
    reglas.textos[clave] = { datos: lista, ...(reglas.textos[clave] || {}) };
  };
  const datos = trabajo.externa && trabajo.externa.datos;
  if (datos) {
    reglas.familia = datos;
    sumar("enviar", (datos.enviar || {}).textos);
    sumar("exito", (datos.exito || {}).textos);
    reglas.url_exito = [...((datos.exito || {}).url || []), ...(base.url_exito || [])];
  }
  if (trabajo.modal) {
    const modal = (sel || {}).modal || {};
    const botones = modal.botones || {};
    const def = defModal(modal);
    reglas.contenedor = def.contenedor;
    reglas.excluir = [...def.desmarcar, ...def.cv_grupo];
    sumar("avanzar", [...(botones.siguiente || []), ...(botones.revisar || [])]);
    sumar("enviar", botones.enviar);
    sumar("nunca", [...(botones.volver || []), "descartar", "guardar"]);
    sumar("exito", ((sel || {}).textos || {}).confirmacion);
  }
  return reglas;
}

async function ejecutarPaso(tabId, paso, contexto) {
  const { trabajo, sel } = contexto;
  const { id, plataforma } = trabajo;
  const datos = { plataforma };
  const correr = (p, d = datos) =>
    enPestana(tabId, (pp, s, dd) => globalThis.__asistente.paso(pp, s, dd), p, sel, d);

  if (paso.accion === "cv_subir" || paso.accion === "cv_liberar" || paso.accion === "cv_verificar") {
    const modo = (sel.cv || {}).modo || "adjunto";
    if (modo !== "perfil_unico" && modo !== "perfil_multiple") return {};
    if (paso.accion === "cv_liberar" && modo !== "perfil_multiple") return {};
    if (!trabajo.actualizar_cv_portal) {
      if (paso.accion === "cv_subir") await reportar(id, "cv_sin_autorizacion", "no se toca el CV del portal");
      return {};
    }
    if (!contexto.cv) await obtenerCv(contexto, []);
    datos.cv = contexto.cv;
    datos.cv_nombre = contexto.cv_nombre;
  }
  if (paso.url) {
    // El paso se ejecuta en otra página (por ejemplo, la hoja de vida del perfil)
    const destino = paso.url === "$vacante" ? trabajo.url : paso.url;
    const actual = (await chrome.tabs.get(tabId)).url;
    if (actual.split("#")[0] !== destino.split("#")[0]) {
      if (!paginaPermitida(destino, plataforma)) {
        await terminar(id, "formulario_desconocido", { motivo: "página no permitida en los selectores" });
        return { fin: true };
      }
      await navegar(tabId, destino);
      await inyectar(tabId, plataforma);
    }
  }
  if (trabajo.ensayo && (paso.accion === "enviar" || paso.envia)) {
    // Ensayo: se comprueba que el botón de enviar existe (y la sesión) y no se pulsa
    const r = await correrSeguro(
      tabId, { ...paso, accion: "esperar", opcional: false, navega: false }, plataforma, correr);
    if (r && r.sin_sesion) {
      await terminar(id, "esperando_sesion", { motivo: "no hay sesión iniciada en el portal" });
      return { fin: true };
    }
    if (!r || r.error) {
      return fallarPaso(tabId, contexto, (r && r.error) || "formulario_desconocido",
        { motivo: (r && r.motivo) || "no apareció el botón de enviar", html: r && r.html });
    }
    return ensayada(contexto, paso.nombre || paso.accion, "paso");
  }
  if (paso.accion === "enviar" || paso.envia) {
    // El servidor registra envio_pulsado antes del clic: si el navegador se cierra justo
    // después, la postulación queda "incierta" y nunca se envía dos veces.
    await llamar("POST", `/postulaciones/${id}/envio`);
    contexto.envio = true;
  }
  await reportar(id, paso.nombre || paso.accion);

  const navega = paso.navega ? esperarCargaNueva(tabId, CARGA_MS, 6000).catch(() => {}) : null;
  let r = await correrSeguro(tabId, paso, plataforma, correr);
  if (r && r.captcha) {
    const resuelto = await esperarVerificacion(tabId, id, sel, plataforma);
    if (!resuelto) return { fin: true, cerrar: false };
    await inyectar(tabId, plataforma);
    r = await correr(paso);
  }
  if (!r) throw new Error("el paso no devolvió resultado");
  if (r.sin_sesion) {
    await terminar(id, "esperando_sesion", { motivo: "no hay sesión iniciada en el portal" });
    return { fin: true };
  }
  if (paso.abre_sin_enviar && (r.chat || (r.campos && r.campos.length) || r.contenedor_abierto)) {
    // El clic anterior (como «Aplicar» en Magneto) abrió una encuesta aún sin enviar
    contexto.envio = false;
  }
  if (r.error) return fallarPaso(tabId, contexto, r.error, { motivo: r.motivo, html: r.html });
  if (r.terminar) {
    await terminar(id, r.terminar, { motivo: r.motivo });
    return { fin: true };
  }
  if (r.ir) {
    if (!paginaPermitida(r.ir, plataforma)) {
      await terminar(id, "formulario_desconocido", { motivo: "enlace fuera del portal" });
      return { fin: true };
    }
    await navegar(tabId, r.ir);
    return {};
  }
  if (r.chat) {
    const lleno = await formularioChat(tabId, contexto, paso);
    if (lleno.fin) return lleno;
  }
  if (r.campos && r.campos.length) {
    const lleno = await formulario(tabId, contexto, r.campos);
    if (lleno.fin) return lleno;
  }
  if (paso.accion === "cv_verificar" && r.verificado === false) {
    await reportar(id, "cv_verificar_fallo", "se postula con el CV existente");
  }
  if (paso.accion === "cv_liberar" && r.liberado) {
    await reportar(id, "cv_liberado", "se reemplaza un CV subido antes por el sistema");
  }
  if (paso.accion === "cv_liberar" && r.sin_espacio) {
    await reportar(id, "cv_sin_espacio", "límite de CV alcanzado sin CV propios del sistema");
  }
  if (paso.accion === "confirmar") {
    if (r.confirmado) {
      await terminar(id, trabajo.tipo === "completar_perfil" ? "completado" : "enviada",
        { confirmacion: r.texto });
    } else {
      await terminar(id, "incierta", { motivo: "no apareció la confirmación", html: r.html });
    }
    return { fin: true };
  }
  if (navega) await navega;
  return {};
}

// Un paso puede quedar cortado porque la página cambió mientras corría (el envío de un
// formulario o una redirección del portal): el script muere y no devuelve nada. Un clic ya
// hizo su trabajo; un paso de lectura se repite en la página nueva cuando termina de cargar.
async function correrSeguro(tabId, paso, plataforma, correr) {
  // Tope por si la página se cuelga a mitad del paso y Chrome nunca devuelve el resultado
  const tope = (paso.ms || 10000) + 20000;
  for (let intento = 0; ; intento++) {
    let r = null;
    let reloj;
    try {
      r = await Promise.race([
        correr(paso),
        new Promise((resolver) => (reloj = setTimeout(() => resolver(null), tope))),
      ]);
    } catch (error) {
      r = null;
    } finally {
      clearTimeout(reloj);
    }
    if (r) return r;
    if (paso.accion === "clic" || paso.accion === "enviar") return { ok: true, navego: true };
    if (intento >= 2) return null;
    await esperarCargaCompleta(tabId);
    await inyectar(tabId, plataforma);
  }
}

async function esperarCargaCompleta(tabId, ms = CARGA_MS) {
  const limite = Date.now() + ms;
  await new Promise((r) => setTimeout(r, 500));
  while (Date.now() < limite) {
    const tab = await chrome.tabs.get(tabId);
    if (tab.status === "complete") return;
    await new Promise((r) => setTimeout(r, 300));
  }
}

async function formulario(tabId, contexto, campos) {
  const { trabajo } = contexto;
  const r = await llamar("POST", `/postulaciones/${trabajo.id}/formulario`, { campos });
  if (r.esperar_usuario) {
    // El bot le pregunta al usuario lo que falta; la postulación vuelve a la cola al responder
    await reportar(trabajo.id, "esperando_usuario", "faltan datos que solo tú sabes");
    return { fin: true };
  }
  if (r.cv_url && campos.some((c) => c.tipo === "archivo")) await descargarCv(contexto, r);
  const { llenado_max_ms } = await opciones();
  let reloj;
  const lleno = await Promise.race([
    enPestana(
      tabId,
      (pp, s, dd) => globalThis.__asistente.paso(pp, s, dd),
      { accion: "llenar" },
      contexto.sel,
      { plataforma: trabajo.plataforma, respuestas: r.respuestas, cv: contexto.cv },
    ),
    new Promise((resolver) => (reloj = setTimeout(() => resolver({ vencido: true }), llenado_max_ms))),
  ]).finally(() => clearTimeout(reloj));
  // Cada respuesta escrita queda en el historial (sin su texto), también si el llenado falló
  for (const n of (lleno && lleno.escritas) || []) await reportar(trabajo.id, `llenado_${n}`);
  if (lleno && lleno.vencido) {
    // La página no devolvió el llenado: no se envía nada a ciegas. La evidencia es lo que
    // se alcance a leer (si la página sigue colgada, se termina sin ella)
    const html = await Promise.race([
      enPestana(tabId, () => globalThis.__asistente.html()).catch(() => null),
      new Promise((resolver) => setTimeout(() => resolver(null), 3000)),
    ]);
    await terminar(trabajo.id, "formulario_desconocido", { motivo: "llenado_sin_respuesta", html });
    return { fin: true };
  }
  if (lleno && lleno.error) {
    // Una respuesta no quedó marcada: no se envía nada a ciegas
    return fallarPaso(tabId, contexto, lleno.error, { motivo: lleno.motivo, html: lleno.html });
  }
  await reportar(trabajo.id, "llenado", `${r.respuestas.length} respuestas`);
  // El servidor arma el resumen final con esto: qué hoja de vida recibió el portal
  if (lleno && lleno.adjunto) await reportar(trabajo.id, "cv_adjunto", lleno.adjunto);
  return {};
}

async function formularioChat(tabId, contexto, paso) {
  const { trabajo, sel } = contexto;
  const chat = paso.chat || {};
  const topePreguntas = chat.max_preguntas || 40;
  const { llenado_max_ms } = await opciones();
  const correr = (p, extra = {}) => enPestana(
    tabId,
    (pp, s, dd) => globalThis.__asistente.paso(pp, s, dd),
    p,
    sel,
    { plataforma: trabajo.plataforma, ...extra },
  );
  let respondidas = 0;
  for (let n = 1; n <= topePreguntas + 1; n++) {
    const turno = await correrSeguro(
      tabId,
      { accion: "chat_turno", chat, ms: chat.espera_turno_ms || 8000 },
      trabajo.plataforma,
      correr,
    );
    if (!turno) throw new Error("el turno del chat no devolvió resultado");
    if (turno.sin_sesion) {
      await terminar(trabajo.id, "esperando_sesion", { motivo: "no hay sesión iniciada en el portal" });
      return { fin: true };
    }
    if (turno.listo) {
      await reportar(trabajo.id, "llenado", `${respondidas} respuestas`);
      return {};
    }
    if (turno.error) {
      return fallarPaso(tabId, contexto, turno.error, { motivo: turno.motivo, html: turno.html });
    }
    if (n > topePreguntas) {
      return fallarPaso(tabId, contexto, "formulario_desconocido", {
        motivo: "chat: la encuesta superó el máximo de preguntas",
      });
    }
    const r = await llamar("POST", `/postulaciones/${trabajo.id}/formulario`, {
      campos: [turno.campo],
    });
    if (r.esperar_usuario) {
      await reportar(trabajo.id, "esperando_usuario", "faltan datos que solo tú sabes");
      return { fin: true };
    }
    let reloj;
    const lleno = await Promise.race([
      correr({ accion: "chat_llenar" }, { respuestas: r.respuestas }),
      new Promise((resolver) => (reloj = setTimeout(() => resolver({ vencido: true }), llenado_max_ms))),
    ]).finally(() => clearTimeout(reloj));
    if (lleno && lleno.vencido) {
      const html = await Promise.race([
        enPestana(tabId, () => globalThis.__asistente.html()).catch(() => null),
        new Promise((resolver) => setTimeout(() => resolver(null), 3000)),
      ]);
      await terminar(trabajo.id, "formulario_desconocido", { motivo: "llenado_sin_respuesta", html });
      return { fin: true };
    }
    if (!lleno || lleno.error) {
      return fallarPaso(tabId, contexto, (lleno && lleno.error) || "formulario_desconocido", {
        motivo: (lleno && lleno.motivo) || "chat: fallo al responder el turno",
        html: lleno && lleno.html,
      });
    }
    respondidas += 1;
    await reportar(trabajo.id, `llenado_${respondidas}`);
  }
  return {};
}

async function obtenerCv(contexto, campos) {
  const r = await llamar("POST", `/postulaciones/${contexto.trabajo.id}/formulario`, { campos });
  if (r.cv_url) await descargarCv(contexto, r);
}

async function descargarArchivo(url, nombre) {
  const bytes = new Uint8Array(await llamar("GET", url, undefined, { binario: true }));
  let binario = "";
  for (let i = 0; i < bytes.length; i += 0x8000) {
    binario += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  }
  return { base64: btoa(binario), nombre };
}

async function descargarCv(contexto, r) {
  contexto.cv = await descargarArchivo(r.cv_url, r.cv_nombre || "CV.pdf");
  contexto.cv_nombre = contexto.cv.nombre;
}

// --- bucle genérico --------------------------------------------------------------------------
// Por cada pantalla: leer (en el marco con más campos) → POST /pantalla (decisión del servidor)
// → llenar → pulsar → resultado. Sirve a las plataformas sin pasos declarados y, con
// `respaldo_declarado`, a los flujos declarados que fallan antes del envío. Después de registrar
// el envío nunca reintenta: sin señal clara la postulación queda `incierta`.

let bucleVivo = false;

// Un paso declarado que falla antes del envío sigue con el bucle genérico si el servidor lo
// permite; después del envío o sin la bandera, termina como siempre
async function fallarPaso(tabId, contexto, estado, datos) {
  const { trabajo } = contexto;
  const motor = trabajo.motor_generico || {};
  if (estado === "formulario_desconocido" && motor.respaldo_declarado && !contexto.envio
      && trabajo.tipo === "postular") {
    await reportar(trabajo.id, "respaldo_generico", datos.motivo || null);
    return bucleGenerico(tabId, contexto);
  }
  await terminar(trabajo.id, estado, datos);
  return { fin: true };
}

async function guardarBucle(tabId, contexto) {
  await chrome.storage.local.set({
    bucle_generico: { tabId, trabajo: contexto.trabajo, inicio: contexto.inicio,
      envio: contexto.envio, bucle: contexto.bucle },
  });
}

// Marcos de la pestaña donde el motor puede operar (la página y los iframes de dominios del
// portal); un iframe de otro dominio se trata como si no existiera
async function marcosPermitidos(tabId, plataforma, ambito = null) {
  let marcos;
  try {
    marcos = await chrome.scripting.executeScript({
      target: { tabId, allFrames: true }, func: () => location.href,
    });
  } catch (error) {
    return [];
  }
  return marcos.filter((m) => m.result && paginaPermitida(m.result, plataforma, ambito))
    .map((m) => m.frameId);
}

// Lee todos los marcos permitidos y elige el que tiene más campos (a igual número, el que
// tiene un botón sugerido y luego el más alto en la página)
async function leerMarcos(tabId, plataforma, reglas, ambito = null) {
  for (let intento = 0; intento < 3; intento++) {
    const frameIds = await marcosPermitidos(tabId, plataforma, ambito);
    if (!frameIds.length) return { prohibida: true };
    try {
      const target = { tabId, frameIds };
      await chrome.scripting.executeScript({ target, files: ["motor.js"] });
      const leidos = await chrome.scripting.executeScript({
        target, func: (r) => globalThis.__asistente.generico.leerPantalla(r), args: [reglas],
      });
      const lecturas = leidos.filter((l) => l.result).map((l) => ({ frameId: l.frameId, pantalla: l.result }));
      if (lecturas.length) {
        lecturas.sort((a, b) => b.pantalla.campos.length - a.pantalla.campos.length
          || Number(Boolean(b.pantalla.sugerido)) - Number(Boolean(a.pantalla.sugerido))
          || a.frameId - b.frameId);
        return lecturas[0];
      }
    } catch (error) {
      // la página cambió mientras se leía
    }
    await esperarCargaCompleta(tabId);
  }
  return { fallo: true };
}

// Corre `func` en el marco elegido, con su URL revisada antes. null: el marco cambió y el
// script murió (se espera la carga y se reintenta si `reintentos` lo permite).
async function enMarco(marco, func, args = [], { reintentos = 3 } = {}) {
  const target = { tabId: marco.tabId, frameIds: [marco.frameId] };
  for (let intento = 0; intento < reintentos; intento++) {
    try {
      const [donde] = await chrome.scripting.executeScript({ target, func: () => location.href });
      if (!donde || !donde.result) throw new Error("el marco ya no está");
      if (!paginaPermitida(donde.result, marco.plataforma, marco.ambito)) return { prohibida: donde.result };
      await chrome.scripting.executeScript({ target, files: ["motor.js"] });
      const [r] = await chrome.scripting.executeScript({ target, func, args });
      if (r && r.result != null) return r.result;
    } catch (error) {
      // el marco navegó o se cerró
    }
    if (intento + 1 < reintentos) await esperarCargaCompleta(marco.tabId);
  }
  return null;
}

async function evidencia(marco) {
  return Promise.race([
    enMarco(marco, () => globalThis.__asistente.generico.html(), [], { reintentos: 1 }),
    new Promise((resolver) => setTimeout(() => resolver(null), 3000)),
  ]).then((h) => (typeof h === "string" ? h : null)).catch(() => null);
}

// Espera el resultado de avanzar o enviar, también a través de una navegación: el script de la
// página muere al navegar, así que se lee en tramos cortos hasta que algo cambie
async function esperarResultado(marco, reglas, previo, ms) {
  const limite = Date.now() + ms;
  for (;;) {
    const tramo = Math.max(0, Math.min(limite - Date.now(), 1500));
    const r = await enMarco(
      marco, (rg, pv, t) => globalThis.__asistente.generico.resultado(rg, pv, t),
      [reglas, previo, tramo], { reintentos: 1 },
    );
    if (r && r.prohibida) return { resultado: "prohibida", url: r.prohibida };
    if (r && r.resultado !== "sin_cambios") return r;
    if (Date.now() >= limite) return r || { resultado: "pantalla_nueva" };
    if (!r) await esperarCargaCompleta(marco.tabId);
  }
}

async function bucleGenerico(tabId, contexto) {
  bucleVivo = true;
  try {
    return await recorrerPantallas(tabId, contexto);
  } finally {
    bucleVivo = false;
    await chrome.storage.local.remove("bucle_generico").catch(() => {});
  }
}

// --- esquema anticipado --------------------------------------------------------------------
// Si el trabajo trae las respuestas del formulario (el servidor las resolvió al tocar ⚡), una
// pantalla cuyos campos están todos ahí se llena sin consultar al servidor, con el botón que
// sugieren las reglas. Cualquier campo que no esté, un archivo o la falta de botón sugerido
// mandan la pantalla al servidor, como siempre.

function normalizarClave(texto) {
  return String(texto || "")
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/\s+/g, " ")
    .trim();
}

// La misma clave que arma el servidor (recetas.clave_campo): el name o la etiqueta sin signos
function claveCampo(campo) {
  const nombre = normalizarClave(campo.nombre);
  const clave = nombre || normalizarClave(campo.texto).replace(/[^a-z0-9]+/g, " ");
  return clave.trim().slice(0, 120);
}

function decisionAnticipada(trabajo, p) {
  const resueltas = ((trabajo.esquema || {}).respuestas) || {};
  const campos = p.campos || [];
  if (p.clase !== "formulario" || !p.sugerido || !campos.length) return null;
  if (!["avanzar", "enviar"].includes(p.sugerido.accion)) return null;
  const respuestas = [];
  for (const [indice, campo] of campos.entries()) {
    const texto = campo.tipo === "archivo" ? null : resueltas[claveCampo(campo)];
    if (!texto) return null;
    const opciones = campo.opciones || [];
    if (!opciones.length) {
      respuestas.push({ indice, valor: texto });
      continue;
    }
    const opcion = opciones.findIndex((o) => normalizarClave(o) === normalizarClave(texto));
    if (opcion < 0) return null;
    respuestas.push({ indice, opcion });
  }
  return {
    esperar_usuario: false, anticipada: true, respuestas, cv_url: null, cv_nombre: null,
    documentos: {}, accion: { tipo: p.sugerido.accion, indice: p.sugerido.indice },
  };
}

async function recorrerPantallas(tabId, contexto) {
  const { trabajo } = contexto;
  const { id, plataforma } = trabajo;
  const topes = { ...TOPES_GENERICO, ...(trabajo.motor_generico || {}) };
  const { resultado_ms: resultadoMs, llenado_max_ms: llenadoMs } = await opciones();
  const e = (contexto.bucle ||= { pantallas: 0, max_campos: 0, clave: null, iguales: 0, corrigiendo: false });
  const ambito = trabajo.externa || null;
  let marco = { tabId, frameId: 0, plataforma, ambito };
  // Tras registrar el envío, un final sin señal clara es incierta (no se reintenta nunca)
  const detener = async (motivo, html = null) => {
    await terminar(id, contexto.envio ? "incierta" : "formulario_desconocido", { motivo, html });
    return { fin: true };
  };
  // En una página externa el motivo dice adónde se fue: salto_de_dominio, oauth…
  const prohibida = async (url = null) => {
    if (plataforma !== "externa") return "página no permitida";
    const donde = url || (await chrome.tabs.get(tabId).catch(() => ({}))).url;
    return (donde && motivoExterno(donde, ambito)) || "página no permitida";
  };
  let reglas;
  try {
    reglas = reglasDelTrabajo(await reglasMotor(), trabajo, contexto.sel);
  } catch (error) {
    return detener("el motor genérico no está disponible en el servidor");
  }
  const modal = trabajo.modal ? defModal((contexto.sel || {}).modal || {}) : null;

  for (;;) {
    await guardarBucle(tabId, contexto);

    if (plataforma === "externa") {
      const motivo = motivoExterno((await chrome.tabs.get(tabId)).url, ambito);
      if (motivo) return detener(motivo);
    }
    if (modal) {
      // «Sigue a …» desmarcada y el CV resuelto antes de leer la pantalla del modal
      await inyectar(tabId, "linkedin").catch(() => {});
      const listo = await enPestana(tabId, (d, o) => globalThis.__asistente.generico.prepararModal(d, o),
        modal, { subir_cv: Boolean(trabajo.actualizar_cv_portal) }).catch(() => null);
      if (listo && listo.sin_cv) return detener("linkedin_sin_cv");
      if (listo && listo.desmarcadas) await reportar(id, "seguir_empresa", "desmarcada");
    }
    const lectura = await leerMarcos(tabId, plataforma, reglas, ambito);
    if (lectura.prohibida) return detener(await prohibida());
    if (lectura.fallo) return detener("no se pudo leer la pantalla");
    marco = { tabId, frameId: lectura.frameId, plataforma, ambito };
    const p = lectura.pantalla;
    e.pantallas += 1;
    if (ensayoEnCurso) ensayoEnCurso.pantalla = e.pantallas;
    e.max_campos = Math.max(e.max_campos, p.campos.length);
    const clave = `${p.clase}|${p.url}|${p.firma.join(",")}`;
    e.iguales = clave === e.clave ? e.iguales + 1 : 1;
    e.clave = clave;
    await guardarBucle(tabId, contexto);
    const registrar = (accion) => reportar(id, `pantalla_${e.pantallas}`,
      `${p.clase}; ${p.campos.length} campos; ${accion || "sin botón"}`);

    if (p.clase === "exito") {
      await registrar("éxito");
      if (!contexto.envio) return detener("la página mostraba una confirmación antes de enviar");
      await terminar(id, "enviada", { confirmacion: p.exito && p.exito.texto });
      return { fin: true };
    }
    if (p.clase === "barrera") {
      await registrar(`barrera ${p.motivo}`);
      return detener(p.motivo || "barrera", await evidencia(marco));
    }
    // Los topes cuentan las pantallas que piden una acción: la página de gracias siempre se lee
    if (Date.now() - contexto.inicio > topes.max_minutos * 60000) {
      await registrar("tope de tiempo");
      return detener(`pasaron más de ${topes.max_minutos} minutos`, await evidencia(marco));
    }
    const tope = e.max_campos <= 1 ? topes.max_pantallas_una_pregunta : topes.max_pantallas;
    if (e.pantallas > tope) {
      await registrar("tope de pantallas");
      return detener(`más de ${tope} pantallas`, await evidencia(marco));
    }
    if (e.iguales >= REPETICIONES_MAX) {
      await registrar("repetida");
      return detener(`la misma pantalla se repitió ${REPETICIONES_MAX} veces`, await evidencia(marco));
    }

    let decision = e.corrigiendo ? null : decisionAnticipada(trabajo, p);
    if (!decision) {
      try {
        decision = await llamar("POST", `/postulaciones/${id}/pantalla`, {
          numero: e.pantallas, clase: p.clase, motivo: p.motivo, idioma: p.idioma, url: p.url,
          campos: p.campos, botones: p.botones, sugerido: p.sugerido, firma: p.firma,
          resumen: p.resumen, exito: p.exito, correccion: e.corrigiendo,
        });
      } catch (error) {
        await registrar("sin decisión");
        return detener("el servidor no resolvió la pantalla", await evidencia(marco));
      }
    }
    if (decision.esperar_usuario) {
      await registrar("pregunta al usuario");
      await reportar(id, "esperando_usuario", "faltan datos que solo tú sabes");
      return { fin: true };
    }
    const accion = decision.accion || {};
    const boton = (p.botones || []).find((b) => b.indice === accion.indice);
    const origen = decision.anticipada ? " (esquema anticipado)" : "";
    await registrar(accion.tipo ? `${accion.tipo}${boton ? ` «${boton.texto}»` : ""}${origen}` : null);

    if (accion.tipo === "respaldo") {
      return detener(accion.motivo || "respaldo", await evidencia(marco));
    }
    if (accion.tipo === "terminar") {
      await terminar(id, accion.estado, { motivo: accion.motivo || null });
      return { fin: true };
    }
    if (accion.tipo === "exito") {
      // Lo decide el árbitro: solo vale si el envío ya se registró
      if (!contexto.envio) return detener("el árbitro vio una confirmación sin envío");
      await terminar(id, "enviada", { confirmacion: accion.texto || null });
      return { fin: true };
    }

    const respuestas = decision.respuestas || [];
    if (respuestas.length || p.campos.some((c) => c.tipo === "archivo")) {
      if (decision.cv_url && !contexto.cv && p.campos.some((c) => c.tipo === "archivo")) {
        await descargarCv(contexto, decision);
      }
      // Otros documentos del usuario (certificado de notas, carta…): se bajan una vez por tipo
      const documentos = (contexto.documentos ||= {});
      for (const [tipo, d] of Object.entries(decision.documentos || {})) {
        if (!documentos[tipo]) documentos[tipo] = await descargarArchivo(d.url, d.nombre || `${tipo}.pdf`);
      }
      const archivos = { ...documentos, ...(contexto.cv ? { cv: contexto.cv } : {}) };
      let reloj;
      const lleno = await Promise.race([
        enMarco(marco, (rs, ar) => globalThis.__asistente.generico.llenar(rs, ar),
          [respuestas, archivos], { reintentos: 1 }),
        new Promise((resolver) => (reloj = setTimeout(() => resolver({ vencido: true }), llenadoMs))),
      ]).finally(() => clearTimeout(reloj));
      if (!lleno || lleno.vencido) {
        return detener("llenado_sin_respuesta", await evidencia(marco));
      }
      if (lleno.prohibida) return detener(await prohibida(lleno.prohibida));
      for (const n of lleno.escritas || []) await reportar(id, `llenado_${n}`);
      if (lleno.error) {
        await terminar(id, lleno.error, { motivo: lleno.motivo, html: lleno.html });
        return { fin: true };
      }
      if ((lleno.adjuntos || []).length) await reportar(id, "cv_adjunto", contexto.cv && contexto.cv.nombre);
    }

    if (accion.tipo === "esperar") {
      await new Promise((r) => setTimeout(r, Math.min(Number(accion.ms) || 1000, 10000)));
      continue;
    }
    if (accion.tipo !== "avanzar" && accion.tipo !== "enviar") {
      return detener(`acción no soportada: ${String(accion.tipo).slice(0, 30)}`, await evidencia(marco));
    }
    if (!boton || boton.clase === "nunca") {
      return detener("la decisión no apunta a un botón", await evidencia(marco));
    }
    if (accion.tipo === "enviar" && !contexto.envio && trabajo.ensayo) {
      return ensayada(contexto, boton.texto, "boton");
    }
    if (accion.tipo === "enviar" && !contexto.envio) {
      // Como en los flujos declarados: el servidor registra el envío antes del clic. La vuelta
      // de corrección tras un error de validación no registra uno nuevo.
      await llamar("POST", `/postulaciones/${id}/envio`);
      contexto.envio = true;
      await guardarBucle(tabId, contexto);
    }
    const pulso = await enMarco(marco, (i) => globalThis.__asistente.generico.pulsar(i),
      [accion.indice], { reintentos: 1 });
    if (pulso && pulso.prohibida) return detener(await prohibida(pulso.prohibida));
    if (!pulso) return detener("no se pudo pulsar el botón", await evidencia(marco));
    if (pulso.error) {
      await terminar(id, contexto.envio ? "incierta" : pulso.error, { motivo: pulso.motivo, html: await evidencia(marco) });
      return { fin: true };
    }

    const previo = { firma: p.firma, url: p.url, encabezados: p.resumen.encabezados, accion: accion.tipo };
    // El clic llega unos ms después de responder: sin esta pausa se leerían los errores de antes
    await new Promise((resolver) => setTimeout(resolver, 300));
    const r = await esperarResultado(marco, reglas, previo, resultadoMs);
    if (r.resultado === "exito") {
      if (!contexto.envio) return detener("hubo una confirmación sin que se registrara el envío");
      await terminar(id, "enviada", { confirmacion: r.texto });
      return { fin: true };
    }
    if (r.resultado === "prohibida") return detener(await prohibida(r.url));
    if (r.resultado === "barrera") return detener(r.motivo || "barrera", await evidencia(marco));
    if (r.resultado === "error") {
      // Una sola vuelta de corrección por pantalla; si persiste, el portal no la aceptó
      if (e.corrigiendo) {
        await terminar(id, "formulario_desconocido", { motivo: "el portal sigue marcando errores", html: await evidencia(marco) });
        return { fin: true };
      }
      e.corrigiendo = true;
      continue;
    }
    e.corrigiendo = false;
    if (r.resultado === "sin_cambios" && accion.tipo === "enviar") {
      return detener("sin señal de que el portal recibiera el envío", await evidencia(marco));
    }
    // campos_nuevos y pantalla_nueva: otra vuelta. sin_cambios tras avanzar vuelve a leer la
    // misma pantalla y el tope de repeticiones la corta (la reparación con IA es de /reparar)
  }
}

// El worker de MV3 puede dormirse a mitad del bucle: la pantalla en curso queda en
// chrome.storage y, si no se había registrado el envío, el siguiente latido sigue desde ahí.
// Con el envío registrado no se retoma nada: la postulación queda como incierta.
async function retomarBucle() {
  if (bucleVivo) return;
  const { bucle_generico: b } = await chrome.storage.local.get("bucle_generico");
  if (!b) return;
  await chrome.storage.local.remove("bucle_generico");
  let pestana;
  try {
    pestana = await chrome.tabs.get(b.tabId);
  } catch (error) {
    return;
  }
  const { trabajo } = b;
  const minutos = { ...TOPES_GENERICO, ...(trabajo.motor_generico || {}) }.max_minutos;
  if (b.envio || Date.now() - b.inicio > minutos * 60000) {
    await cerrarPestana(pestana);
    return;
  }
  let cerrar = true;
  try {
    const sel = await selectores(trabajo.origen || trabajo.plataforma);
    await guardarEstado({ trabajo_actual: { id: trabajo.id, titulo: trabajo.titulo, plataforma: trabajo.origen || trabajo.plataforma, inicio: b.inicio } });
    await reportar(trabajo.id, "retomar", "el navegador se reinició a mitad del formulario");
    const contexto = { trabajo, sel, cv: null, cv_nombre: null, inicio: b.inicio, envio: false, bucle: b.bucle };
    ensayoEnCurso = trabajo.ensayo ? { id: trabajo.id, pantalla: 0 } : null;
    cerrar = (await bucleGenerico(pestana.id, contexto)).cerrar !== false;
  } catch (error) {
    await terminar(trabajo.id, "fallida", { motivo: String(error.message || error).slice(0, 400) }).catch(() => {});
  } finally {
    ensayoEnCurso = null;
    await guardarEstado({ trabajo_actual: null });
    if (cerrar) await cerrarPestana(pestana);
  }
}

// Captcha o verificación: se muestra la pestaña y se espera a que el usuario la resuelva
async function esperarVerificacion(tabId, id, sel, plataforma) {
  const { sondeo_captcha_ms, verificacion_max_ms } = await opciones();
  await llamar("POST", `/postulaciones/${id}/verificacion`, { estado: "pendiente" }).catch(() => {});
  const tab = await chrome.tabs.update(tabId, { active: true });
  chrome.windows.update(tab.windowId, { state: "normal", focused: true }).catch(() => {});
  const limite = Date.now() + verificacion_max_ms;
  while (Date.now() < limite) {
    await new Promise((r) => setTimeout(r, sondeo_captcha_ms));
    try {
      await inyectar(tabId, plataforma);
      const estado = await enPestana(tabId, (s) => globalThis.__asistente.sesion(s), sel);
      if (!estado.captcha) {
        await llamar("POST", `/postulaciones/${id}/verificacion`, { estado: "resuelta" });
        return true;
      }
    } catch (error) {
      return false; // el usuario cerró la pestaña: el servidor decide por vencimiento
    }
  }
  await terminar(id, "bloqueada", { motivo: "la verificación no se resolvió en 2 horas" });
  return false;
}

async function reportar(id, paso, detalle = null) {
  try {
    await llamar("POST", `/postulaciones/${id}/paso`, { paso: String(paso).slice(0, 60),
      detalle: detalle == null ? null : String(detalle).slice(0, 2000) });
  } catch (error) {
    // el registro de pasos no detiene la postulación
  }
}

async function terminar(id, estado, { motivo = null, html = null, confirmacion = null } = {}) {
  if (ensayoEnCurso && ensayoEnCurso.id === id && !SIN_TRABA.includes(estado)) {
    // Ensayo que no llegó al botón: queda dicho en qué pantalla se trabaría
    const donde = ensayoEnCurso.pantalla ? `pantalla ${ensayoEnCurso.pantalla}` : "antes de la primera pantalla";
    await reportar(id, "ensayo_trabado", `${donde}: ${motivo || estado}`);
  }
  try {
    await llamar("POST", `/postulaciones/${id}/resultado`, { estado, motivo, html, confirmacion });
  } finally {
    await guardarEstado({ ultima: { id, estado, motivo, fin: Date.now() } });
  }
}

// --- vinculación automática y portales visitados por el usuario ------------------------------

chrome.tabs.onUpdated.addListener(async (tabId, cambio, tab) => {
  if (cambio.status !== "complete" || !tab.url) return;
  const { servidor, token } = await ajustes();
  if (tab.url.startsWith(`${servidor}/api/v1/vincular/`)) {
    await vincularDesdePagina(tabId);
    return;
  }
  // El usuario visitó un portal: si cambió la sesión, se revisa el portal y se avisa
  const plataforma = plataformaDeUrl(tab.url);
  if (!plataforma || !token || ocupado) return;
  const { estado = {} } = await chrome.storage.local.get("estado");
  if (estado.trabajo_actual) return;
  try {
    const sel = await selectores(plataforma);
    await inyectar(tabId, plataforma);
    const s = await enPestana(tabId, (ss) => globalThis.__asistente.sesion(ss), sel);
    const { portales = {} } = await chrome.storage.local.get("portales");
    const antes = portales[plataforma] ? portales[plataforma].estado !== "sin_sesion" : null;
    if (antes !== !s.sin_sesion) {
      await chrome.storage.local.set({ portales: { ...portales, [plataforma]: { ...(portales[plataforma] || {}), revisado: 0 } } });
      latido();
    }
  } catch (error) {
    // la pestaña se cerró o cambió de página
  }
});

async function vincularDesdePagina(tabId) {
  const leer = await enPestana(tabId, () => {
    const el = document.getElementById("asistente-vinculo");
    return el ? { codigo: el.dataset.codigo } : null;
  }).catch(() => null);
  if (!leer || !leer.codigo) return;
  let ok = false;
  let mensaje;
  try {
    await vincular(leer.codigo);
    ok = true;
    mensaje = "Navegador vinculado. Ya puedes cerrar esta pestaña y volver a Telegram.";
  } catch (error) {
    mensaje = error.estado === 400
      ? "El código venció o ya se usó. Pide uno nuevo en el bot con /vincular."
      : "No pude contactar al servidor. Intenta de nuevo en unos minutos.";
  }
  await enPestana(tabId, (texto, exito) => {
    const p = document.getElementById("estado");
    if (p) {
      p.textContent = texto;
      p.className = exito ? "ok" : "error";
    }
    document.body.dataset.vinculado = exito ? "si" : "no";
  }, mensaje, ok).catch(() => {});
  if (ok) {
    await chrome.storage.local.set({ portales: {} });
    latido({ forzarRevision: true });
  }
}

// --- iniciar sesión desde el popup --------------------------------------------------------

async function marcarVigilando(plataforma, activo) {
  const { vigilando = {} } = await chrome.storage.local.get("vigilando");
  if (activo) vigilando[plataforma] = Date.now();
  else delete vigilando[plataforma];
  await chrome.storage.local.set({ vigilando });
}

// Abre la página de ingreso del portal, espera a que el usuario inicie sesión (sondeando la
// pestaña cada 2 s) y la cierra sola en cuanto detecta la sesión; entonces relee ese portal y
// avisa al servidor, que es quien le pide al usuario confirmar la cuenta en el bot.
// El popup la lanza sin esperarla: sin token no abre nada y ningún error queda sin capturar.
async function vigilarInicioSesion(plataforma) {
  try {
    const { token } = await ajustes();
    if (!token) return;
    await vigilar(plataforma);
  } catch (error) {
    await guardarEstado({ error: String(error.message || error) }).catch(() => {});
  }
}

async function vigilar(plataforma) {
  const url = INGRESO[plataforma];
  if (!url) return;
  let tab;
  try {
    // Se crea en blanco y luego navega, igual que abrirPestana: así el navegador ya tiene la
    // pestaña lista para interceptar la navegación real (y las pruebas pueden servirla)
    tab = await crearPestana({ active: true });
    await navegar(tab.id, url);
  } catch (error) {
    if (tab) cerrarPestana(tab);
    return;
  }
  await marcarVigilando(plataforma, true);
  try {
    const sel = await selectores(plataforma);
    const { sondeo_sesion_ms, espera_sesion_max_ms } = await opciones();
    const limite = Date.now() + espera_sesion_max_ms;
    while (Date.now() < limite) {
      await new Promise((r) => setTimeout(r, sondeo_sesion_ms));
      let actual;
      try {
        actual = await chrome.tabs.get(tab.id);
      } catch (error) {
        return; // el usuario cerró la pestaña antes de iniciar sesión
      }
      if (actual.status !== "complete" || plataformaDeUrl(actual.url) !== plataforma) continue;
      let estado;
      try {
        await inyectar(tab.id, plataforma);
        estado = await enPestana(tab.id, (ss) => globalThis.__asistente.sesion(ss), sel);
      } catch (error) {
        continue; // la página está cargando o cambiando justo ahora
      }
      if (estado.sin_sesion) continue;
      await cerrarPestana(tab);
      // Se relee ya mismo ese portal (correo incluido): un segundo intento por si justo tras
      // cerrar la pestaña el navegador queda un instante ocupado y el primero sale en falso
      let resultado;
      for (let intento = 0; intento < 2; intento++) {
        if (intento) await new Promise((r) => setTimeout(r, 500));
        try {
          resultado = await revisarPortal(plataforma);
        } catch (error) {
          resultado = { estado: "sin_sesion", correo: null };
        }
        if (resultado.estado !== "sin_sesion") break;
      }
      const { portales = {} } = await chrome.storage.local.get("portales");
      const nuevo = { ...resultado, revisado: Date.now() };
      await anotarDuracion(nuevo, plataforma);
      await chrome.storage.local.set({ portales: { ...portales, [plataforma]: nuevo } });
      await latido({ forzarRevision: false });
      return;
    }
  } finally {
    await marcarVigilando(plataforma, false);
  }
}

// --- mensajes del popup y las opciones -------------------------------------------------------

chrome.runtime.onMessage.addListener((mensaje, _remitente, responder) => {
  (async () => {
    switch (mensaje && mensaje.tipo) {
      case "vincular":
        try {
          await vincular(mensaje.codigo);
          await chrome.storage.local.set({ portales: {} });
          latido({ forzarRevision: true });
          return { ok: true };
        } catch (error) {
          return { ok: false, estado: error.estado || 0 };
        }
      case "latido":
        return { ok: Boolean(await latido({ forzarRevision: Boolean(mensaje.revisar) })) };
      case "medirDuracion":
        return { ok: await medirDuracion(mensaje.plataforma) };
      case "iniciarSesion":
        vigilarInicioSesion(mensaje.plataforma); // se deja corriendo; no bloquea la respuesta
        return { ok: true };
      case "preferenciasLeer":
        try {
          return { ok: true, datos: await llamar("GET", `/preferencias/${mensaje.plataforma}`) };
        } catch (error) {
          return { ok: false };
        }
      case "preferenciasGuardar":
        try {
          await llamar("POST", `/preferencias/${mensaje.plataforma}`, mensaje.datos);
          return { ok: true };
        } catch (error) {
          return { ok: false };
        }
      case "nivelIaLeer":
        try {
          return { ok: true, datos: await llamar("GET", "/nivel_ia") };
        } catch (error) {
          return { ok: false };
        }
      case "nivelIaGuardar":
        try {
          await llamar("POST", "/nivel_ia", { nivel: mensaje.nivel });
          return { ok: true };
        } catch (error) {
          return { ok: false };
        }
      case "olvidarCuenta":
        try {
          await llamar("POST", `/cuenta/${mensaje.plataforma}/olvidar`);
          return { ok: true };
        } catch (error) {
          return { ok: false };
        }
      case "desvincular":
        await chrome.storage.local.set({ token: null, portales: {}, estado: {} });
        return { ok: true };
      default:
        return { ok: false };
    }
  })().then(responder);
  return true;
});

// Acceso para las pruebas automáticas (Playwright evalúa en el service worker)
globalThis.asistente = { latido, ejecutar, revisarPortal, estadoPortales, vigilarInicioSesion,
  retomarBucle, medirDuracion };
