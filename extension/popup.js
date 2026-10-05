import { ajustes } from "./api.js";
import { NOMBRES, origenes, tienePermiso } from "./portales.js";

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

async function pintar() {
  const { token, pausado } = await ajustes();
  const { estado = {}, portales = {}, selectores_version = {} } =
    await chrome.storage.local.get(["estado", "portales", "selectores_version"]);
  $("sin-vincular").hidden = Boolean(token);
  $("vinculado").hidden = !token;
  if (!token) return;
  $("linea").textContent = estado.en_linea
    ? `🟢 Conectado al servidor · ${hace(estado.ultimo_latido)}`
    : `🔴 Sin conexión con el servidor${estado.error ? ` (${estado.error})` : ""}`;
  const habilitadas = Object.keys(selectores_version).length
    ? Object.keys(selectores_version) : ["computrabajo", "magneto"];
  const filas = [];
  for (const p of habilitadas) {
    const li = document.createElement("li");
    if (!(await tienePermiso(p))) {
      // Plataforma nueva habilitada en el servidor: el usuario da el permiso con un toque
      li.append(`${NOMBRES[p] || p}: `);
      const boton = document.createElement("button");
      boton.type = "button";
      boton.className = "enlace";
      boton.textContent = "Activar";
      boton.addEventListener("click", async () => {
        if (await chrome.permissions.request({ origins: origenes(p) })) {
          await chrome.runtime.sendMessage({ tipo: "latido", revisar: true });
        }
        pintar();
      });
      li.append(boton);
      filas.push(li);
      continue;
    }
    const info = portales[p];
    const cuentaOk = estado.cuentas ? estado.cuentas[p] : undefined;
    let texto = `${NOMBRES[p] || p}: ${info ? ESTADOS[info.estado] || info.estado : "sin revisar"}`;
    if (info && info.correo) texto += ` · ${info.correo}`;
    if (info && info.estado !== "sin_sesion" && cuentaOk === false) texto += " (confírmala en el bot)";
    li.textContent = texto;
    filas.push(li);
  }
  $("portales").replaceChildren(...filas);
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
