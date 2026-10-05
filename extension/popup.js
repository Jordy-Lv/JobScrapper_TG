import { ajustes } from "./api.js";
import { INICIO, NOMBRES, origenes, tienePermiso } from "./portales.js";

const RESULTADOS = {
  enviada: "✅ Enviada", ya_postulada: "Ya estabas postulado", vacante_cerrada: "Vacante cerrada",
  esperando_sesion: "Faltaba iniciar sesión", formulario_desconocido: "Formulario desconocido",
  incierta: "Sin confirmación", fallida: "Falló", bloqueada: "Verificación sin resolver",
  completado: "Perfil completado", cuenta_distinta: "Otra cuenta abierta",
};

// Subtítulo de las plataformas que aún no habilita el servidor
const DESCRIPCION = {
  computrabajo: "Bolsa de empleo",
  magneto: "Empleo en Colombia",
  elempleo: "Ofertas en Colombia",
  getonboard: "Startups y empleo remoto",
  linkedin: "Solicitud sencilla",
  spe: "Portal oficial de Colombia",
};

const $ = (id) => document.getElementById(id);
const SVG = "http://www.w3.org/2000/svg";

function hace(ms) {
  const min = Math.round((Date.now() - ms) / 60000);
  return min < 1 ? "hace un momento" : min < 60 ? `hace ${min} min` : `hace ${Math.round(min / 60)} h`;
}

function el(etiqueta, clase, texto) {
  const nodo = document.createElement(etiqueta);
  if (clase) nodo.className = clase;
  if (texto != null) nodo.textContent = texto;
  return nodo;
}

