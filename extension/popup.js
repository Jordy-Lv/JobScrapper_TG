import { ajustes } from "./api.js";
import { INGRESO, NOMBRES, origenes, tienePermiso } from "./portales.js";

const ESTADOS = { listo: "listo ✅", incompleto: "perfil incompleto", sin_sesion: "sin sesión" };
const RESULTADOS = {
  enviada: "✅ enviada", ya_postulada: "ya estabas postulado", vacante_cerrada: "vacante cerrada",
  esperando_sesion: "falta iniciar sesión", formulario_desconocido: "formulario desconocido",
  incierta: "sin confirmación", fallida: "falló", bloqueada: "verificación sin resolver",
  completado: "perfil completado", cuenta_distinta: "otra cuenta abierta",
};

const $ = (id) => document.getElementById(id);

function hace(ms) {
  const min = Math.round((Date.now() - ms) / 60000);
  return min < 1 ? "hace un momento" : min < 60 ? `hace ${min} min` : `hace ${Math.round(min / 60)} h`;
}

function nota(texto) {
  const span = document.createElement("span");
  span.className = "nota";
  span.textContent = texto;
  return span;
}

function boton(texto, accion) {
  const b = document.createElement("button");
  b.type = "button";
  b.className = "enlace";
  b.textContent = texto;
  b.addEventListener("click", accion);
  return b;
}

async function pintarPortales(estado, portales, selectores_version, vinculado) {
  // Todas las plataformas: las que el servidor habilitó muestran su estado y su acción
  const filas = [];
  for (const p of Object.keys(NOMBRES)) {
    const habilitada = p in selectores_version || (!Object.keys(selectores_version).length
      && (p === "computrabajo" || p === "magneto"));
    const info = portales[p];
    const li = document.createElement("li");
    const nombre = document.createElement("b");
    nombre.textContent = NOMBRES[p];
    li.append(nombre, " ");
    if (!habilitada) {
      li.append(nota("próximamente"));
    } else if (!(await tienePermiso(p))) {
      li.append(nota("sin activar "), boton("Activar", async () => {
        if (await chrome.permissions.request({ origins: origenes(p) })) {
          await chrome.runtime.sendMessage({ tipo: "latido", revisar: true });
        }
        pintar();
      }));
    } else if (!vinculado || !info || info.estado === "sin_sesion") {
      li.append(nota(vinculado ? (info ? "sin sesión " : "sin revisar ") : ""), boton("Iniciar sesión", () => {
        chrome.tabs.create({ url: INGRESO[p] });
      }));
    } else {
      let texto = ESTADOS[info.estado] || info.estado;
      if (info.correo) texto += ` · ${info.correo}`;
      const cuentaOk = estado.cuentas ? estado.cuentas[p] : undefined;
      if (cuentaOk === false) texto += " (confírmala en el bot)";
      li.append(texto);
    }
    filas.push(li);
  }
  $("portales").replaceChildren(...filas);
}

async function pintar() {
  const { token, pausado } = await ajustes();
  const { estado = {}, portales = {}, selectores_version = {} } =
    await chrome.storage.local.get(["estado", "portales", "selectores_version"]);
  $("sin-vincular").hidden = Boolean(token);
  $("vinculado").hidden = !token;
  await pintarPortales(estado, portales, selectores_version, Boolean(token));
  if (!token) return;
  $("linea").textContent = estado.en_linea
    ? `🟢 Conectado al servidor · ${hace(estado.ultimo_latido)}`
    : `🔴 Sin conexión con el servidor${estado.error ? ` (${estado.error})` : ""}`;
  $("actual").textContent = estado.trabajo_actual
    ? `⏳ Postulando: ${estado.trabajo_actual.titulo || NOMBRES[estado.trabajo_actual.plataforma]}` : "";
  $("ultima").textContent = estado.ultima
    ? `Última: ${RESULTADOS[estado.ultima.estado] || estado.ultima.estado} · ${hace(estado.ultima.fin)}` : "";
  $("actualizar").hidden = !estado.actualizar;
  $("pausar").textContent = pausado ? "▶️ Reanudar" : "⏸️ Pausar";
}

$("form-codigo").addEventListener("submit", async (evento) => {
  evento.preventDefault();
  $("mensaje-codigo").textContent = "Vinculando…";
  const r = await chrome.runtime.sendMessage({ tipo: "vincular", codigo: $("codigo").value });
  $("mensaje-codigo").textContent = r.ok ? "✅ Navegador vinculado"
    : r.estado === 400 ? "❌ Código vencido o ya usado. Pide otro con /vincular."
    : "❌ No pude contactar al servidor.";
  pintar();
});

$("revisar").addEventListener("click", async () => {
  $("revisar").disabled = true;
  await chrome.runtime.sendMessage({ tipo: "latido", revisar: true });
  $("revisar").disabled = false;
  pintar();
});

$("pausar").addEventListener("click", async () => {
  const { pausado } = await ajustes();
  await chrome.storage.local.set({ pausado: !pausado });
  pintar();
});

chrome.storage.onChanged.addListener(pintar);
pintar();
