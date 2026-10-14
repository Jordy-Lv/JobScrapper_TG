// Motor de pasos declarativos. Se inyecta en la pestaña del portal y ejecuta UN paso por
// llamada; el service worker coordina el flujo entre páginas. No ejecuta código remoto: los
// pasos y selectores del servidor son datos que este archivo interpreta.

(() => {
  if (globalThis.__asistente) return; // ya inyectado en esta página

  const adaptadores = {};
  let campos = []; // campos leídos por el último paso "formulario" en esta página

  const dormir = (ms) => new Promise((r) => setTimeout(r, ms));
  const pausa = (min = 150, max = 450) => dormir(min + Math.random() * (max - min));

  function normalizar(texto) {
    return String(texto || "")
      .normalize("NFD")
      .replace(/[̀-ͯ]/g, "")
      .toLowerCase()
      .replace(/\s+/g, " ")
      .trim();
  }

  function visible(el) {
    if (!el || !el.isConnected) return false;
    if (el.closest("[hidden], .hide, [aria-hidden='true']")) return false;
    const estilo = getComputedStyle(el);
    if (estilo.display === "none" || estilo.visibility === "hidden") return false;
    return el.getClientRects().length > 0;
  }

  // Un <input> no tiene textContent: su texto visible (botones, submit) va en el atributo value
  function textoVisible(el) {
    if (!el) return "";
    if (el.tagName === "INPUT" && el.value) return el.value;
    return el.textContent || "";
  }

  // Un selector es un string CSS o {css, texto} (el texto debe estar contenido, sin tildes)
  function candidatos(selector, raiz = document) {
    const def = typeof selector === "string" ? { css: selector } : selector;
    let lista;
    try {
      lista = [...raiz.querySelectorAll(def.css)];
    } catch {
      return [];
    }
    if (def.texto) {
      const buscado = normalizar(def.texto);
      lista = lista.filter((el) => normalizar(textoVisible(el)).includes(buscado));
    }
    return lista;
  }

  function buscar(selectores, { raiz = document, ocultos = false } = {}) {
    for (const selector of [].concat(selectores || [])) {
      const el = candidatos(selector, raiz).find((x) => ocultos || visible(x));
      if (el) return el;
    }
    return null;
  }

  async function esperar(selectores, ms = 10000, opciones = {}) {
    const limite = Date.now() + ms;
    do {
      const el = buscar(selectores, opciones);
      if (el) return el;
      await dormir(250);
    } while (Date.now() < limite);
    return null;
  }

  function textoPagina() {
    return normalizar(document.body ? document.body.innerText : "");
  }

  function hayTexto(textos) {
    const pagina = textoPagina();
    return [].concat(textos || []).some((t) => pagina.includes(normalizar(t)));
  }

  function textos(sel, clave) {
    return (sel.textos && sel.textos[clave]) || [];
  }

  function hayCaptcha(sel) {
    return Boolean(buscar(sel.captcha || [])) || hayTexto(textos(sel, "verificacion"));
  }

  function sinSesion(sel) {
    const s = sel.sesion || {};
    if ((s.url_sin_sesion || []).some((p) => location.href.includes(p))) return true;
    return Boolean(buscar(s.sin_sesion || []));
  }

  // HTML del formulario (o la página) sin los valores escritos: evidencia para el dueño
  function htmlSinValores(raiz) {
    const copia = (raiz || document.documentElement).cloneNode(true);
    copia.querySelectorAll("script, style, noscript, svg, img, iframe").forEach((n) => n.remove());
    // Sin la cabecera, el menú ni el recuadro de la cuenta: ahí están el nombre y el correo
    copia.querySelectorAll("header, nav, footer, [data-info-user], .header_popup, [class*='user' i]")
      .forEach((n) => n.remove());
    copia.querySelectorAll("input").forEach((n) => {
      n.removeAttribute("value");
      n.removeAttribute("checked");
    });
    copia.querySelectorAll("textarea").forEach((n) => (n.textContent = ""));
    copia.querySelectorAll("option").forEach((n) => n.removeAttribute("selected"));
    copia.querySelectorAll("[data-value]").forEach((n) => n.removeAttribute("data-value"));
    return copia.outerHTML.slice(0, 300 * 1024);
  }

  // --- lectura de campos -----------------------------------------------------------------

  function textoDe(el) {
    return el ? textoVisible(el).replace(/\s+/g, " ").trim() : "";
  }

  function etiqueta(el) {
    if (el.id) {
      const lab = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
      if (lab && textoDe(lab)) return textoDe(lab);
    }
    const envolvente = el.closest("label");
    if (envolvente && textoDe(envolvente)) return textoDe(envolvente);
    if (el.getAttribute("aria-label")) return el.getAttribute("aria-label").trim();
    const ids = el.getAttribute("aria-labelledby");
    if (ids) {
      const t = ids.split(/\s+/).map((i) => textoDe(document.getElementById(i))).join(" ").trim();
      if (t) return t;
    }
    // Texto del bloque contenedor más cercano que tenga una etiqueta o un título
    let nodo = el.parentElement;
    for (let i = 0; nodo && i < 4; i++, nodo = nodo.parentElement) {
      const titulo = nodo.querySelector("label, legend, h3, h4, p, span.label, .label");
      if (titulo && !titulo.contains(el) && textoDe(titulo)) return textoDe(titulo);
    }
    return el.getAttribute("placeholder") || el.name || "";
  }

  function tipoDe(el) {
    const t = (el.getAttribute("type") || "").toLowerCase();
    if (el.tagName === "SELECT") return "opciones";
    if (el.tagName === "TEXTAREA") return "texto";
    if (t === "file") return "archivo";
    if (t === "email") return "correo";
    if (t === "tel") return "telefono";
    if (t === "number") return "numero";
    if (t === "date") return "fecha";
    if (t === "radio" || t === "checkbox") return "opciones";
    return "texto";
  }

  // Además del atributo HTML, los portales marcan lo obligatorio con la validación de jQuery
  // (Computrabajo: data-rule-required y data-val-requiredif en las preguntas de selección)
  function requerido(el) {
    return el.required || el.getAttribute("aria-required") === "true"
      || el.getAttribute("data-rule-required") === "true"
      || el.hasAttribute("data-val-required") || el.hasAttribute("data-val-requiredif");
  }

  function obligatoria(el) {
    if (requerido(el)) return true;
    const lab = etiqueta(el);
    return /\*\s*$/.test(lab);
  }

  // Texto de la pregunta de un grupo de radios o casillas: el título más cercano que no sea
  // la etiqueta de una de sus opciones (en Computrabajo está fuera del contenedor de opciones)
  function leyendaDeGrupo(elementos) {
    const ids = new Set(elementos.map((x) => x.id).filter(Boolean));
    const deOpcion = (t) => elementos.some((x) => t.contains(x)) || ids.has(t.getAttribute("for"));
    let nodo = elementos[0].parentElement;
    for (let i = 0; nodo && i < 4; i++, nodo = nodo.parentElement) {
      const titulo = [...nodo.querySelectorAll("legend, label, p, h3, h4, .label")]
        .find((t) => !deOpcion(t) && textoDe(t));
      if (titulo) return textoDe(titulo);
    }
    return "";
  }

  function leerCampos(contenedor) {
    const leidos = [];
    const grupos = new Map(); // radios y casillas agrupados por name
    const elementos = contenedor.querySelectorAll("input, select, textarea");
    for (const el of elementos) {
      const t = (el.getAttribute("type") || "").toLowerCase();
      if (["hidden", "submit", "button", "reset", "image", "password"].includes(t)) continue;
      if (el.disabled || el.readOnly) continue;
      if (t !== "file" && !visible(el) && !(t === "radio" || t === "checkbox")) continue;
      if (t === "radio" || (t === "checkbox" && el.name)) {
        const clave = `${t}:${el.name || el.id}`;
        if (!grupos.has(clave)) {
          const grupo = { tipo: t, elementos: [], nombre: el.name };
          grupos.set(clave, grupo);
          leidos.push(grupo);
        }
        grupos.get(clave).elementos.push(el);
        continue;
      }
      leidos.push({ el });
    }
    campos = [];
    const salida = [];
    for (const item of leidos) {
      if (item.elementos) {
        const primero = item.elementos[0];
        const opciones = item.elementos.map((x) => etiqueta(x));
        if (item.elementos.length === 1 && item.tipo === "checkbox") {
          campos.push({ tipo: "casilla", el: primero });
          salida.push({ texto: etiqueta(primero), tipo: "opciones", opciones: ["Sí", "No"],
            obligatoria: requerido(primero), nombre: primero.name || null });
          continue;
        }
        campos.push({ tipo: item.tipo, elementos: item.elementos });
        salida.push({
          texto: leyendaDeGrupo(item.elementos) || item.nombre || "",
          tipo: "opciones",
          opciones,
          obligatoria: item.elementos.some(requerido),
          nombre: item.nombre || null,
        });
        continue;
      }
      const el = item.el;
      const t = (el.getAttribute("type") || "").toLowerCase();
      if (t === "checkbox") {
        campos.push({ tipo: "casilla", el });
        salida.push({ texto: etiqueta(el), tipo: "opciones", opciones: ["Sí", "No"],
          obligatoria: requerido(el), nombre: el.name || null });
        continue;
      }
      let opciones = [];
      let indices = [];
      if (el.tagName === "SELECT") {
        [...el.options].forEach((o, i) => {
          if (o.value === "" || o.disabled) return; // marcador "Selecciona…"
          opciones.push(o.textContent.trim());
          indices.push(i);
        });
      }
      campos.push({ tipo: el.tagName === "SELECT" ? "select" : tipoDe(el), el, indices });
      salida.push({
        texto: etiqueta(el).slice(0, 1000),
        tipo: tipoDe(el),
        opciones: opciones.slice(0, 100),
        obligatoria: obligatoria(el),
        nombre: el.name || el.id || null,
      });
    }
    return salida.slice(0, 80);
  }

  // --- llenado con eventos nativos ---------------------------------------------------------

  function asignarValor(el, valor) {
    const proto = el.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype
      : el.tagName === "SELECT" ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto, "value").set;
    el.focus();
    setter.call(el, valor);
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    el.blur();
  }

  function marcar(el, activo) {
    if (el.checked !== activo) el.click();
  }

  function adjuntar(el, archivo) {
    const bytes = Uint8Array.from(atob(archivo.base64), (c) => c.charCodeAt(0));
    const file = new File([bytes], archivo.nombre, { type: "application/pdf" });
    const dt = new DataTransfer();
    dt.items.add(file);
    el.files = dt.files;
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }

  async function llenar(respuestas, cv) {
    let escritos = 0;
    for (const r of respuestas) {
      const campo = campos[r.indice];
      if (!campo) continue;
      if (campo.tipo === "select") {
        if (r.opcion == null) continue;
        const el = campo.el;
        el.focus();
        el.selectedIndex = campo.indices[r.opcion];
        el.dispatchEvent(new Event("input", { bubbles: true }));
        el.dispatchEvent(new Event("change", { bubbles: true }));
        el.blur();
      } else if (campo.tipo === "radio") {
        if (r.opcion == null) continue;
        marcar(campo.elementos[r.opcion], true);
      } else if (campo.tipo === "checkbox") {
        if (r.opcion == null) continue;
        marcar(campo.elementos[r.opcion], true);
      } else if (campo.tipo === "casilla") {
        if (r.opcion == null) continue;
        marcar(campo.el, r.opcion === 0);
      } else if (campo.tipo !== "archivo") {
        if (r.valor == null) continue;
        asignarValor(campo.el, String(r.valor));
      }
      escritos++;
      await pausa();
    }
    let adjunto = null;
    if (cv) {
      for (const campo of campos) {
        if (campo.tipo === "archivo" && !(campo.el.files && campo.el.files.length)) {
          adjuntar(campo.el, cv);
          adjunto = cv.nombre;
          escritos++;
        }
      }
    }
    return { escritos, adjunto };
  }

  // --- pasos ----------------------------------------------------------------------------

  function error(paso, motivo, raiz) {
    return { error: "formulario_desconocido", motivo: `${paso.accion}: ${motivo}`,
      html: htmlSinValores(raiz) };
  }

  // Casos que terminan el flujo: la página dice el resultado (ya postulado, cerrada) o el
  // portal pide una acción en la cuenta antes de aceptar postulaciones (verificar el correo…)
  function casoPresente(casos, sel) {
    const url = location.href.toLowerCase();
    for (const caso of casos || []) {
      const porSelector = caso.selector && buscar(caso.selector);
      const porTexto = caso.texto && hayTexto(textos(sel, caso.texto));
      const porUrl = caso.url && [].concat(caso.url).some((p) => url.includes(p.toLowerCase()));
      if (porSelector || porTexto || porUrl) {
        return { terminar: caso.resultado, motivo: caso.motivo || caso.texto || "" };
      }
    }
    return null;
  }

  function confirmado(sel, paso) {
    const titulo = normalizar(document.title);
    return hayTexto(textos(sel, "confirmacion"))
      || textos(sel, "confirmacion_titulo").some((t) => titulo.includes(normalizar(t)))
      || Boolean(paso.selector && buscar(paso.selector));
  }

  async function paso(paso, sel, datos = {}) {
    if (hayCaptcha(sel)) return { captcha: true };
    if (sinSesion(sel)) return { sin_sesion: true };
    const adaptador = adaptadores[datos.plataforma] || {};
    if (adaptador[paso.accion]) {
      const propio = await adaptador[paso.accion](paso, sel, api);
      if (propio !== undefined) return propio;
    }
    const ms = paso.ms || 10000;
    switch (paso.accion) {
      case "detectar": {
        // Termina el flujo si la página ya dice el resultado (ya postulado, cerrada…)
        const limite = Date.now() + (paso.ms || 0);
        do {
          const caso = casoPresente(paso.casos, sel);
          if (caso) return caso;
          if (Date.now() >= limite) break;
          await dormir(250);
        } while (true);
        return { ok: true };
      }
      case "esperar": {
        const el = await esperar(paso.selector, ms);
        if (!el && !paso.opcional) return error(paso, "no apareció el elemento");
        return { ok: true, encontrado: Boolean(el) };
      }
      case "clic":
      case "enviar": {
        const el = await esperar(paso.selector, ms);
        if (!el) {
          if (paso.opcional) return { ok: true, encontrado: false };
          return error(paso, "no apareció el botón");
        }
        await pausa(300, 800);
        el.scrollIntoView({ block: "center" });
        el.click();
        if (paso.errores) {
          // Si el portal no acepta el envío marca los campos en la misma página; si lo acepta,
          // la página cambia y este script deja de existir (el service worker lo sabe así)
          await dormir(paso.espera_errores_ms || 1500);
          if (buscar(paso.errores)) return error(paso, "el portal marcó campos sin responder");
        }
        return { ok: true };
      }
      case "ir": {
        const el = await esperar(paso.selector, ms, { ocultos: true });
        const url = el && (paso.atributo ? el.getAttribute(paso.atributo) : el.href);
        if (!url) {
          if (paso.opcional) return { ok: true, encontrado: false };
          return error(paso, "no apareció el enlace");
        }
        return { ir: new URL(url, location.href).href };
      }
      case "formulario": {
        const contenedor = await esperar(paso.contenedor || ["form"], ms);
        if (!contenedor) {
          if (paso.opcional) return { ok: true, campos: [] };
          return error(paso, "no apareció el formulario");
        }
        return { campos: leerCampos(contenedor) };
      }
      case "llenar":
        return { ok: true, ...(await llenar(datos.respuestas || [], datos.cv)) };
      case "cv_liberar": {
        // perfil_multiple: si se alcanzó el límite, borra solo un CV subido por el sistema
        const filas = [].concat(paso.item || []).flatMap((x) => candidatos(x)).filter(visible);
        if (filas.length < (paso.limite || 1)) return { ok: true, liberado: false };
        const propia = filas.find((f) => {
          const nombre = textoDe(buscar(paso.nombre_cv, { raiz: f }) || f);
          return /^CV_[^\s]+\.pdf$/i.test(nombre.trim()) || nombre.includes(datos.cv_nombre || "\u0000");
        });
        if (!propia) return { ok: true, liberado: false, sin_espacio: true };
        const borrar = buscar(paso.eliminar, { raiz: propia });
        if (!borrar) return error(paso, "no apareció el botón de eliminar");
        borrar.click();
        if (paso.confirmar) {
          const confirmar = await esperar(paso.confirmar, ms);
          if (confirmar) confirmar.click();
        }
        await dormir(1500);
        return { ok: true, liberado: true };
      }
      case "cv_subir": {
        const el = await esperar(paso.selector, ms, { ocultos: true });
        if (!el) return error(paso, "no apareció el campo del archivo");
        if (!datos.cv) return { ok: true, subido: false };
        adjuntar(el, datos.cv);
        if (paso.guardar) {
          const boton = await esperar(paso.guardar, ms);
          if (boton) boton.click();
        }
        return { ok: true, subido: true };
      }
      case "cv_verificar": {
        const nombre = normalizar(datos.cv_nombre || "");
        const limite = Date.now() + ms;
        do {
          if (nombre && textoPagina().includes(nombre)) return { ok: true, verificado: true };
          await dormir(500);
        } while (Date.now() < limite);
        return { ok: true, verificado: false };
      }
      case "confirmar": {
        const limite = Date.now() + (paso.ms || 20000);
        do {
          if (confirmado(sel, paso)) return { confirmado: true, texto: document.title.slice(0, 200) };
          const caso = casoPresente(paso.casos, sel);
          if (caso) return caso;
          if (hayCaptcha(sel)) return { captcha: true };
          await dormir(500);
        } while (Date.now() < limite);
        // El formulario sigue en pantalla: el portal no aceptó el envío (validación propia,
        // un campo que no aceptó la respuesta…). No es "sin confirmación": no se envió nada.
        if (paso.no_enviado && buscar(paso.no_enviado)) {
          return error(paso, "el portal no aceptó el envío: el formulario sigue en pantalla");
        }
        return { confirmado: false, html: htmlSinValores() };
      }
      default:
        return error(paso, "acción desconocida");
    }
  }

  // Estado del portal: sesión, correo de la cuenta y secciones del perfil
  async function revisar(sel, datos = {}) {
    await esperar(["body"], 5000);
    await dormir(datos.espera_ms ?? 1500); // las páginas armadas con JS tardan en mostrar el usuario
    if (sinSesion(sel)) {
      const redirigido = ((sel.sesion || {}).url_sin_sesion || []).some((p) => location.href.includes(p));
      return { estado: "sin_sesion", motivo: redirigido ? "redireccion_login" : "enlace_ingresar" };
    }
    const s = sel.sesion || {};
    // La marca de sesión debe existir; no se exige que se vea (en pantallas pequeñas el portal
    // la oculta en un menú)
    if ((s.iniciada || []).length && !(await esperar(s.iniciada, 5000, { ocultos: true }))) {
      return { estado: "sin_sesion", motivo: "sin_marca_sesion" };
    }
    const resultado = { estado: "listo", correo: null, secciones: {} };
    const cuenta = sel.cuenta || {};
    if (cuenta.correo) await esperar(cuenta.correo, 3000, { ocultos: true });
    resultado.correo = buscarCorreo(sel).correo || null;
    for (const [nombre, seccion] of Object.entries((sel.perfil || {}).secciones || {})) {
      if (datos.secciones === false) break;
      if (seccion.url && !location.href.startsWith(seccion.url)) continue;
      const completa = seccion.completo ? Boolean(buscar(seccion.completo, { ocultos: true })) : true;
      const vacia = seccion.vacio ? Boolean(buscar(seccion.vacio)) : false;
      resultado.secciones[nombre] = completa && !vacia;
    }
    return resultado;
  }

  // --- correo de la cuenta ----------------------------------------------------------------

  const CORREO = /[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+/g;
  // Correos del propio portal o de soporte, que no son del usuario
  const AJENOS = /^(no-?reply|noreply|info|soporte|support|contacto|ayuda|help|servicio|atencion|privacidad|privacy|notificaciones|empleo|empresas)@/i;
  const ENLACES_CUENTA = /mi cuenta|cuenta|configuraci|ajustes|datos de acceso|datos personales|mi perfil|perfil|hoja de vida|mi cv|account|settings|profile/;

  function dominioPortal() {
    return location.hostname.split(".").slice(-2).join(".");
  }

  function correoValido(c) {
    const correo = c.toLowerCase();
    return !AJENOS.test(correo) && !correo.endsWith("@" + dominioPortal())
      && !/\.(png|jpe?g|gif|svg|webp)$/.test(correo);
  }

  function buscarCorreo(sel) {
    if (sinSesion(sel)) return { sin_sesion: true };
    const candidatos = [];
    const el = buscar((sel.cuenta || {}).correo || [], { ocultos: true });
    if (el) candidatos.push(el.value || el.getAttribute("content") || el.textContent || "");
    document.querySelectorAll("input[type='email'], input[name*='mail' i], input[id*='mail' i]")
      .forEach((i) => candidatos.push(i.value || ""));
    candidatos.push(document.body ? document.body.innerText : "");
    for (const texto of candidatos) {
      const correo = (String(texto).match(CORREO) || []).find(correoValido);
      if (correo) return { correo: correo.toLowerCase(), enlaces: [] };
    }
    return { correo: null, enlaces: enlacesCuenta() };
  }

  // Enlaces del mismo portal hacia la cuenta o el perfil del usuario
  function enlacesCuenta() {
    const salida = [];
    for (const a of document.querySelectorAll("a[href]")) {
      const texto = normalizar(a.textContent + " " + (a.getAttribute("title") || "") + " "
        + (a.getAttribute("aria-label") || ""));
      if (!ENLACES_CUENTA.test(texto)) continue;
      let url;
      try {
        url = new URL(a.href, location.href);
      } catch {
        continue;
      }
      if (!url.hostname.endsWith(dominioPortal()) || url.protocol !== "https:") continue;
      if (!salida.includes(url.href)) salida.push(url.href);
      if (salida.length >= 8) break;
    }
    return salida;
  }

  const api = { buscar, esperar, visible, normalizar, hayTexto, htmlSinValores, leerCampos,
    llenar, dormir, pausa, error };

  globalThis.__asistente = {
    registrar(nombre, hooks) {
      adaptadores[nombre] = hooks;
    },
    paso,
    revisar,
    buscarCorreo,
    enlacesCuenta,
    sesion: (sel) => ({ sin_sesion: sinSesion(sel), captcha: hayCaptcha(sel) }),
    html: () => htmlSinValores(),
    api,
  };
})();