function iconoAbrir() {
  const svg = document.createElementNS(SVG, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  for (const d of ["M14 4h6v6", "M20 4l-9 9", "M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"]) {
    const ruta = document.createElementNS(SVG, "path");
    ruta.setAttribute("d", d);
    svg.append(ruta);
  }
  return svg;
}

function accion(texto, alHacer) {
  const b = el("button", "accion", texto);
  b.type = "button";
  b.addEventListener("click", alHacer);
  return b;
}

// Una tarjeta por plataforma: logo, estado y la acción que corresponda
async function tarjeta(p, { habilitada, vinculado, info, cuentaOk, vigilando }) {
  const li = el("li", `tarjeta ${p}`);
  const logo = el("div", "logo");
  const img = el("img");
  img.src = `logos/${p}.png`;
  img.alt = "";
  logo.append(img);

  const cuerpo = el("div", "cuerpo");
  const fila = el("div", "fila");
  fila.append(el("span", "nombre", NOMBRES[p]));
  const sub = el("div", "sub");

  let pill;
  if (!habilitada) {
    li.classList.add("apagada");
    pill = el("span", "pill pronto", "Próximamente");
    sub.textContent = DESCRIPCION[p];
  } else if (!(await tienePermiso(p))) {
    pill = el("span", "pill activar", "Sin activar");
    sub.append(accion("Activar ↗", async () => {
      if (await chrome.permissions.request({ origins: origenes(p) })) {
        await chrome.runtime.sendMessage({ tipo: "latido", revisar: true });
      }
      pintar();
    }));
  } else if (vigilando) {
    pill = el("span", "pill pendiente", "Iniciando sesión…");
    sub.textContent = "Esperando que termines de iniciar sesión en la pestaña abierta";
  } else if (vinculado && info && info.estado !== "sin_sesion") {
    // La cuenta queda "confirmada" solo cuando el servidor lo dice explícitamente: ni sin
    // respuesta todavía ni tras cancelar en el bot se debe mostrar como lista
    const confirmada = cuentaOk === true;
    if (!info.correo) {
      pill = el("span", "pill pendiente", "Buscando correo");
      sub.textContent = "Sesión iniciada · buscando tu correo";
    } else if (!confirmada) {
      pill = el("span", "pill pendiente", "Confírmala");
      sub.textContent = "Esperando confirmación en el bot de Telegram";
      sub.title = `Confirma en el bot que ${info.correo} es tuya`;
    } else if (info.estado === "incompleto") {
      pill = el("span", "pill pendiente", "Perfil incompleto");
      sub.textContent = info.correo;
    } else {
      pill = el("span", "pill listo", "Listo ✓");
      sub.textContent = info.correo;
    }
  } else {
    // Sin sesión: un toque abre la página de ingreso y espera a que el usuario inicie sesión
    pill = vinculado ? el("span", "pill pendiente", info ? "Sin sesión" : "Revisando") : null;
    sub.append(accion("Iniciar sesión ↗", async (evento) => {
      evento.target.disabled = true;
      await chrome.runtime.sendMessage({ tipo: "iniciarSesion", plataforma: p });
    }));
  }
  if (pill) fila.append(pill);
  cuerpo.append(fila, sub);

  const abrir = el("button", "abrir");
  abrir.type = "button";
  abrir.title = `Abrir ${NOMBRES[p]}`;
  abrir.setAttribute("aria-label", abrir.title);
  abrir.append(iconoAbrir());
  abrir.addEventListener("click", () => chrome.tabs.create({ url: INICIO[p] }));

  li.append(logo, cuerpo, abrir);
  return li;
}

async function pintar() {
  const { token, pausado } = await ajustes();
  const { estado = {}, portales = {}, selectores_version = {}, vigilando = {} } =
    await chrome.storage.local.get(["estado", "portales", "selectores_version", "vigilando"]);
  const vinculado = Boolean(token);
  const conVersiones = Object.keys(selectores_version).length > 0;

  const tarjetas = [];
  for (const p of Object.keys(NOMBRES)) {
    const habilitada = conVersiones ? p in selectores_version : p === "computrabajo" || p === "magneto";
    tarjetas.push(await tarjeta(p, {
      habilitada, vinculado, info: portales[p], cuentaOk: (estado.cuentas || {})[p],
      vigilando: Boolean(vigilando[p]),
    }));
  }
  $("portales").replaceChildren(...tarjetas);

  $("sin-vincular").hidden = vinculado;
  $("revisar").hidden = !vinculado;
  $("pausar").hidden = !vinculado;
  const linea = $("linea");
  const enPausa = vinculado && Boolean(estado.en_linea) && Boolean(pausado);
  linea.classList.toggle("en-linea", vinculado && Boolean(estado.en_linea) && !enPausa);
  linea.classList.toggle("pausa", enPausa);
  linea.classList.toggle("caido", vinculado && !estado.en_linea);
  $("linea-texto").textContent = !vinculado ? "Sin vincular"
    : estado.en_linea ? `Conectado · ${hace(estado.ultimo_latido)}`
    : "Sin conexión con el servidor";
  if (vinculado && estado.en_linea && pausado) $("linea-texto").textContent = "En pausa";

  const boton = $("pausar");
  boton.classList.toggle("pausado", Boolean(pausado));
  boton.title = pausado ? "Reanudar las postulaciones" : "Pausar las postulaciones";
  boton.setAttribute("aria-label", boton.title);

  const actual = estado.trabajo_actual;
  $("actual").hidden = !actual;
  $("actual").textContent = actual
    ? `⏳ Postulando: ${actual.titulo || NOMBRES[actual.plataforma]}` : "";
  $("actualizar").hidden = !estado.actualizar;
  $("ultima").textContent = vinculado && estado.ultima
    ? `Última: ${RESULTADOS[estado.ultima.estado] || estado.ultima.estado} · ${hace(estado.ultima.fin)}`
    : "";
}

$("form-codigo").addEventListener("submit", async (evento) => {
  evento.preventDefault();
  $("mensaje-codigo").textContent = "Vinculando…";
  const r = await chrome.runtime.sendMessage({ tipo: "vincular", codigo: $("codigo").value });
  $("mensaje-codigo").textContent = r.ok ? "✅ Navegador vinculado"
    : r.estado === 400 ? "Código vencido o ya usado. Pide otro con /vincular."
    : "No pude contactar al servidor.";
  pintar();
});

$("revisar").addEventListener("click", async () => {
  // La revisión abre cada portal en una pestaña de fondo y tarda unos segundos
  $("revisar").disabled = true;
  $("revisar").textContent = "Revisando…";
  await chrome.runtime.sendMessage({ tipo: "latido", revisar: true });
  $("revisar").disabled = false;
  $("revisar").textContent = "Revisar";
  pintar();
});

$("pausar").addEventListener("click", async () => {
  const { pausado } = await ajustes();
  await chrome.storage.local.set({ pausado: !pausado });
  pintar();
});

// Botón de chat: accesos al bot y al grupo de Telegram (los enlaces los da el servidor)
const ENLACES_DEFECTO = { bot: "https://t.me/PostuladorJobs_Bot", grupo: null };

async function enlaces() {
  const { enlaces: guardados = {} } = await chrome.storage.local.get("enlaces");
  return { ...ENLACES_DEFECTO, ...Object.fromEntries(Object.entries(guardados).filter(([, v]) => v)) };
}

function alternarPanel(abrir) {
  const panel = $("panel-chat");
  const mostrar = abrir ?? panel.hidden;
  panel.hidden = !mostrar;
  $("boton-chat").setAttribute("aria-expanded", String(mostrar));
}

$("boton-chat").addEventListener("click", async () => {
  $("ir-grupo").hidden = !(await enlaces()).grupo;
  alternarPanel(true);
});
$("cerrar-chat").addEventListener("click", () => alternarPanel(false));
document.querySelector(".fondo-chat").addEventListener("click", () => alternarPanel(false));
$("ir-bot").addEventListener("click", async () => chrome.tabs.create({ url: (await enlaces()).bot }));
$("ir-grupo").addEventListener("click", async () => chrome.tabs.create({ url: (await enlaces()).grupo }));
document.addEventListener("keydown", (evento) => {
  if (evento.key === "Escape") alternarPanel(false);
});

chrome.storage.onChanged.addListener(pintar);
pintar();
