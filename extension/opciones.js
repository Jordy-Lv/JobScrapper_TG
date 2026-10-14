import { ajustes } from "./api.js";
import { SERVIDOR_DEFECTO } from "./portales.js";

const $ = (id) => document.getElementById(id);

async function pintar() {
  const { servidor, token, nombre } = await ajustes();
  $("servidor").value = servidor;
  $("vinculo").textContent = token ? `Vinculado como «${nombre || "este navegador"}».` : "Sin vincular.";
  $("desvincular").hidden = !token;
}

async function guardar(url) {
  const limpio = url.replace(/\/+$/, "");
  const origen = new URL(limpio).origin + "/*";
  // Un servidor distinto al de fábrica necesita el permiso explícito del usuario
  const permitido = (await chrome.permissions.contains({ origins: [origen] }))
    || (await chrome.permissions.request({ origins: [origen] }));
  if (!permitido) {
    $("mensaje").textContent = "Sin permiso para ese servidor.";
    return;
  }
  await chrome.storage.local.set({ servidor: limpio, token: null, portales: {} });
  $("mensaje").textContent = "Guardado. Vuelve a vincular el navegador desde el bot.";
  pintar();
}

$("form-servidor").addEventListener("submit", (e) => {
  e.preventDefault();
  guardar($("servidor").value).catch(() => ($("mensaje").textContent = "Dirección no válida."));
});
$("restaurar").addEventListener("click", () => guardar(SERVIDOR_DEFECTO));
$("desvincular").addEventListener("click", async () => {
  await chrome.runtime.sendMessage({ tipo: "desvincular" });
  pintar();
});
pintar();
