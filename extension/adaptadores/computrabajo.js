// Adaptador de Computrabajo. El flujo y los selectores llegan del servidor
// (assets/selectores/computrabajo.json); aquí solo va lo que no se puede expresar como datos.

(() => {
  const motor = globalThis.__asistente;
  if (!motor || motor.computrabajo) return;
  motor.computrabajo = true;

  motor.registrar("computrabajo", {
    // El botón "Aplicar" guarda la URL de postulación en un atributo; si falta el atributo
    // (versión vieja de la página) se usa el enlace de acceso o el href.
    async ir(paso, _sel, api) {
      if (paso.atributo !== "data-href-offer-apply") return undefined;
      const el = await api.esperar(paso.selector, paso.ms || 10000, { ocultos: true });
      if (!el) return undefined;
      const url = el.getAttribute("data-href-offer-apply") || el.getAttribute("data-href-access") || el.href;
      return url ? { ir: new URL(url, location.href).href } : undefined;
    },
  });
})();
