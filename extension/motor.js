// Motor de pasos declarativos. Se inyecta en la pestaña del portal y ejecuta UN paso por
// llamada; el service worker coordina el flujo entre páginas. No ejecuta código remoto: los
// pasos y selectores del servidor son datos que este archivo interpreta.

(() => {
  if (globalThis.__asistente) return; // ya inyectado en esta página

  const adaptadores = {};
  let campos = []; // campos leídos por el último paso "formulario" en esta página
  let turnoChat = null; // turno actual leído por chat_turno en esta página

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
      const permitirOculto = ocultos || Boolean(selector && typeof selector === "object" && selector.ocultos);
      const el = candidatos(selector, raiz).find((x) => permitirOculto || visible(x));
      if (el) return el;
    }
    return null;
  }

  async function esperar(selectores, ms = 10000, opciones = {}) {
    const limite = Date.now() + ms;
    do {
      const el = buscar(selectores, opciones);
      if (!el && opciones.cortar && buscar(opciones.cortar)) return null;
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

  function enIngreso(sel) {
    return ((sel.sesion || {}).url_sin_sesion || []).some((p) => location.href.includes(p));
  }

  // La marca de sesión debe existir; no se exige que se vea (en pantallas pequeñas el portal
  // la oculta en un menú)
  function hayMarca(sel) {
    const marca = (sel.sesion || {}).iniciada || [];
    return marca.length > 0 && Boolean(buscar(marca, { ocultos: true }));
  }

  // Por qué no hay sesión, o null si la hay. La página de ingreso manda; si no, la marca de
  // sesión iniciada prevalece sobre el enlace de ingreso (Magneto lo trae en el HTML inicial
  // aunque haya sesión). Con marca_obligatoria, sin marca tampoco hay sesión.
  function motivoSinSesion(sel) {
    const s = sel.sesion || {};
    if (enIngreso(sel)) return "redireccion_login";
    if (hayMarca(sel)) return null;
    if (buscar(s.sin_sesion || [])) return "enlace_ingresar";
    if (s.marca_obligatoria && (s.iniciada || []).length) return "sin_marca_sesion";
    return null;
  }

  function sinSesion(sel) {
    return Boolean(motivoSinSesion(sel));
  }

  // Espera la marca hasta sesion.espera_ms: hay portales que la muestran solo cuando la página
  // termina de cargarse. Esperan los portales con marca obligatoria y, con `exigirMarca` (la
  // revisión del portal), también los demás mientras no haya enlace de ingreso, como antes.
  async function esperarSesion(sel, { exigirMarca = false } = {}) {
    const s = sel.sesion || {};
    const marca = s.iniciada || [];
    const esperarMarca = marca.length && !enIngreso(sel) && !hayMarca(sel)
      && (s.marca_obligatoria || (exigirMarca && !buscar(s.sin_sesion || [])));
    if (esperarMarca) await esperar(marca, s.espera_ms ?? 5000, { ocultos: true });
    const motivo = motivoSinSesion(sel);
    if (motivo) return motivo;
    return exigirMarca && marca.length && !hayMarca(sel) ? "sin_marca_sesion" : null;
  }

  // HTML del formulario (o la página) sin los valores escritos: evidencia para el dueño
  function htmlSinValores(raiz) {
    const enContenedor = Boolean(
      raiz && raiz !== document.documentElement && raiz !== document.body
      && raiz.closest("[role=dialog], [aria-modal=true], dialog, form, article"),
    );
    const copia = (raiz || document.documentElement).cloneNode(true);
    copia.querySelectorAll("script, style, noscript, svg, img, iframe").forEach((n) => n.remove());
    // Sin la cabecera, el menú ni el recuadro de la cuenta: ahí están el nombre y el correo
    copia.querySelectorAll("header, nav, footer").forEach((n) => {
      if (!enContenedor && !n.closest("[role=dialog], [aria-modal=true], dialog, form, article")) n.remove();
    });
    copia.querySelectorAll("[data-info-user], .header_popup, [class*='user' i]")
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

  // maxlength de un campo de texto, para que la redacción quepa. Sin atributo (-1) o con uno
  // enorme, que no limita nada, no se envía.
  function maximoDe(el) {
    if (el.tagName === "SELECT") return null;
    const maximo = el.maxLength;
    return maximo > 0 && maximo <= 100000 ? maximo : null;
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
        maximo: maximoDe(el),
      });
    }
    return salida.slice(0, 80);
  }

  // Límite de una pregunta abierta: el maxlength del campo o, si no lo tiene, el número del
  // contador que muestra el portal («0 de 140», Magneto)
  function limiteDe(campo, bloque, def) {
    const propio = maximoDe(campo);
    if (propio) return propio;
    for (const el of [].concat(def.limite || []).flatMap((s) => candidatos(s, bloque))) {
      const m = textoDe(el).match(/de\s+(\d+)/i);
      if (m) return Number(m[1]);
    }
    return null;
  }

  // Encuesta hecha de preguntas sin <form> ni name (Magneto). `def` declara el bloque de cada
  // pregunta, su título, su botón de respuesta y, para las preguntas de texto, el campo
  // abierto (`abierta`) y el contador de caracteres (`limite`). Cada pregunta es obligatoria:
  // el portal no deja enviar sin responderlas. Los botones de «Cancelar» y de enviar quedan
  // fuera porque no son botones de respuesta ni están dentro de una pregunta.
  function leerPreguntas(contenedor, def) {
    const titulo = (bloque) => textoDe(buscar(def.titulo, { raiz: bloque }));
    const bloques = candidatos(def.pregunta, contenedor).filter((b) => visible(b) && titulo(b));
    // Si un bloque contiene a otro con título, vale el interior (el exterior es un envoltorio)
    const preguntas = bloques.filter((b) => !bloques.some((o) => o !== b && b.contains(o)));
    campos = [];
    const salida = [];
    for (const bloque of preguntas) {
      const botones = candidatos(def.respuesta, bloque).filter(visible);
      const abierta = !botones.length && def.abierta
        ? buscar(def.abierta, { raiz: bloque }) : null;
      if (abierta && !abierta.disabled && !abierta.readOnly) {
        campos.push({ tipo: "abierta", el: abierta });
        salida.push({
          texto: titulo(bloque).slice(0, 1000),
          tipo: "texto",
          opciones: [],
          obligatoria: true,
          nombre: null,
          maximo: limiteDe(abierta, bloque, def),
        });
        continue;
      }
      if (!botones.length) return { sin_respuesta: titulo(bloque).slice(0, 200) };
      campos.push({ tipo: "boton", elementos: botones });
      salida.push({
        texto: titulo(bloque).slice(0, 1000),
        tipo: "opciones",
        opciones: botones.map((b) => textoDe(b)),
        obligatoria: true,
        nombre: null,
      });
    }
    return { campos: salida.slice(0, 80) };
  }

  // --- cuestionario conversacional por turnos (Magneto) -------------------------------------

  function limpiarTextoPortal(valor, regla, maximo) {
    let t = String(valor ?? "");
    if (regla === "magneto_texto") {
      t = t
        .replace(/[—–―]/g, "-")
        .replace(/[/\\]/g, "-")
        .replace(/[«»“”„]/g, '"')
        .replace(/[‘’‚]/g, "'")
        .replace(/…/g, "...")
        .replace(/[•·]/g, "-")
        .replace(/\[/g, "(")
        .replace(/\]/g, ")")
        .replace(/[^a-zA-ZÀ-ÿ0-9\s.,¿¡!?@$%^&*()_+\-=;:'"|`´]/g, " ")
        .replace(/[ \t]{2,}/g, " ")
        .trim();
    }
    if (maximo && t.length > maximo) t = t.slice(0, maximo).trim();
    return t;
  }

  function esContenedorChat(contenedor, def) {
    if (!def || !def.contenedor) return false;
    const propios = [].concat(def.contenedor).flatMap((s) => candidatos(s));
    return propios.includes(contenedor) || Boolean(buscar(def.contenedor, { raiz: contenedor }));
  }

  function limiteChat(abierta, ayuda, bloque) {
    const propio = maximoDe(abierta);
    if (propio) return propio;
    const fuente = `${ayuda || ""} ${textoDe(bloque)}`;
    const m = fuente.match(/m[aá]ximo\s+(\d+)|de\s+(\d+)\s*$/i);
    return m ? Number(m[1] || m[2]) : null;
  }

  async function esperarTurnoChat(def) {
    turnoChat = null;
    const esperaMs = def.espera_turno_ms || 8000;
    const limite = Date.now() + esperaMs;
    let ultimoTextoSinControl = "";
    let raiz = null;
    do {
      raiz = buscar(def.contenedor);
      if (!raiz) {
        return {
          error: "formulario_desconocido",
          contenedor_abierto: true,
          motivo: "chat: desapareció la encuesta antes de enviar",
          html: htmlSinValores(),
        };
      }
      const todos = candidatos(def.pregunta, raiz).filter(visible);
      const preguntas = todos.filter((b) => !todos.some((o) => o !== b && b.contains(o)));
      const pendientes = preguntas.filter((b) => !buscar(def.respondida, { raiz: b }));
      const botonEnviar = buscar(def.enviar_final, { raiz }) || buscar(def.enviar_final);
      if (preguntas.length > 0 && pendientes.length === 0 && botonEnviar && !botonEnviar.disabled) {
        return { listo: true };
      }
      if (pendientes.length > 0) {
        const actual = pendientes[0];
        const cargando = def.cargando && buscar(def.cargando, { raiz: actual });
        const burbuja = !cargando && buscar(def.burbuja_bot, { raiz: actual });
        if (burbuja) {
          const nodoTitulo = def.titulo ? burbuja.querySelector(def.titulo) : burbuja;
          const nodoAyuda = def.ayuda ? burbuja.querySelector(def.ayuda) : null;
          const texto = textoDe(nodoTitulo || burbuja);
          const ayuda = textoDe(nodoAyuda) || null;
          if (texto) {
            const unicas = candidatos(def.unica, actual).filter(visible);
            if (unicas.length) {
              turnoChat = { bloque: actual, raiz, tipo: "unica", elementos: unicas, def };
              return {
                campo: {
                  texto: texto.slice(0, 1000),
                  ayuda,
                  tipo: "opciones",
                  opciones: unicas.map((o) => textoDe(o)),
                  obligatoria: true,
                  multiple: false,
                  nombre: null,
                  maximo: null,
                },
              };
            }
            const multiples = candidatos(def.multiple, actual).filter(visible);
            if (multiples.length) {
              turnoChat = { bloque: actual, raiz, tipo: "multiple", elementos: multiples, def };
              return {
                campo: {
                  texto: texto.slice(0, 1000),
                  ayuda,
                  tipo: "opciones",
                  opciones: multiples.map((o) => textoDe(o)),
                  obligatoria: true,
                  multiple: true,
                  nombre: null,
                  maximo: null,
                },
              };
            }
            const abierta = buscar(def.abierta, { raiz: actual });
            if (abierta && !abierta.disabled && !abierta.readOnly) {
              const maximo = limiteChat(abierta, ayuda, actual);
              turnoChat = { bloque: actual, raiz, tipo: "abierta", el: abierta, maximo, def };
              return {
                campo: {
                  texto: texto.slice(0, 1000),
                  ayuda,
                  tipo: "texto",
                  opciones: [],
                  obligatoria: true,
                  multiple: false,
                  nombre: null,
                  maximo,
                },
              };
            }
            ultimoTextoSinControl = texto;
          }
        }
      }
      await dormir(150);
    } while (Date.now() < limite);
    const motivo = ultimoTextoSinControl
      ? `chat: la pregunta «${ultimoTextoSinControl.slice(0, 200)}» no tiene controles de respuesta`
      : "chat: no apareció la siguiente pregunta ni se habilitó enviar";
    return {
      error: "formulario_desconocido",
      contenedor_abierto: true,
      motivo,
      html: htmlSinValores(raiz),
    };
  }

  async function responderTurnoChat(respuestas) {
    if (!turnoChat || !turnoChat.bloque || !turnoChat.bloque.isConnected) {
      return {
        error: "formulario_desconocido",
        contenedor_abierto: true,
        motivo: "llenar: el turno del chat ya no está en pantalla",
        html: htmlSinValores(),
      };
    }
    const { bloque, raiz, tipo, def } = turnoChat;
    const r = (respuestas || [])[0];
    const fallo = (motivo) => ({
      error: "formulario_desconocido",
      contenedor_abierto: true,
      motivo: `llenar: ${motivo}`,
      html: htmlSinValores(raiz),
    });
    const esperarRespondida = async (ms = 2500) => {
      const limite = Date.now() + ms;
      while (Date.now() < limite) {
        if (buscar(def.respondida, { raiz: bloque })) return true;
        await dormir(100);
      }
      return Boolean(buscar(def.respondida, { raiz: bloque }));
    };
    if (!r) return fallo("falta la respuesta del turno");

    if (tipo === "unica") {
      const op = turnoChat.elementos[r.opcion];
      if (!op) return fallo("la opción elegida no existe en el turno");
      const input = op.querySelector("input");
      op.scrollIntoView({ block: "center" });
      op.click();
      if (!(await esperarRespondida(400)) && input && input.isConnected && !input.checked) {
        input.click();
      }
      if (!(await esperarRespondida(2500))) {
        return fallo("la opción elegida no quedó marcada");
      }
    } else if (tipo === "multiple") {
      const indices = Array.isArray(r.opciones) && r.opciones.length
        ? r.opciones
        : (r.opcion != null ? [r.opcion] : []);
      if (!indices.length) return fallo("no hay opciones elegidas para marcar");
      for (const idx of indices) {
        const op = turnoChat.elementos[idx];
        if (!op) return fallo("una opción elegida no existe en el turno");
        const input = op.querySelector("input[type='checkbox'], input");
        op.scrollIntoView({ block: "center" });
        if (!input || !input.checked) op.click();
        await dormir(150);
        if (input && !input.checked) input.click();
        await dormir(100);
        if (input && !input.checked) return fallo("la opción múltiple no quedó marcada");
      }
      const guardar = await esperar(def.guardar_multiple, 2000, { raiz: bloque });
      if (!guardar) return fallo("no apareció el botón Guardar de la pregunta múltiple");
      const topeGuardar = Date.now() + 1500;
      while (guardar.disabled && Date.now() < topeGuardar) await dormir(100);
      if (guardar.disabled) return fallo("el botón Guardar sigue deshabilitado");
      guardar.scrollIntoView({ block: "center" });
      guardar.click();
      if (!(await esperarRespondida(2500))) {
        return fallo("la pregunta múltiple no quedó registrada al guardar");
      }
    } else if (tipo === "abierta") {
      if (r.valor == null) return fallo("falta el texto de la respuesta abierta");
      const limpio = limpiarTextoPortal(r.valor, def.caracteres_permitidos, turnoChat.maximo);
      if (!limpio) return fallo("la respuesta abierta quedó vacía tras limpiar caracteres");
      const el = turnoChat.el;
      el.scrollIntoView({ block: "center" });
      asignarValor(el, limpio);
      await dormir(200);
      const normalizarSaltos = (t) => String(t).replace(/\r\n?/g, "\n");
      if (normalizarSaltos(el.value) !== normalizarSaltos(limpio)) {
        return fallo("la respuesta abierta no quedó escrita en el campo");
      }
      const boton = await esperar(def.enviar_abierta, 2000, { raiz: bloque });
      if (!boton) return fallo("no apareció el botón para enviar la respuesta abierta");
      const topeBoton = Date.now() + 1500;
      while (boton.disabled && Date.now() < topeBoton) await dormir(100);
      if (boton.disabled) return fallo("el botón de la respuesta abierta sigue deshabilitado");
      boton.scrollIntoView({ block: "center" });
      boton.click();
      if (!(await esperarRespondida(2500))) {
        return fallo("el chat no registró la respuesta abierta");
      }
    }
    await pausa();
    return { ok: true };
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

  // Pulsa el botón de una respuesta y comprueba que su input quedó marcado. Si el portal solo
  // escucha al input, se prueba también con él. Un botón sin input se da por pulsado.
  async function pulsarRespuesta(boton) {
    if (!boton) return false;
    const input = boton.querySelector("input");
    const marcado = async () => {
      await dormir(200); // el portal marca la opción de forma asíncrona
      return !input || input.checked;
    };
    boton.scrollIntoView({ block: "center" });
    boton.click();
    if (await marcado()) return true;
    input.click();
    return marcado();
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
    // Número (desde 1) de cada pregunta que quedó escrita o marcada: el servicio lo reporta
    // paso a paso, así un llenado que se corta muestra hasta dónde llegó
    const escritas = [];
    const fallo = (motivo) => ({ ...error({ accion: "llenar" }, motivo), escritas });
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
      } else if (campo.tipo === "boton") {
        if (r.opcion == null) continue;
        if (!(await pulsarRespuesta(campo.elementos[r.opcion]))) {
          return fallo("la opción elegida no quedó marcada");
        }
      } else if (campo.tipo === "abierta") {
        // Pregunta abierta de una encuesta (Magneto, React): se comprueba que el portal
        // aceptó el texto, porque un componente controlado puede descartarlo
        if (r.valor == null) continue;
        const valor = String(r.valor);
        campo.el.scrollIntoView({ block: "center" });
        asignarValor(campo.el, valor);
        await dormir(200);
        const linea = (t) => t.replace(/\r\n?/g, "\n"); // el textarea normaliza los saltos
        if (linea(campo.el.value) !== linea(valor)) {
          return fallo("la respuesta abierta no quedó escrita en el campo");
        }
      } else if (campo.tipo === "casilla") {
        if (r.opcion == null) continue;
        marcar(campo.el, r.opcion === 0);
      } else if (campo.tipo !== "archivo") {
        if (r.valor == null) continue;
        asignarValor(campo.el, String(r.valor));
      }
      escritos++;
      escritas.push(r.indice + 1);
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
    return { escritos, adjunto, escritas };
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

  // Qué se guarda como confirmación: el título de la página o, si el paso lo pide
  // (`texto_de_selector`), el texto del aviso que lo confirmó (Magneto no cambia el título)
  function textoConfirmacion(paso) {
    const aviso = paso.texto_de_selector && paso.selector && buscar(paso.selector);
    return (aviso ? textoDe(aviso) : document.title).slice(0, 200);
  }

  async function paso(paso, sel, datos = {}) {
    if (hayCaptcha(sel)) return { captcha: true };
    if (await esperarSesion(sel)) return { sin_sesion: true };
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
        const el = await esperar(paso.selector, ms, { cortar: paso.cortar_si });
        if (!el && !paso.opcional) return error(paso, "no apareció el elemento");
        return { ok: true, encontrado: Boolean(el) };
      }
      case "clic":
      case "enviar": {
        const el = await esperar(paso.selector, ms, { cortar: paso.cortar_si });
        if (!el) {
          if (paso.opcional) return { ok: true, encontrado: false };
          return error(paso, "no apareció el botón");
        }
        if (paso.esperar_habilitado) {
          // El portal habilita el botón cuando da todo por respondido (Magneto). Pulsar uno
          // deshabilitado no envía nada: se reporta en vez de esperar una confirmación.
          const limite = Date.now() + ms;
          while (el.disabled && Date.now() < limite) await dormir(250);
          if (el.disabled) {
            return error(paso, "el botón de enviar sigue deshabilitado: el portal no dio por respondidas todas las preguntas");
          }
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
        const contenedor = await esperar(paso.contenedor || ["form"], ms, { cortar: paso.cortar_si });
        if (!contenedor) {
          if (paso.opcional) return { ok: true, campos: [] };
          return error(paso, "no apareció el formulario");
        }
        if (paso.chat && esContenedorChat(contenedor, paso.chat)) {
          return { chat: true, contenedor_abierto: true };
        }
        if (paso.preguntas) {
          const leidas = leerPreguntas(contenedor, paso.preguntas);
          if (leidas.sin_respuesta) {
            return {
              ...error(paso, `la pregunta «${leidas.sin_respuesta}» no tiene botones ni campo de respuesta`, contenedor),
              contenedor_abierto: true,
            };
          }
          return { campos: leidas.campos, contenedor_abierto: true };
        }
        return { campos: leerCampos(contenedor), contenedor_abierto: true };
      }
      case "chat_turno":
        return esperarTurnoChat(paso.chat || {});
      case "chat_llenar": {
        return responderTurnoChat(datos.respuestas || []);
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
          if (confirmado(sel, paso)) return { confirmado: true, texto: textoConfirmacion(paso) };
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
        // Sin encuesta ni modal y con el botón de postular aún en la vacante, el portal no
        // procesó el clic: no se envió nada (a diferencia de un envío sin confirmación)
        if (paso.sin_efecto && buscar(paso.sin_efecto)) {
          return { error: "formulario_desconocido", motivo: "aplicar_sin_efecto",
            html: htmlSinValores() };
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
    const motivo = await esperarSesion(sel, { exigirMarca: true });
    if (motivo) return { estado: "sin_sesion", motivo };
    const resultado = { estado: "listo", correo: null, secciones: {} };
    const cuenta = sel.cuenta || {};
    await abrirCuenta(sel);
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

  // `ajenos`: dominios o correos del portal que declara cuenta.dominios_ajenos (elempleo
  // pertenece a El Tiempo y su soporte escribe desde @eltiempo.com)
  function correoValido(c, ajenos = []) {
    const correo = c.toLowerCase();
    const dominio = correo.split("@")[1] || "";
    if (ajenos.some((a) => String(a).toLowerCase().replace(/^@/, "") === dominio
      || String(a).toLowerCase() === correo || dominio.endsWith("." + String(a).toLowerCase().replace(/^@/, "")))) {
      return false;
    }
    return !AJENOS.test(correo) && !correo.endsWith("@" + dominioPortal())
      && !/\.(png|jpe?g|gif|svg|webp)$/.test(correo);
  }

  // La sesión ya la confirmó `revisar`: en las páginas de cuenta solo la página o el enlace de
  // ingreso dicen que se perdió (una página sin la marca deja el correo sin encontrar)
  function buscarCorreo(sel) {
    const motivo = motivoSinSesion(sel);
    if (motivo && motivo !== "sin_marca_sesion") return { sin_sesion: true };
    const cuenta = sel.cuenta || {};
    const ajenos = cuenta.dominios_ajenos || [];
    const candidatos = [];
    const el = buscar(cuenta.correo || [], { ocultos: true });
    if (el) candidatos.push(el.value || el.getAttribute("content") || el.textContent || "");
    // Con selectores verificados no se lee texto libre: trae correos de soporte o de vacantes
    if (!cuenta.solo_selectores) {
      document.querySelectorAll("input[type='email'], input[name*='mail' i], input[id*='mail' i]")
        .forEach((i) => candidatos.push(i.value || ""));
      candidatos.push(document.body ? document.body.innerText : "");
    }
    for (const texto of candidatos) {
      const correo = (String(texto).match(CORREO) || []).find((c) => correoValido(c, ajenos));
      if (correo) return { correo: correo.toLowerCase(), enlaces: [] };
    }
    return { correo: null, enlaces: enlacesCuenta() };
  }

  // Correo válido dentro de los elementos declarados en cuenta.correo (sin mirar el resto de
  // la página, que puede traer correos de las vacantes listadas)
  function correoDeLaCuenta(sel) {
    for (const selector of [].concat((sel.cuenta || {}).correo || [])) {
      for (const el of candidatos(selector)) {
        const texto = el.value || el.getAttribute("content") || el.textContent || "";
        const ajenos = (sel.cuenta || {}).dominios_ajenos || [];
        if ((String(texto).match(CORREO) || []).some((c) => correoValido(c, ajenos))) return true;
      }
    }
    return false;
  }

  // Hay portales que solo generan el correo al abrir el menú de la cuenta (Magneto: clic en el
  // avatar). Se hace clic solo en el elemento declarado en cuenta.abrir, que únicamente
  // despliega el menú, y se espera el correo hasta 3 s.
  async function abrirCuenta(sel) {
    const abrir = (sel.cuenta || {}).abrir || [];
    if (!abrir.length || (await esperarSesion(sel)) || correoDeLaCuenta(sel)) {
      return { abierto: false };
    }
    const el = await esperar(abrir, 3000);
    if (!el) return { abierto: false };
    el.click();
    const limite = Date.now() + 3000;
    while (!correoDeLaCuenta(sel) && Date.now() < limite) await dormir(250);
    return { abierto: true };
  }

  // Hay portales que pintan la ventana de la cuenta con JavaScript tras cargar la página
  // (LinkedIn): `cuenta.espera_ms` es lo máximo que se espera a que aparezca el correo
  async function esperarCorreo(sel) {
    const limite = Date.now() + ((sel.cuenta || {}).espera_ms || 0);
    while (!correoDeLaCuenta(sel) && Date.now() < limite) await dormir(250);
  }

  // Correo leído del HTML que entrega el portal, sin esperar a que lo pinte (LinkedIn: en la
  // pestaña de revisión, que está en segundo plano, ni salta de /in/me/ al perfil ni pinta la
  // ventana de contacto; el correo ya viene en los datos de la página). `cuenta.html` declara
  // de dónde sale el usuario del perfil, la página de contacto y la expresión del correo. Solo
  // GET al mismo origen, con la sesión del navegador.
  async function correoPorHtml(sel) {
    const cuenta = sel.cuenta || {};
    const h = cuenta.html;
    if (!h) return null;
    async function leer(ruta) {
      const r = await fetch(new URL(ruta, location.origin), { credentials: "same-origin" });
      const sinSesion = ((sel.sesion || {}).url_sin_sesion || []).some((p) => r.url.includes(p));
      return { sinSesion, texto: sinSesion ? "" : await r.text() };
    }
    try {
      let perfil = h.perfil_ruta ? (location.pathname.match(new RegExp(h.perfil_ruta)) || [])[1] : null;
      if (!perfil && h.inicio && h.perfil_html) {
        const inicio = await leer(h.inicio);
        if (inicio.sinSesion) return { correo: null, motivo: "sin_sesion" };
        // El propio perfil aparece cientos de veces; los sugeridos, pocas
        const cuentas = {};
        for (const m of inicio.texto.matchAll(new RegExp(h.perfil_html, "g"))) {
          if (m[1] && m[1] !== "me") cuentas[m[1]] = (cuentas[m[1]] || 0) + 1;
        }
        perfil = Object.keys(cuentas).sort((a, b) => cuentas[b] - cuentas[a])[0] || null;
      }
      if (!perfil) return { correo: null, motivo: "sin_perfil" };
      const ruta = h.url.replace("{perfil}", perfil);
      const contacto = await leer(ruta);
      if (contacto.sinSesion) return { correo: null, motivo: "sin_sesion" };
      const ajenos = cuenta.dominios_ajenos || [];
      const correos = new Set();
      for (const m of contacto.texto.matchAll(new RegExp(h.correo, "g"))) {
        let c = m[1] || "";
        try {
          c = decodeURIComponent(c);
        } catch {
          // se deja como vino
        }
        c = c.trim().toLowerCase();
        if ((c.match(CORREO) || [])[0] === c && correoValido(c, ajenos)) correos.add(c);
      }
      if (correos.size === 1) return { correo: [...correos][0], ruta: new URL(ruta, location.origin).pathname };
      return { correo: null, motivo: correos.size ? "varios_correos" : "sin_correo" };
    } catch (error) {
      return { correo: null, motivo: "sin_correo" };
    }
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

  // --- motor genérico: pantallas que nadie declaró ----------------------------------------
  // Lee la pantalla, extrae el esquema (también de los controles ARIA), llena comprobando cada
  // campo, clasifica los botones y reconoce el resultado. Los textos, las trampas y los desafíos
  // llegan del servidor (assets/asistente/motor_generico.json); aquí solo quedan las reglas de
  // seguridad que no se pueden apagar: nunca se leen ni se llenan contraseñas, campos ocultos ni
  // respuestas de captcha, y el resumen para la IA nunca lleva valores.

  const AUTOCOMPLETE_CLAVE = /(^|\s)(current-password|new-password)(\s|$)/i;
  const RESPUESTA_CAPTCHA = /g-recaptcha-response|h-captcha-response|cf-turnstile-response/i;
  // Etiqueta de un botón de archivo («Attach»): la pregunta está en el grupo que lo contiene
  const ETIQUETA_DE_BOTON = /^(attach|adjuntar|subir|upload|upload file|choose file|seleccionar archivo|examinar|browse|anexar)$/;
  const AUTORRELLENO = /autofill|auto-fill|autocompletar|rellenar automaticamente|preencher automaticamente/;
  const TIPOS_ARCHIVO = [
    ["certificado_notas", /transcript|certificado de notas|calificaciones|notas academicas|historico escolar/],
    ["carta", /cover letter|carta de presentacion|carta/],
    ["portafolio", /portfolio|portafolio|portafolio/],
    ["cv", /resume|\bcv\b|curriculum|curriculo|hoja de vida/],
  ];
  const CONTROLES = "input, select, textarea, [role=combobox], button[aria-haspopup=listbox], "
    + "[role=radiogroup], [role=radio], [role=checkbox], [role=switch], [role=listbox], "
    + "[contenteditable=''], [contenteditable=true]";
  const INTERACTIVOS = "input, select, textarea, button, a[href], [role=button], [role=link], "
    + "[role=combobox], [role=radio], [role=checkbox], [role=switch], [role=tab], [role=option], "
    + "[contenteditable=''], [contenteditable=true]";
  const FUERA = "header, nav, footer, [role=search], [role=banner], [role=contentinfo]";
  const MAX_RESUMEN = 150;
  const MAX_BYTES_RESUMEN = 12 * 1024;

  // Lo leído en la última pantalla: los índices del esquema, de los botones y del resumen
  // apuntan a estos elementos
  const generico = { campos: [], botones: [], clases: [], elementos: [], contenedor: null,
    fijo: null, familia: null };

  function escaparRegex(t) {
    return t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  // Textos de una clave de las reglas en los tres idiomas, ya normalizados
  function frases(reglas, clave) {
    const porIdioma = ((reglas || {}).textos || {})[clave] || {};
    return Object.values(porIdioma).flat().map(normalizar).filter(Boolean);
  }

  // Una frase coincide si aparece como palabras completas (sin tildes ni mayúsculas)
  function coincide(texto, lista) {
    const t = normalizar(texto);
    if (!t) return false;
    return lista.some((f) => new RegExp(`(^|[^a-z0-9])${escaparRegex(f)}([^a-z0-9]|$)`).test(t));
  }

  function limpiarEtiqueta(texto) {
    return String(texto || "").replace(/\s+/g, " ").trim()
      .replace(/^\d+\s*(→|\.|\))\s*/, "") // numeración de la pregunta («1→», «2.»)
      .replace(/\s*\*\s*$/, "")
      .trim();
  }

  function dentroDePantalla(el) {
    const r = el.getBoundingClientRect();
    if (r.width <= 1 && r.height <= 1) return false;
    return r.right + scrollX > 0 && r.bottom + scrollY > 0;
  }

  function visibleGenerico(el) {
    if (!visible(el) || !dentroDePantalla(el)) return false;
    if (el.getAttribute("tabindex") === "-1" && el.getAttribute("aria-hidden") === "true") return false;
    return getComputedStyle(el).opacity !== "0";
  }

  function esTrampa(el, reglas) {
    const tokens = normalizar([el.name, el.id, el.getAttribute("data-automation-id")].join(" "));
    return ((reglas || {}).trampas || []).some((t) => tokens.includes(normalizar(t)));
  }

  function esClave(el) {
    return (el.getAttribute("type") || "").toLowerCase() === "password"
      || AUTOCOMPLETE_CLAVE.test(el.getAttribute("autocomplete") || "");
  }

  function textoPorIds(ids) {
    return String(ids || "").split(/\s+/).filter(Boolean)
      .map((i) => textoDe(document.getElementById(i))).filter(Boolean).join(" ").trim();
  }

  function bannersCookies(reglas) {
    const lista = (((reglas || {}).cookies || {}).banner || []).flatMap((s) => candidatos(s))
      .filter(visible);
    return lista.filter((b) => !lista.some((o) => o !== b && o.contains(b)));
  }

  // Dentro del contenedor fijado (el modal de la Solicitud sencilla) su cabecera y su pie
  // cuentan: ahí están «Siguiente» y «Enviar solicitud»
  function enZonaExcluida(el, banners) {
    const zona = el.closest(FUERA);
    if (zona && !(generico.fijo && generico.fijo.contains(zona))
        && !zona.closest("[role=dialog], [aria-modal=true], dialog, form")) return true;
    return banners.some((b) => b.contains(el));
  }

  // Contenedor declarado por los datos (`reglas.contenedor`): si está en la página, campos y
  // botones se leen solo ahí dentro
  function contenedorFijo(reglas) {
    return buscar((reglas || {}).contenedor || []);
  }

  // Campos que el motor maneja por su cuenta y nunca manda al servidor (`reglas.excluir`: la
  // casilla «Sigue a …» y el grupo de CV de LinkedIn)
  function excluido(el, reglas) {
    return ((reglas || {}).excluir || []).some((s) => {
      try {
        return Boolean(el.closest(s));
      } catch {
        return false;
      }
    });
  }

  // Un elemento que coincide con un selector de los datos de la familia de ATS del destino
  function deFamilia(el, selectores) {
    return (selectores || []).some((s) => {
      try {
        return el.matches(s);
      } catch {
        return false;
      }
    });
  }

  function modalActivo(banners = []) {
    const modales = [...document.querySelectorAll("[aria-modal='true'], dialog[open]")]
      .filter((m) => visible(m) && dentroDePantalla(m) && !banners.some((b) => b.contains(m)));
    for (let i = modales.length - 1; i >= 0; i--) {
      const m = modales[i];
      if (m.querySelector(CONTROLES) || m.querySelector("button, input[type=submit], [role=button]")) {
        return m;
      }
    }
    return null;
  }

  function contenedorRadiosSinNombre(el, ambito) {
    let nodo = el.parentElement;
    for (let i = 0; nodo && i < 4 && nodo !== document.body && nodo !== ambito; i++, nodo = nodo.parentElement) {
      const radios = [...nodo.querySelectorAll("input[type=radio]")].filter((r) => !r.name);
      if (radios.length > 1) return nodo;
    }
    return null;
  }

  // Texto de un campo en el orden de la spec: etiqueta, aria-labelledby, aria-label, etiqueta
  // envolvente, leyenda o título del bloque. Una etiqueta que solo nombra el botón de un archivo
  // («Attach») no cuenta: vale la del grupo. `explicita` dice si salió del marcado del campo.
  function etiquetaGenerica(el) {
    const propia = () => {
      if (el.id) {
        const lab = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
        const t = lab && textoDe(lab);
        if (t && !ETIQUETA_DE_BOTON.test(normalizar(limpiarEtiqueta(t)))) return t;
      }
      const por = textoPorIds(el.getAttribute("aria-labelledby"));
      if (por) return por;
      if (el.getAttribute("aria-label")) {
        const t = el.getAttribute("aria-label").trim();
        if (!ETIQUETA_DE_BOTON.test(normalizar(t))) return t;
      }
      const envolvente = el.closest("label");
      if (envolvente && textoDe(envolvente)) return textoDe(envolvente);
      const grupo = el.closest("[role=group][aria-labelledby], [role=radiogroup][aria-labelledby]");
      if (grupo) {
        const t = textoPorIds(grupo.getAttribute("aria-labelledby"));
        if (t) return t;
      }
      const conjunto = el.closest("fieldset");
      const leyenda = conjunto && conjunto.querySelector("legend");
      if (leyenda && conjunto.querySelectorAll(CONTROLES).length === 1) return textoDe(leyenda);
      return "";
    };
    const t = propia();
    if (t) return { texto: t, explicita: true };
    let nodo = el.parentElement;
    for (let i = 0; nodo && i < 4; i++, nodo = nodo.parentElement) {
      const titulo = nodo.querySelector("label, legend, h2, h3, h4, p, span.label, .label");
      if (titulo && !titulo.contains(el) && textoDe(titulo)) {
        return { texto: textoDe(titulo), explicita: false };
      }
    }
    return { texto: el.getAttribute("placeholder") || el.name || "", explicita: false };
  }

  function ayudaDe(el) {
    return textoPorIds(el.getAttribute("aria-describedby")).slice(0, 300) || null;
  }

  function obligatoriaGenerica(el, textoCrudo) {
    if (requerido(el)) return true;
    const grupo = el.closest("[role=group], [role=radiogroup]");
    if (grupo && grupo.getAttribute("aria-required") === "true") return true;
    return /\*\s*$/.test(String(textoCrudo || "").trim());
  }

  function idiomaPagina() {
    return (document.documentElement.lang || "").slice(0, 2).toLowerCase() || null;
  }

  function tipoArchivo(texto) {
    const t = normalizar(texto);
    const encontrado = TIPOS_ARCHIVO.find(([, patron]) => patron.test(t));
    return encontrado ? encontrado[0] : null;
  }

  // Lista nativa de prefijos telefónicos junto a un campo de teléfono: es parte del teléfono,
  // no una pregunta aparte
  function esPrefijo(select) {
    const opciones = [...select.options].filter((o) => o.value !== "");
    const conCodigo = opciones.filter((o) => /\+\s?\d{1,3}/.test(o.textContent));
    if (!opciones.length || conCodigo.length * 2 < opciones.length) return false;
    const bloque = select.closest(".form-group, .field, fieldset") || select.parentElement;
    return Boolean(bloque && bloque.querySelector("input[type=tel]"));
  }

  function prefijoDe(el) {
    let nodo = el.parentElement;
    for (let i = 0; nodo && i < 3; i++, nodo = nodo.parentElement) {
      const sel = [...nodo.querySelectorAll("select")].find(esPrefijo);
      if (sel) return sel;
    }
    return null;
  }

  // Lista de opciones de un combobox: la que nombra aria-controls/aria-owns o el último listbox
  // visible
  function listaDe(el) {
    const id = el.getAttribute("aria-controls") || el.getAttribute("aria-owns");
    const propia = id && document.getElementById(id);
    if (propia && visible(propia)) return propia;
    return [...document.querySelectorAll("[role=listbox]")].filter(visible).pop() || null;
  }

  function opcionesDe(lista) {
    return lista ? [...lista.querySelectorAll("[role=option]")].filter(visible) : [];
  }

  function tecla(el, key) {
    const codigos = { ArrowDown: 40, Escape: 27, Enter: 13 };
    el.dispatchEvent(new KeyboardEvent("keydown", { key, code: key, keyCode: codigos[key],
      which: codigos[key], bubbles: true, cancelable: true }));
  }

  function clicCompleto(el) {
    for (const tipo of ["pointerdown", "mousedown", "pointerup", "mouseup"]) {
      const Evento = tipo.startsWith("pointer") && typeof PointerEvent === "function"
        ? PointerEvent : MouseEvent;
      el.dispatchEvent(new Evento(tipo, { bubbles: true, cancelable: true }));
    }
    el.click();
  }

  function abrirCombo(el) {
    el.focus();
    if (el.tagName === "INPUT") {
      tecla(el, "ArrowDown");
      if (el.getAttribute("aria-expanded") !== "true") clicCompleto(el);
    } else {
      el.click();
    }
  }

  function cerrarCombo(el) {
    if (el.getAttribute("aria-expanded") === "true") tecla(el, "Escape");
    if (el.getAttribute("aria-expanded") === "true" && el.tagName !== "INPUT") el.click();
    el.blur();
  }

  // Espera las opciones de la lista abierta: se corta al aparecerlas o, si la lista se abrió
  // vacía (búsqueda que espera texto), un poco después
  async function esperarOpciones(el, ms) {
    const inicio = Date.now();
    while (Date.now() - inicio < ms) {
      const lista = listaDe(el);
      const opciones = opcionesDe(lista);
      if (opciones.length) return opciones;
      if (lista && Date.now() - inicio > 400) break;
      await dormir(100);
    }
    return [];
  }

  // Abre la lista, lee sus opciones y la cierra sin elegir nada
  async function leerOpcionesCombo(el) {
    let opciones = el.getAttribute("aria-expanded") === "true" ? opcionesDe(listaDe(el)) : [];
    if (!opciones.length) {
      abrirCombo(el);
      opciones = await esperarOpciones(el, 1200);
    }
    const textos = opciones.map((o) => textoDe(o)).filter(Boolean);
    cerrarCombo(el);
    await dormir(100);
    const busqueda = textos.length === 0 || textos.length > 100;
    return { opciones: busqueda ? [] : textos, busqueda };
  }

  // Las opciones de Typeform empiezan por su atajo de teclado («A», «B»…): se quita
  function sinAtajos(textos) {
    const atajos = textos.map((t) => (t.match(/^([A-Z])\s+/) || [])[1]);
    const secuencia = atajos.every((a, i) => a === String.fromCharCode(65 + i));
    return secuencia && textos.length > 1 ? textos.map((t) => t.replace(/^[A-Z]\s+/, "")) : textos;
  }

  // Controles visibles que el usuario puede llenar, en orden del documento. Los radios y las
  // casillas nativos se agrupan por name; los ARIA, por su radiogroup.
  function buscarControles(reglas) {
    generico.fijo = contenedorFijo(reglas);
    generico.familia = (reglas || {}).familia || null;
    const banners = bannersCookies(reglas);
    const usados = new Set();
    const items = [];
    const grupos = new Map();
    const ambito = modalActivo(banners) || document;
    const gruposSinNombre = new Map();
    for (const el of ambito.querySelectorAll(CONTROLES)) {
      if (generico.fijo && !generico.fijo.contains(el)) continue;
      if (usados.has(el) || enZonaExcluida(el, banners) || excluido(el, reglas)) continue;
      if (esTrampa(el, reglas) || esClave(el) || RESPUESTA_CAPTCHA.test(`${el.name} ${el.id}`)) continue;
      if (el.disabled || el.readOnly || el.getAttribute("aria-disabled") === "true") continue;
      const rol = el.getAttribute("role");
      const t = (el.getAttribute("type") || "").toLowerCase();
      if (el.tagName === "INPUT" && ["hidden", "submit", "button", "reset", "image", "search"].includes(t)) continue;
      if (rol === "radiogroup") {
        const radios = [...el.querySelectorAll("[role=radio]")].filter(visibleGenerico);
        radios.forEach((r) => usados.add(r));
        if (visibleGenerico(el) && radios.length) items.push({ tipo: "aria_radio", el, elementos: radios });
        continue;
      }
      if (rol === "radio" && el.tagName !== "INPUT") {
        const padre = el.parentElement;
        const radios = [...padre.querySelectorAll(":scope > [role=radio]")].filter(visibleGenerico);
        radios.forEach((r) => usados.add(r));
        if (radios.length) items.push({ tipo: "aria_radio", el: padre, elementos: radios });
        continue;
      }
      if ((rol === "checkbox" || rol === "switch") && el.tagName !== "INPUT") {
        if (visibleGenerico(el)) items.push({ tipo: "aria_casilla", el });
        continue;
      }
      if (rol === "listbox") {
        // Lista visible por sí misma (no el desplegable de un combobox)
        const deCombo = document.querySelector(`[aria-controls="${CSS.escape(el.id || "-")}"]`);
        const opciones = [...el.querySelectorAll("[role=option]")].filter(visibleGenerico);
        opciones.forEach((o) => usados.add(o));
        if (!deCombo && visibleGenerico(el) && opciones.length) {
          items.push({ tipo: "aria_lista", el, elementos: opciones });
        }
        continue;
      }
      if (rol === "combobox" || (el.tagName === "BUTTON" && el.getAttribute("aria-haspopup") === "listbox")) {
        if (visibleGenerico(el)) items.push({ tipo: "combo", el });
        continue;
      }
      if (el.isContentEditable && el.tagName !== "INPUT" && el.tagName !== "TEXTAREA") {
        if (visibleGenerico(el)) items.push({ tipo: "editable", el });
        continue;
      }
      if (t === "file") {
        if (el.parentElement && visible(el.parentElement)) items.push({ tipo: "archivo", el });
        continue;
      }
      if (t === "radio" || t === "checkbox") {
        const lab = (el.id && document.querySelector(`label[for="${CSS.escape(el.id)}"]`)) || el.closest("label");
        if (!visibleGenerico(el) && !(lab && visibleGenerico(lab))) continue;
        if (t === "radio" || el.name) {
          let clave = `${t}:${el.name || el.id}`;
          if (t === "radio" && !el.name) {
            const caja = contenedorRadiosSinNombre(el, ambito);
            if (caja) {
              if (!gruposSinNombre.has(caja)) gruposSinNombre.set(caja, `radio_caja_${gruposSinNombre.size}`);
              clave = gruposSinNombre.get(caja);
            }
          }
          if (!grupos.has(clave)) {
            const grupo = { tipo: t, el, elementos: [] };
            grupos.set(clave, grupo);
            items.push(grupo);
          }
          grupos.get(clave).elementos.push(el);
        } else {
          items.push({ tipo: "casilla", el });
        }
        continue;
      }
      if (el.tagName === "SELECT") {
        if (visibleGenerico(el) && !esPrefijo(el)) items.push({ tipo: "select", el });
        continue;
      }
      if (visibleGenerico(el)) items.push({ tipo: tipoDe(el) === "fecha" ? "fecha" : "texto", el });
    }
    // Una casilla sola agrupada por name es una casilla de Sí/No
    for (const item of items) {
      if (item.tipo === "checkbox" && item.elementos.length === 1) {
        item.tipo = "casilla";
        item.el = item.elementos[0];
      }
    }
    return { items, banners };
  }

  // Contenedor del formulario: el <form> con más campos o, si no hay, el ancestro común más
  // cercano de los campos visibles (Ashby no usa <form>)
  function contenedorDe(items) {
    if (!items.length) return null;
    const conteo = new Map();
    for (const item of items) {
      const form = item.el.closest("form");
      if (form) conteo.set(form, (conteo.get(form) || 0) + 1);
    }
    if (conteo.size) return [...conteo.entries()].sort((a, b) => b[1] - a[1])[0][0];
    let comun = items[0].el.parentElement;
    while (comun && !items.every((i) => comun.contains(i.el))) comun = comun.parentElement;
    return comun || document.body;
  }

  // El CV va solo en el campo de archivo etiquetado como CV: el de «Autofill from resume» y
  // los que no tienen etiqueta (si hay uno etiquetado) no se reportan ni se llenan
  function sinArchivosDeRelleno(items) {
    const datos = new Map();
    for (const item of items.filter((i) => i.tipo === "archivo")) {
      const { texto, explicita } = etiquetaGenerica(item.el);
      const t = normalizar(limpiarEtiqueta(texto));
      const cvFamilia = deFamilia(item.el, (generico.familia || {}).cv);
      datos.set(item, { cv: cvFamilia || (tipoArchivo(t) === "cv" && explicita),
        sinEtiqueta: !explicita && !cvFamilia, autorrelleno: !cvFamilia && AUTORRELLENO.test(t) });
    }
    const hayCv = [...datos.values()].some((d) => d.cv && !d.autorrelleno);
    return items.filter((i) => {
      const d = datos.get(i);
      return !d || !(d.autorrelleno || (hayCv && d.sinEtiqueta));
    });
  }

  async function esquemaDe(items, idioma) {
    const campos = [];
    const salida = [];
    for (const item of items) {
      const { texto: crudo, explicita } = etiquetaGenerica(item.el);
      const texto = limpiarEtiqueta(crudo).slice(0, 1000);
      const el = item.el;
      const base = {
        texto,
        ayuda: ayudaDe(el),
        tipo: "texto",
        opciones: [],
        obligatoria: obligatoriaGenerica(el, crudo),
        nombre: el.name || el.id || el.getAttribute("data-automation-id") || null,
        autocomplete: (el.getAttribute("autocomplete") || "").toLowerCase() || null,
        maximo: null,
        accept: null,
        idioma,
        busqueda: false,
      };
      if (["off", "on"].includes(base.autocomplete)) base.autocomplete = null;
      const campo = { ...item };
      if (item.tipo === "radio" || item.tipo === "checkbox") {
        base.tipo = "opciones";
        base.texto = limpiarEtiqueta(leyendaDeGrupo(item.elementos) || el.name || "");
        base.opciones = item.elementos.map((x) => limpiarEtiqueta(etiquetaGenerica(x).texto));
        base.obligatoria = item.elementos.some(requerido) || base.obligatoria;
        base.nombre = el.name || null;
      } else if (item.tipo === "casilla" || item.tipo === "aria_casilla") {
        base.tipo = "opciones";
        base.opciones = ["Sí", "No"];
      } else if (item.tipo === "aria_radio" || item.tipo === "aria_lista") {
        base.tipo = "opciones";
        base.opciones = sinAtajos(item.elementos.map((x) => textoDe(x)));
      } else if (item.tipo === "select") {
        base.tipo = "opciones";
        campo.indices = [];
        [...el.options].forEach((o, i) => {
          if (o.value === "" || o.disabled) return;
          base.opciones.push(o.textContent.trim());
          campo.indices.push(i);
        });
        if (base.opciones.length > 100) {
          base.busqueda = true;
          base.opciones = [];
        }
      } else if (item.tipo === "combo") {
        base.tipo = "opciones";
        const leidas = await leerOpcionesCombo(el);
        base.opciones = leidas.opciones;
        base.busqueda = leidas.busqueda;
        campo.opciones = leidas.opciones;
      } else if (item.tipo === "archivo") {
        base.tipo = "archivo";
        base.accept = el.getAttribute("accept") || null;
        campo.documento = deFamilia(el, (generico.familia || {}).cv) ? "cv"
          : explicita ? tipoArchivo(texto) : null;
      } else {
        base.tipo = tipoDe(el);
        base.maximo = maximoDe(el);
        campo.telefono = base.tipo === "telefono";
        campo.prefijo = campo.telefono ? prefijoDe(el) : null;
      }
      campos.push(campo);
      salida.push(base);
    }
    return { campos, salida };
  }

  // --- botones -------------------------------------------------------------------------------

  function textoBoton(el) {
    const t = (el.tagName === "INPUT" ? el.value : textoDe(el)) || el.getAttribute("aria-label")
      || el.getAttribute("title") || "";
    return t.replace(/\s+/g, " ").trim().slice(0, 80);
  }

  function clasificarBoton(texto, reglas, sinCampos) {
    if (coincide(texto, frases(reglas, "oauth"))) return "nunca";
    if (coincide(texto, frases(reglas, "nunca"))) return "nunca";
    if (sinCampos && coincide(texto, frases(reglas, "intermedia"))) return "intermedia";
    if (coincide(texto, frases(reglas, "enviar"))) return "enviar";
    if (coincide(texto, frases(reglas, "avanzar"))) return "avanzar";
    return null;
  }

  // El botón de enviar que declara la familia de ATS gana sobre los textos genéricos
  function claseDeBoton(el, texto, reglas, sinCampos) {
    const clase = clasificarBoton(texto, reglas, sinCampos);
    const enviar = ((generico.familia || {}).enviar || {}).selectores;
    return clase !== "nunca" && deFamilia(el, enviar) ? "enviar" : clase;
  }

  // Botones del contenedor y los de justo debajo; sin contenedor, los de la página
  function leerBotones(contenedor, reglas, banners, sinCampos) {
    const salida = [];
    const elementos = [];
    const abajo = contenedor ? contenedor.getBoundingClientRect().bottom : 0;
    const ambito = modalActivo(banners) || document;
    const todos = ambito.querySelectorAll("button, input[type=submit], input[type=button], [role=button], a[href]");
    for (const el of todos) {
      if (!visibleGenerico(el) || enZonaExcluida(el, banners)) continue;
      if (el.closest("[role=listbox]") || el.closest("[role=combobox]")) continue;
      if (contenedor && !contenedor.contains(el)) {
        if (generico.fijo) continue;
        const despues = contenedor.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING;
        const margen = ambito === document ? 300 : 2000;
        if (!despues || el.getBoundingClientRect().top - abajo > margen) continue;
      }
      const texto = textoBoton(el);
      if (!texto) continue;
      const tipo = el.tagName === "A" ? "enlace" : ((el.getAttribute("type") || "").toLowerCase()
        || (el.tagName === "BUTTON" && el.closest("form") ? "submit" : "button"));
      elementos.push(el);
      salida.push({
        indice: salida.length,
        texto,
        clase: claseDeBoton(el, texto, reglas, sinCampos),
        oauth: coincide(texto, frases(reglas, "oauth")),
        tipo,
        en_contenedor: Boolean(contenedor && contenedor.contains(el)),
      });
    }
    generico.botones = elementos;
    generico.clases = salida.map((b) => b.clase);
    return salida;
  }

  // El botón que las reglas eligen, o null si dudan (decide el árbitro)
  function botonSugerido(botones, clase) {
    const de = (c) => botones.filter((b) => b.clase === c);
    const unico = (lista) => {
      if (lista.length === 1) return lista[0];
      const submits = lista.filter((b) => b.tipo === "submit");
      return submits.length === 1 ? submits[0] : null;
    };
    if (clase === "intermedia") {
      const intermedios = de("intermedia");
      const elegido = unico(intermedios.length ? intermedios : de("avanzar"));
      return elegido ? { indice: elegido.indice, accion: "avanzar" } : null;
    }
    if (clase !== "formulario" && clase !== "error") return null;
    const enviar = de("enviar");
    if (enviar.length) {
      const elegido = unico(enviar);
      return elegido ? { indice: elegido.indice, accion: "enviar" } : null;
    }
    const avanzar = de("avanzar");
    if (avanzar.length) {
      const elegido = unico(avanzar);
      return elegido ? { indice: elegido.indice, accion: "avanzar" } : null;
    }
    // Sin textos conocidos, un único submit del contenedor gana
    const submits = botones.filter((b) => b.clase === null && b.tipo === "submit" && b.en_contenedor);
    return submits.length === 1 ? { indice: submits[0].indice, accion: "enviar" } : null;
  }

  // --- barreras y resultado --------------------------------------------------------------------

  function desafioVisible(reglas) {
    const captcha = (reglas || {}).captcha || {};
    const minimo = captcha.tamano_minimo || 30;
    return (captcha.desafio || []).flatMap((s) => candidatos(s)).some((el) => {
      if (!visible(el) || !dentroDePantalla(el)) return false;
      const r = el.getBoundingClientRect();
      return r.width >= minimo && r.height >= minimo && getComputedStyle(el).opacity !== "0";
    });
  }

  // Textos visibles «junto al formulario»: encabezados, botones y etiquetas
  function textosCercanos(contenedor, banners) {
    const raiz = contenedor || document.body;
    const nodos = [...document.querySelectorAll("h1, h2, h3, [role=heading]"),
      ...raiz.querySelectorAll("button, [role=button], a, label, legend")];
    return nodos.filter((n) => visible(n) && !banners.some((b) => b.contains(n)))
      .map((n) => textoDe(n)).filter(Boolean);
  }

  function barreraDe(reglas, contenedor, items, botones, banners) {
    const visibles = [...document.querySelectorAll("input")].filter((i) => visibleGenerico(i));
    if (visibles.some(esClave)) return "ats_con_cuenta";
    if (desafioVisible(reglas) || hayTexto(frases(reglas, "captcha"))) return "captcha";
    const codigo = visibles.some((i) => /one-time-code/i.test(i.getAttribute("autocomplete") || ""))
      || items.some((i) => coincide(etiquetaGenerica(i.el).texto, frases(reglas, "verificacion")));
    if (codigo) return "codigo_verificacion";
    if (textosCercanos(contenedor, banners).some((t) => coincide(t, frases(reglas, "barrera")))) {
      return "ats_con_cuenta";
    }
    const caminos = botones.filter((b) => ["enviar", "avanzar", "intermedia"].includes(b.clase));
    if (!items.length && botones.some((b) => b.oauth) && !caminos.length) return "oauth";
    return null;
  }

  function encabezados() {
    return [...document.querySelectorAll("h1, h2, h3")].filter(visible)
      .map((h) => textoDe(h).slice(0, 120)).filter(Boolean).slice(0, 10);
  }

  function avisos(contenedor) {
    const raiz = contenedor || document.body;
    return [...raiz.querySelectorAll("[role=alert], [aria-live=assertive], .field-validation-error, .error, .error-text")]
      .filter(visible).map((a) => textoDe(a).slice(0, 160)).filter(Boolean).slice(0, 10);
  }

  function exitoDe(reglas, sinCampos) {
    const url = location.href.toLowerCase();
    const porUrl = ((reglas || {}).url_exito || []).some((p) => url.includes(p.toLowerCase()));
    const lista = frases(reglas, "exito");
    const marcas = ((((reglas || {}).familia || {}).exito) || {}).selectores || [];
    const marca = marcas.flatMap((s) => candidatos(s)).find(visible);
    if (marca) return { senal: "selector", texto: textoDe(marca).slice(0, 200) };
    const dialogo = [...document.querySelectorAll("[role=dialog], [role=alert], [aria-modal=true], dialog[open]")]
      .some((d) => visible(d) && coincide(textoDe(d), lista));
    if (dialogo) return { senal: "texto", texto: textoPagina().slice(0, 200) };
    if (!sinCampos) return null;
    const visibleTexto = document.body ? document.body.innerText : "";
    const frase = lista.find((f) => coincide(visibleTexto, [f]));
    if (frase) return { senal: "texto", texto: frase.slice(0, 200) };
    return porUrl ? { senal: "url", texto: location.pathname.slice(0, 200) } : null;
  }

  function hayErrores(contenedor) {
    const raiz = contenedor || document.body;
    const invalidos = [...raiz.querySelectorAll("[aria-invalid=true]")].filter(visible);
    return invalidos.length > 0 || avisos(contenedor).length > 0;
  }

  // Firma de la pantalla: las claves de sus campos (nombre o texto normalizado), ordenadas
  function firmaDe(items) {
    const clave = (i) => i.el.name || i.el.id || i.el.getAttribute("data-automation-id")
      || limpiarEtiqueta(etiquetaGenerica(i.el).texto);
    return [...new Set(items.map((i) => normalizar(clave(i)).slice(0, 60)))].sort();
  }

  // Campos del formulario de la pantalla actual, sin abrir listas
  function camposActuales(reglas) {
    const { items, banners } = buscarControles(reglas);
    const contenedor = generico.fijo || contenedorDe(items);
    const dentro = contenedor ? sinArchivosDeRelleno(items.filter((i) => contenedor.contains(i.el))) : [];
    return { contenedor, dentro, banners };
  }

  // --- resumen sin valores para el árbitro ---------------------------------------------------

  // Lista numerada de lo visible e interactivo. Nunca lee value, checked ni files: de los
  // campos solo su etiqueta; de los botones, su texto.
  function resumenDe(contenedor, banners) {
    const elementos = [];
    const lista = [];
    const ambito = modalActivo(banners) || document;
    for (const el of ambito.querySelectorAll(INTERACTIVOS)) {
      if (lista.length >= MAX_RESUMEN) break;
      if (!visibleGenerico(el) || esClave(el)) continue;
      const t = (el.getAttribute("type") || "").toLowerCase();
      if (el.tagName === "INPUT" && t === "hidden") continue;
      const campo = ["INPUT", "SELECT", "TEXTAREA"].includes(el.tagName) && !["submit", "button", "reset"].includes(t)
        || ["combobox", "radio", "checkbox", "switch"].includes(el.getAttribute("role"))
        || el.isContentEditable;
      const texto = campo ? limpiarEtiqueta(etiquetaGenerica(el).texto) : textoBoton(el);
      elementos.push(el);
      lista.push({
        indice: lista.length,
        rol: el.getAttribute("role") || (el.tagName === "A" ? "link" : el.tagName.toLowerCase()),
        texto: texto.slice(0, 80),
        tipo: t || null,
        en_contenedor: Boolean(contenedor && contenedor.contains(el)),
        cookies: banners.some((b) => b.contains(el)),
      });
    }
    const resumen = { elementos: lista, encabezados: encabezados(), avisos: avisos(contenedor) };
    while (JSON.stringify(resumen).length > MAX_BYTES_RESUMEN && resumen.elementos.length) {
      resumen.elementos.pop();
      elementos.pop();
    }
    generico.elementos = elementos;
    return resumen;
  }

  // --- cookies -------------------------------------------------------------------------------

  function tapa(banner, items) {
    const r = banner.getBoundingClientRect();
    if (r.width * r.height >= innerWidth * innerHeight * 0.5) return true;
    return items.some((i) => {
      const c = i.el.getBoundingClientRect();
      const punto = document.elementFromPoint(c.left + c.width / 2, c.top + c.height / 2);
      return punto && banner.contains(punto);
    });
  }

  // Rechaza las cookies no esenciales si el banner lo permite; si solo ofrece aceptar, no se
  // pulsa nada (aceptar es un consentimiento)
  async function atenderCookies(reglas) {
    const banners = bannersCookies(reglas);
    if (!banners.length) return null;
    for (const banner of banners) {
      const boton = [...banner.querySelectorAll("button, [role=button], a")]
        .find((b) => visible(b) && coincide(textoBoton(b), frases(reglas, "cookies_rechazar")));
      if (boton) {
        boton.click();
        await dormir(500);
        return "rechazadas";
      }
    }
    const { items } = buscarControles({ ...reglas, cookies: { banner: [] } });
    return banners.some((b) => tapa(b, items)) ? "tapa" : "sin_tocar";
  }

  // --- leer la pantalla ----------------------------------------------------------------------

  async function leerPantalla(reglas) {
    const cookies = await atenderCookies(reglas);
    const idioma = idiomaPagina();
    const { contenedor, dentro, banners } = camposActuales(reglas);
    const { campos, salida } = await esquemaDe(dentro, idioma);
    generico.campos = campos;
    generico.contenedor = contenedor;
    const botones = leerBotones(contenedor, reglas, banners, salida.length === 0);
    let clase;
    let motivo = barreraDe(reglas, contenedor, dentro, botones, banners);
    let exito = null;
    if (motivo) clase = "barrera";
    else if ((exito = exitoDe(reglas, salida.length === 0))) clase = "exito";
    else if (salida.length && hayErrores(contenedor)) clase = "error";
    else if (salida.length) clase = "formulario";
    // Pantalla de revisión: sin campos y con el botón de enviar (Typeform, el paso final de un ATS)
    else if (botones.some((b) => b.clase === "enviar")) clase = "formulario";
    else if (botones.some((b) => b.clase === "intermedia" || b.clase === "avanzar")) clase = "intermedia";
    else clase = "desconocida";
    if (clase !== "barrera") motivo = null;
    return {
      clase,
      motivo,
      exito,
      idioma,
      cookies,
      url: location.origin + location.pathname,
      campos: salida,
      botones,
      sugerido: botonSugerido(botones, clase),
      firma: firmaDe(dentro),
      resumen: resumenDe(contenedor, banners),
    };
  }

  // Resultado tras pulsar avanzar o enviar, comparado con la pantalla anterior (`previo`: su
  // firma, su URL, sus encabezados y la acción pulsada). Espera hasta `ms` mientras nada cambie.
  // No abre listas.
  async function resultado(reglas, previo = {}, ms = 0) {
    const limite = Date.now() + ms;
    do {
      const { contenedor, dentro, banners } = camposActuales(reglas);
      const motivo = barreraDe(reglas, contenedor, dentro, [], banners);
      if (motivo) return { resultado: "barrera", motivo };
      const exito = exitoDe(reglas, dentro.length === 0);
      if (exito) return { resultado: "exito", ...exito };
      if (dentro.length && contenedor && [...contenedor.querySelectorAll("[aria-invalid=true]")].some(visible)) {
        return { resultado: "error", avisos: avisos(contenedor) };
      }
      const url = location.origin + location.pathname;
      const otraUrl = Boolean(previo.url) && url !== previo.url;
      const otraFirma = JSON.stringify(firmaDe(dentro)) !== JSON.stringify(previo.firma || []);
      const otrosEncabezados = JSON.stringify(encabezados()) !== JSON.stringify(previo.encabezados || []);
      // Tras enviar, el formulario desaparece y aparece un encabezado nuevo: también es éxito
      if (previo.accion === "enviar" && !dentro.length && (previo.firma || []).length && otrosEncabezados) {
        return { resultado: "exito", senal: "desaparicion", texto: encabezados().join(" · ").slice(0, 200) };
      }
      if (dentro.length && (otraFirma || otraUrl)) return { resultado: "campos_nuevos" };
      if (avisos(contenedor).length && dentro.length) return { resultado: "error", avisos: avisos(contenedor) };
      // Otra pantalla sin campos (revisión, página intermedia): se vuelve a leer
      if (otraUrl || otrosEncabezados || (!dentro.length && otraFirma)) return { resultado: "pantalla_nueva" };
      if (Date.now() >= limite) break;
      await dormir(500);
    } while (true);
    return { resultado: "sin_cambios" };
  }

  // Evidencia del contenedor sin valores: además de lo que borra htmlSinValores, el texto que
  // muestran los combobox (la opción elegida, por ejemplo la ciudad)
  function htmlGenerico() {
    const raiz = generico.contenedor || document.body;
    const marcados = [];
    for (const combo of raiz.querySelectorAll("[role=combobox], button[aria-haspopup=listbox]")) {
      if (combo.tagName !== "INPUT") {
        marcados.push(combo);
        continue;
      }
      for (const n of bloqueDe(combo).querySelectorAll("*")) {
        if (!n.children.length && !n.closest("label, [role=listbox], button")) marcados.push(n);
      }
    }
    marcados.forEach((n) => n.setAttribute("data-asistente-valor", ""));
    try {
      const copia = raiz.cloneNode(true);
      copia.querySelectorAll("[data-asistente-valor]").forEach((n) => {
        n.textContent = "";
        n.removeAttribute("data-asistente-valor");
      });
      return htmlSinValores(copia);
    } finally {
      marcados.forEach((n) => n.removeAttribute("data-asistente-valor"));
    }
  }

  // --- llenado comprobado ----------------------------------------------------------------------

  // Escribe sin soltar el foco: un combobox cierra su lista al perderlo
  function escribir(el, valor) {
    const proto = el.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, "value").set.call(el, valor);
    el.dispatchEvent(new Event("input", { bubbles: true }));
  }

  const linea = (t) => String(t).replace(/\r\n?/g, "\n");

  function mejorOpcion(opciones, deseado) {
    const d = normalizar(deseado);
    const textos = opciones.map((o) => normalizar(textoDe(o)));
    let i = textos.findIndex((t) => t === d);
    if (i < 0) i = textos.findIndex((t) => t.startsWith(d));
    if (i < 0) i = textos.findIndex((t) => t.includes(d));
    return i < 0 ? null : opciones[i];
  }

  // Bloque de un combobox: el ancestro más grande que no llega a la etiqueta ni a otro campo
  function bloqueDe(el) {
    let bloque = el.parentElement;
    for (let i = 0; bloque && i < 6; i++) {
      const padre = bloque.parentElement;
      if (!padre) break;
      const otros = [...padre.querySelectorAll(CONTROLES)].filter((x) => x !== el && visibleGenerico(x));
      if (otros.length || padre.querySelector("label") || padre === document.body) break;
      bloque = padre;
    }
    return bloque;
  }

  // Texto que muestra un combobox: el de su bloque, sin la etiqueta, la lista ni los avisos
  function mostradoDe(el) {
    if (el.tagName !== "INPUT") return textoDe(el);
    const bloque = bloqueDe(el);
    const partes = [];
    const recorrido = document.createTreeWalker(bloque, NodeFilter.SHOW_TEXT);
    while (recorrido.nextNode()) {
      const nodo = recorrido.currentNode;
      const padre = nodo.parentElement;
      if (!padre || !visible(padre)) continue;
      if (padre.closest("label, [role=listbox], [role=log], [aria-live], button")) continue;
      if (el.getAttribute("aria-describedby") && textoPorIds(el.getAttribute("aria-describedby")).includes(nodo.textContent.trim())) continue;
      partes.push(nodo.textContent);
    }
    const ocultos = [...bloque.querySelectorAll("input")].filter((x) => x !== el).map((x) => x.value);
    return [partes.join(" "), ...ocultos].join(" ").replace(/\s+/g, " ").trim();
  }

  async function elegirEnCombo(campo, r) {
    const el = campo.el;
    const deseado = r.opcion != null && campo.opciones && campo.opciones[r.opcion] != null
      ? campo.opciones[r.opcion] : r.valor;
    if (deseado == null) return null;
    el.scrollIntoView({ block: "center" });
    if (el.tagName === "INPUT") {
      el.focus();
      escribir(el, String(deseado));
    } else {
      abrirCombo(el);
    }
    const opciones = await esperarOpciones(el, 3000);
    const opcion = mejorOpcion(opciones, String(deseado));
    if (!opcion) {
      cerrarCombo(el);
      return "ninguna opción de la lista coincide con la respuesta";
    }
    const elegida = textoDe(opcion);
    opcion.scrollIntoView({ block: "nearest" });
    clicCompleto(opcion);
    await dormir(250);
    if (!normalizar(mostradoDe(el)).includes(normalizar(elegida))) {
      return "la opción elegida no quedó mostrada en la lista";
    }
    return true;
  }

  // Fecha en el formato del placeholder (dd/mm/aaaa, mm/dd/yyyy…) a partir de AAAA-MM-DD
  function fechaComo(valor, placeholder) {
    const m = String(valor).match(/^(\d{4})-(\d{2})-(\d{2})$/);
    const formato = normalizar(placeholder).replace(/a/g, "y");
    if (!m || !/(dd|mm|yy)/.test(formato)) return String(valor);
    const [, anio, mes, dia] = m;
    return formato.replace("yyyy", anio).replace("yy", anio.slice(2)).replace("mm", mes).replace("dd", dia);
  }

  async function escribirTexto(campo, r) {
    if (r.valor == null) return null;
    const el = campo.el;
    let valor = String(r.valor);
    el.scrollIntoView({ block: "center" });
    if (campo.tipo === "editable") {
      el.focus();
      el.textContent = valor;
      el.dispatchEvent(new Event("input", { bubbles: true }));
      el.blur();
      await dormir(150);
      return linea(el.textContent) === linea(valor) || "el texto no quedó escrito";
    }
    if (campo.tipo === "fecha" && el.type !== "date") valor = fechaComo(valor, el.getAttribute("placeholder"));
    if (campo.tipo === "texto" && el.getAttribute("placeholder") && /^\d{4}-\d{2}-\d{2}$/.test(valor)) {
      valor = fechaComo(valor, el.getAttribute("placeholder"));
    }
    if (campo.telefono && campo.prefijo) {
      // Prefijo del país en su lista y el número sin él (+57 si la respuesta no trae otro)
      const codigo = (valor.match(/^\+\s?(\d{1,3})/) || [null, "57"])[1];
      valor = valor.replace(/^\+\s?\d{1,3}[\s-]*/, "");
      const i = [...campo.prefijo.options].findIndex((o) => new RegExp(`\\+\\s?${codigo}\\b`).test(o.textContent));
      if (i < 0) return "el prefijo del teléfono no está en la lista";
      campo.prefijo.selectedIndex = i;
      campo.prefijo.dispatchEvent(new Event("change", { bubbles: true }));
    }
    asignarValor(el, valor);
    await dormir(150);
    if (campo.telefono) {
      const digitos = (t) => String(t).replace(/\D/g, "");
      return digitos(el.value).endsWith(digitos(valor)) || "el teléfono no quedó escrito";
    }
    return linea(el.value) === linea(valor) || "el texto no quedó escrito en el campo";
  }

  async function marcarAria(el, activo) {
    if ((el.getAttribute("aria-checked") === "true") !== activo) {
      el.scrollIntoView({ block: "center" });
      clicCompleto(el);
      await dormir(200);
    }
    return (el.getAttribute("aria-checked") === "true") === activo;
  }

  function adjuntarComprobado(el, archivo) {
    adjuntar(el, archivo);
    return (el.files && el.files.length && el.files[0].name === archivo.nombre) || "el archivo no quedó adjunto";
  }

  async function llenarCampo(campo, r, archivos) {
    switch (campo.tipo) {
      case "texto":
      case "fecha":
      case "editable":
        return escribirTexto(campo, r);
      case "combo":
        return elegirEnCombo(campo, r);
      case "select": {
        const el = campo.el;
        let indice = r.opcion != null ? campo.indices[r.opcion] : null;
        if (indice == null && r.valor != null) {
          const o = mejorOpcion([...el.options].filter((x) => x.value !== ""), String(r.valor));
          indice = o ? o.index : null;
        }
        if (indice == null) return r.opcion == null && r.valor == null ? null : "la opción no está en la lista";
        el.focus();
        el.selectedIndex = indice;
        el.dispatchEvent(new Event("input", { bubbles: true }));
        el.dispatchEvent(new Event("change", { bubbles: true }));
        el.blur();
        return el.selectedIndex === indice || "la opción no quedó elegida";
      }
      case "radio":
      case "checkbox": {
        if (r.opcion == null) return null;
        const el = campo.elementos[r.opcion];
        if (!el) return "la opción no existe";
        marcar(el, true);
        await dormir(100);
        return el.checked || "la opción no quedó marcada";
      }
      case "casilla": {
        if (r.opcion == null) return null;
        marcar(campo.el, r.opcion === 0);
        await dormir(100);
        return campo.el.checked === (r.opcion === 0) || "la casilla no quedó como se quería";
      }
      case "aria_casilla":
        if (r.opcion == null) return null;
        return (await marcarAria(campo.el, r.opcion === 0)) || "la casilla no quedó como se quería";
      case "aria_radio":
      case "aria_lista": {
        if (r.opcion == null) return null;
        const el = campo.elementos[r.opcion];
        if (!el) return "la opción no existe";
        el.scrollIntoView({ block: "center" });
        clicCompleto(el);
        await dormir(200);
        const marcado = el.getAttribute("aria-checked") === "true" || el.getAttribute("aria-selected") === "true";
        return marcado || "la opción elegida no quedó marcada";
      }
      case "archivo": {
        const clave = r.documento || campo.documento;
        const archivo = clave && archivos[clave];
        if (!archivo) return r.documento ? `falta el documento ${r.documento}` : null;
        return adjuntarComprobado(campo.el, archivo);
      }
      default:
        return null;
    }
  }

  // `respuestas`: [{indice, valor, opcion, documento}] sobre el esquema de la última pantalla.
  // `archivos`: {cv: {nombre, base64}, certificado_notas: {…}…}. Un campo de archivo sin
  // respuesta recibe el documento que corresponde a su etiqueta, si lo hay. Un campo que no
  // quedó como se quería corta el llenado: no se avanza ni se envía.
  async function llenarGenerico(respuestas, archivos = {}) {
    const escritas = [];
    const adjuntos = [];
    const fallo = (indice, motivo) => ({ error: "formulario_desconocido", campo: indice,
      motivo: `llenar: campo ${indice + 1}: ${motivo}`, escritas, html: htmlGenerico() });
    const respondidos = new Set();
    for (const r of respuestas || []) {
      const campo = generico.campos[r.indice];
      if (!campo) continue;
      respondidos.add(r.indice);
      const ok = await llenarCampo(campo, r, archivos);
      if (ok === null) continue;
      if (ok !== true) return fallo(r.indice, ok);
      if (campo.tipo === "archivo") adjuntos.push(r.indice + 1);
      escritas.push(r.indice + 1);
      await pausa(80, 200);
    }
    for (const [i, campo] of generico.campos.entries()) {
      if (campo.tipo !== "archivo" || respondidos.has(i) || !campo.documento) continue;
      const archivo = archivos[campo.documento];
      if (!archivo || (campo.el.files && campo.el.files.length)) continue;
      const ok = adjuntarComprobado(campo.el, archivo);
      if (ok !== true) return fallo(i, ok);
      adjuntos.push(i + 1);
      escritas.push(i + 1);
    }
    return { ok: true, escritas, adjuntos };
  }

  // Antes de leer cada pantalla de un modal declarado (la Solicitud sencilla de LinkedIn):
  // desmarca las casillas de `desmarcar` («Sigue a …», que viene marcada) y deja resuelto el
  // CV: con `subir_cv` pulsa el botón que hace aparecer el campo de archivo; si no, elige el
  // primer CV guardado. Sin ninguno guardado ni autorización para subir, `sin_cv`.
  async function prepararModal(def, { subir_cv: subirCv = false } = {}) {
    const raiz = buscar(def.contenedor || []);
    if (!raiz) return { sin_modal: true };
    let desmarcadas = 0;
    for (const s of def.desmarcar || []) {
      for (const el of candidatos(s, raiz)) {
        if (!el.checked && el.getAttribute("aria-checked") !== "true") continue;
        el.click();
        desmarcadas += 1;
      }
    }
    const grupo = buscar(def.cv_grupo || [], { raiz, ocultos: true });
    if (!grupo) return { ok: true, desmarcadas };
    const archivo = () => raiz.querySelector("input[type=file]");
    if (subirCv) {
      if (!archivo()) {
        const boton = [...raiz.querySelectorAll("button, [role=button]")]
          .find((b) => visible(b) && normalizar(textoBoton(b)).includes(normalizar(def.cv_subir || "")));
        if (boton) boton.click();
        const limite = Date.now() + 3000;
        while (!archivo() && Date.now() < limite) await dormir(200);
      }
      if (archivo()) return { ok: true, desmarcadas, cv: "subir" };
    }
    const opciones = [...grupo.querySelectorAll("input[type=radio], [role=radio]")];
    if (!opciones.length) return { sin_cv: true, desmarcadas };
    const marcada = (o) => o.checked || o.getAttribute("aria-checked") === "true";
    if (!opciones.some(marcada)) {
      opciones[0].click();
      await dormir(200);
    }
    return opciones.some(marcada) ? { ok: true, desmarcadas, cv: "guardado" } : { sin_cv: true, desmarcadas };
  }

  // Cierra el modal sin enviar ni guardar: la X y, en el aviso «¿Quieres guardar esta
  // solicitud?», «Descartar» (nunca «Guardar», que deja un borrador en la cuenta)
  async function descartarModal(def) {
    const x = buscar(def.cerrar || []);
    if (!x) return { cerrado: false };
    x.click();
    const limite = Date.now() + 3000;
    while (Date.now() < limite) {
      const aviso = buscar(def.aviso || []);
      if (aviso) {
        // Por su texto visible: la X del aviso también se llama «Descartar» (aria-label), pero
        // solo cierra el aviso y deja el modal abierto
        const boton = [...aviso.querySelectorAll("button")]
          .find((b) => visible(b) && normalizar(b.textContent) === normalizar(def.descartar || "descartar"));
        if (boton) {
          boton.click();
          // Se espera a que LinkedIn cierre el modal: cerrar la pestaña antes cortaría el descarte
          const fin = Date.now() + 3000;
          while (buscar(def.contenedor || []) && Date.now() < fin) await dormir(200);
          return { cerrado: !buscar(def.contenedor || []), descartado: true };
        }
      }
      if (!buscar(def.contenedor || [])) return { cerrado: true };
      await dormir(200);
    }
    return { cerrado: false };
  }

  // Pulsa un botón leído en la última pantalla. Un botón `nunca` no se pulsa. El clic va
  // después de responder, porque puede navegar y terminar este script.
  async function pulsar(indice, { esperar_habilitado: esperarHabilitado = 10000 } = {}) {
    const el = generico.botones[indice];
    if (!el || !el.isConnected) return { error: "formulario_desconocido", motivo: "pulsar: el botón ya no está" };
    if (generico.clases[indice] === "nunca") {
      return { error: "formulario_desconocido", motivo: "pulsar: ese botón nunca se pulsa" };
    }
    const limite = Date.now() + esperarHabilitado;
    while ((el.disabled || el.getAttribute("aria-disabled") === "true") && Date.now() < limite) await dormir(250);
    if (el.disabled || el.getAttribute("aria-disabled") === "true") {
      return { error: "formulario_desconocido", motivo: "pulsar: el botón sigue deshabilitado" };
    }
    el.scrollIntoView({ block: "center" });
    setTimeout(() => el.click(), 50);
    return { ok: true, texto: textoBoton(el) };
  }

  // --- selector estable ----------------------------------------------------------------------

  function idGenerado(id) {
    return !/^[A-Za-z][\w-]*$/.test(id) || /\d{3,}/.test(id) || id.length > 50
      || /^(react-select|mui-|ember|radix-|headlessui-|input-\d)/.test(id)
      || /[0-9a-f]{8}-[0-9a-f]{4}/i.test(id);
  }

  function primero(selector) {
    const lista = candidatos(selector);
    return lista.find(visible) || lista[0] || null;
  }

  // Selector que vuelve a encontrar `el`, del más estable al menos: id no generado, name,
  // data-automation-id/data-qa/data-testid, aria-label y, por último, {css, texto}. Lo calcula
  // la extensión sobre el elemento real; la IA nunca lo escribe.
  function selectorEstable(el) {
    if (!el) return null;
    const tag = el.tagName.toLowerCase();
    const unico = (s) => {
      const lista = candidatos(s);
      return lista.length === 1 && lista[0] === el ? s : null;
    };
    const atributo = (nombre) => {
      const v = el.getAttribute(nombre);
      return v ? unico(`${tag}[${nombre}="${CSS.escape(v)}"]`) : null;
    };
    const porId = el.id && !idGenerado(el.id) ? unico(`#${CSS.escape(el.id)}`) : null;
    const elegido = porId || atributo("name") || atributo("data-automation-id")
      || atributo("data-qa") || atributo("data-testid") || atributo("aria-label");
    if (elegido) return elegido;
    const texto = textoBoton(el);
    if (texto) {
      const rol = el.getAttribute("role");
      const css = rol ? `[role="${rol}"]` : tag;
      const def = { css, texto };
      if (primero(def) === el) return def;
    }
    // Ruta desde el ancestro con id estable más cercano
    const partes = [];
    let nodo = el;
    while (nodo && nodo !== document.body) {
      if (nodo.id && !idGenerado(nodo.id) && nodo !== el) {
        partes.unshift(`#${CSS.escape(nodo.id)}`);
        break;
      }
      const hermanos = [...nodo.parentElement.children].filter((h) => h.tagName === nodo.tagName);
      partes.unshift(`${nodo.tagName.toLowerCase()}:nth-of-type(${hermanos.indexOf(nodo) + 1})`);
      nodo = nodo.parentElement;
    }
    const ruta = partes.join(" > ");
    return candidatos(ruta)[0] === el ? ruta : null;
  }

  // Un campo, un botón o un elemento del resumen de la última pantalla
  function elementoDe({ campo, boton, elemento }) {
    return campo != null ? (generico.campos[campo] || {}).el
      : boton != null ? generico.botones[boton] : generico.elementos[elemento];
  }

  function selectorDe(objetivo) {
    return selectorEstable(elementoDe(objetivo));
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
    abrirCuenta,
    esperarCorreo,
    correoPorHtml,
    enlacesCuenta,
    sesion: (sel) => ({ sin_sesion: sinSesion(sel), captcha: hayCaptcha(sel) }),
    html: () => htmlSinValores(),
    // Motor genérico: `reglas` es el contenido de motor_generico.json que entrega el servidor
    generico: {
      leerPantalla,
      llenar: llenarGenerico,
      pulsar,
      resultado,
      selectorDe,
      selectorEstable,
      elemento: elementoDe,
      encontrar: primero, // el elemento al que apunta un selector de receta o de parche
      html: htmlGenerico,
      prepararModal,
      descartarModal,
    },
    api,
  };
})();
