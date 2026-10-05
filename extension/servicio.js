// Service worker: latido con el servidor, vinculación y ejecución de la cola del usuario.
// Coordina el flujo entre páginas; cada paso lo ejecuta motor.js dentro de la pestaña.

import { ajustes, llamar, version, vincular, ErrorApi } from "./api.js";
import { ADAPTADORES, paginaPermitida, plataformaDeUrl, tienePermiso } from "./portales.js";

const ALARMA = "latido";
const REVISION_MAX_MS = 6 * 60 * 60 * 1000; // estado de los portales: se revisa cada 6 h
const CARGA_MS = 45000;
const PREDETERMINADOS = { sondeo_captcha_ms: 10000, verificacion_max_ms: 2 * 60 * 60 * 1000 };

let ocupado = false;
let enCurso = null; // latido en curso: quien llama mientras tanto recibe el mismo

// --- arranque y alarma ----------------------------------------------------------------------

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

function latido(opciones = {}) {
  if (!enCurso) enCurso = latidoUnico(opciones).finally(() => (enCurso = null));
  return enCurso;
}

async function latidoUnico({ forzarRevision = false } = {}) {
  const { token, pausado } = await ajustes();
  if (!token) return null;
  ocupado = true;
  try {
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
  const cuerpo = { version: version(), portales: {} };
  for (const [plataforma, p] of Object.entries(portales)) {
    cuerpo.portales[plataforma] = { estado: p.estado, correo: p.correo || null,
      pagina_correo: p.pagina_correo || null };
  }
  try {
    const r = await llamar("POST", "/latido", cuerpo);
    await chrome.storage.local.set({ selectores_version: r.selectores || {} });
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
    const vencido = !previo || Date.now() - previo.revisado > REVISION_MAX_MS;
    if (soloPlataforma ? plataforma === soloPlataforma : forzar || vencido) {
      try {
        portales[plataforma] = { ...(await revisarPortal(plataforma)), revisado: Date.now() };
      } catch (error) {
        if (!previo) portales[plataforma] = { estado: "sin_sesion", revisado: Date.now() };
      }
    }
  }
  await chrome.storage.local.set({ portales });
  return portales;
}

// Revisa el portal en una ventana minimizada: primero la sesión en la página principal (donde
// el botón "Ingresar" delata que no hay sesión) y luego el correo de la cuenta, en las páginas
// de cuenta conocidas o siguiendo los enlaces "Mi cuenta", "Mi perfil"… del propio portal.
const MAX_PAGINAS_CORREO = 5;

async function revisarPortal(plataforma) {
  const sel = await selectores(plataforma);
  const sesion = sel.sesion || {};
  const cuenta = sel.cuenta || {};
  const inicio = sesion.url || cuenta.url || (cuenta.urls || [])[0];
  if (!inicio) throw new Error(`sin página para revisar ${plataforma}`);
  const pestana = await abrirPestana(inicio);
  try {
    let tab = await chrome.tabs.get(pestana.id);
    if (plataformaDeUrl(tab.url) !== plataforma) return { estado: "sin_sesion", correo: null };
    await inyectar(pestana.id, plataforma);
    const s = await enPestana(
      pestana.id, (ss) => globalThis.__asistente.revisar(ss, { secciones: false }), sel,
    );
    if (s.estado === "sin_sesion") return { estado: "sin_sesion", correo: null };
    let correo = s.correo;
    let origen = correo ? tab.url : null;
    const pendientes = [...(cuenta.urls || (cuenta.url ? [cuenta.url] : []))];
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
      const r = await enPestana(pestana.id, (ss) => globalThis.__asistente.buscarCorreo(ss), sel);
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
    return { estado: "listo", correo: correo || null, pagina_correo };
  } finally {
    cerrarPestana(pestana);
  }
}

// --- pestañas -----------------------------------------------------------------------------

// Pestaña en segundo plano: se crea vacía y luego navega, así la carga es igual a cualquier
// navegación posterior (y las pruebas pueden servir las páginas del portal)
// Se abre en una ventana minimizada aparte para no mover las pestañas del usuario; si el
// portal pide una verificación, esa ventana se muestra (ver esperarVerificacion).
async function abrirPestana(url) {
  let pestana;
  try {
    const ventana = await chrome.windows.create({
      url: "about:blank", focused: false, state: "minimized",
    });
    pestana = ventana.tabs[0];
  } catch (error) {
    pestana = await chrome.tabs.create({ url: "about:blank", active: false });
  }
  try {
    await navegar(pestana.id, url);
  } catch (error) {
    cerrarPestana(pestana);
    throw error;
  }
  return pestana;
}

function cerrarPestana(pestana) {
  chrome.tabs.remove(pestana.id).catch(() => {});
}

async function navegar(tabId, url) {
  const carga = esperarCargaNueva(tabId);
  await chrome.tabs.update(tabId, { url });
  await carga;
}

// Espera una navegación que empieza después de llamar a esta función
function esperarCargaNueva(tabId, ms = CARGA_MS) {
  return new Promise((resolver, rechazar) => {
    let cargando = false;
    const fin = setTimeout(() => {
      chrome.tabs.onUpdated.removeListener(oyente);
      rechazar(new Error("la página no cargó"));
    }, ms);
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
  if (!pasos.length || !url) {
    await terminar(id, "formulario_desconocido", { motivo: `sin flujo de ${tipo} para ${plataforma}` });
    return;
  }
  let pestana;
  try {
    pestana = await abrirPestana(url);
  } catch (error) {
    await terminar(id, "fallida", { motivo: "la página de la vacante no cargó" });
    return;
  }
  let cerrar = true;
  const contexto = { trabajo, sel, cv: null, cv_nombre: null };
  try {
    await reportar(id, "abrir", trabajo.titulo || url);
    for (let i = 0; i < pasos.length; i++) {
      const paso = pasos[i];
      const tab = await chrome.tabs.get(pestana.id);
      if (!paginaPermitida(tab.url, plataforma)) {
        // Fuera del portal o en una página prohibida: el motor se niega a operar
        await terminar(id, "formulario_desconocido", { motivo: `página no permitida: ${new URL(tab.url).host}${new URL(tab.url).pathname}` });
        return;
      }
      await inyectar(pestana.id, plataforma);
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
    await guardarEstado({ trabajo_actual: null });
    if (cerrar) cerrarPestana(pestana);
  }
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
  if (paso.accion === "enviar" || paso.envia) {
    // El servidor registra envio_pulsado antes del clic: si el navegador se cierra justo
    // después, la postulación queda "incierta" y nunca se envía dos veces.
    await llamar("POST", `/postulaciones/${id}/envio`);
  }
  await reportar(id, paso.nombre || paso.accion);

  const navega = paso.navega ? esperarCargaNueva(tabId).catch(() => {}) : null;
  let r = await correr(paso);
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
  if (r.error) {
    await terminar(id, r.error, { motivo: r.motivo, html: r.html });
    return { fin: true };
  }
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
  if (r.campos) {
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

async function formulario(tabId, contexto, campos) {
  const { trabajo } = contexto;
  const r = await llamar("POST", `/postulaciones/${trabajo.id}/formulario`, { campos });
  if (r.esperar_usuario) {
    // El bot le pregunta al usuario lo que falta; la postulación vuelve a la cola al responder
    await reportar(trabajo.id, "esperando_usuario", "faltan datos que solo tú sabes");
    return { fin: true };
  }
  if (r.cv_url && campos.some((c) => c.tipo === "archivo")) await descargarCv(contexto, r);
  await enPestana(
    tabId,
    (pp, s, dd) => globalThis.__asistente.paso(pp, s, dd),
    { accion: "llenar" },
    contexto.sel,
    { plataforma: trabajo.plataforma, respuestas: r.respuestas, cv: contexto.cv },
  );
  await reportar(trabajo.id, "llenado", `${r.respuestas.length} respuestas`);
  return {};
}

async function obtenerCv(contexto, campos) {
  const r = await llamar("POST", `/postulaciones/${contexto.trabajo.id}/formulario`, { campos });
  if (r.cv_url) await descargarCv(contexto, r);
}

async function descargarCv(contexto, r) {
  const bytes = new Uint8Array(await llamar("GET", r.cv_url, undefined, { binario: true }));
  let binario = "";
  for (let i = 0; i < bytes.length; i += 0x8000) {
    binario += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  }
  contexto.cv = { base64: btoa(binario), nombre: r.cv_nombre || "CV.pdf" };
  contexto.cv_nombre = contexto.cv.nombre;
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
    mensaje = "✅ Navegador vinculado. Ya puedes cerrar esta pestaña y volver a Telegram.";
  } catch (error) {
    mensaje = error.estado === 400
      ? "❌ El código venció o ya se usó. Pide uno nuevo en el bot con /vincular."
      : "❌ No pude contactar al servidor. Intenta de nuevo en unos minutos.";
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
globalThis.asistente = { latido, ejecutar, revisarPortal, estadoPortales };
