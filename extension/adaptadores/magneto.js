// Adaptador de Magneto. El flujo y los selectores llegan del servidor
// (assets/selectores/magneto.json); aquí solo va lo que no se puede expresar como datos.

(() => {
  const motor = globalThis.__asistente;
  if (!motor || motor.magneto) return;
  motor.magneto = true;

  motor.registrar("magneto", {
    // Magneto es una aplicación de una sola página: tras un clic no hay carga nueva, así que
    // se espera a que el contenido cambie antes de seguir.
    async clic(paso, _sel, api) {
      if (!paso.esperar_cambio) return undefined;
      const el = await api.esperar(paso.selector, paso.ms || 10000);
      if (!el) return undefined;
      const antes = document.body.innerText.length;
      await api.pausa(300, 800);
      el.scrollIntoView({ block: "center" });
      el.click();
      const limite = Date.now() + 8000;
      while (Date.now() < limite && document.body.innerText.length === antes) await api.dormir(250);
      return { ok: true };
    },
  });
})();
