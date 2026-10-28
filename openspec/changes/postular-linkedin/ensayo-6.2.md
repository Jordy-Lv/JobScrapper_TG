# Ensayo 6.2: LinkedIn en ensayo solo para el dueño

Objetivo: que el asistente llene las postulaciones de LinkedIn (Solicitud sencilla y páginas externas)
y se detenga justo antes de enviar, para ver la cobertura por familia sin enviar nada.

## Qué se activa en el Fedora

Todo en `~/buscador-vacantes/config.local.yaml` (fuera de git), sin tocar `config.yaml`:

```yaml
asistente:
  plataformas:
    linkedin: {automatica: true}
  ensayo:
    plataformas: [linkedin]   # en ensayo para todos: nadie envía de verdad
```

El ensayo es por plataforma y vale para todos los usuarios, así que aunque un invitado acepte el
aviso de riesgo, su postulación en LinkedIn solo se llena y se detiene. Los invitados no entran al
ensayo de verdad hasta 6.4.

Vuelta atrás: quitar esas dos claves (o `/plataformas linkedin off`) y reiniciar el servicio.

## Pasos del dueño (👤)

1. **Extensión 1.3.0** en el Chrome de Windows: `chrome://extensions` → recargar la extensión sin
   empaquetar desde `extension/` de la rama `postular-linkedin`. Debe decir 1.3.0 en el popup.
2. **Sesión de LinkedIn activa** en ese mismo Chrome.
3. **Permiso amplio**: en el popup, bloque «Páginas de las empresas» → conceder el permiso. Sin él
   las externas quedan en respaldo con `sin_permiso_externo`.
4. En el bot: tocar ⚡ en una vacante de LinkedIn → aparece el aviso de riesgo → «Acepto y postular».
   Después `/linkedin` muestra los dos interruptores («Solicitud sencilla» y «Páginas externas»);
   verificar que estén en 🟢.
5. Tocar ⚡ en 3 vacantes de LinkedIn de tipo sencilla y 3 de tipo externa. Cada una debe terminar en
   la card «ensayada» (llenó y no envió).

## Qué verificar al empezar (supuestos sin comprobar)

- **Cuenta de LinkedIn en el latido**: `linkedin.json` lee el correo del `mailto:` de
  `<perfil>/overlay/contact-info/` (verificado el 2026-10-28; `/in/me/` no servía y dejaba el popup en
  «Buscando correo»). Si el latido no trae `cuenta`, la cola no asigna nada: es lo primero que se ve.
- **Señales de éxito** de Greenhouse, Lever, Ashby y Workday: son las esperadas, no vistas.
- **Lever** trae hCaptcha: debe detenerse como barrera `captcha`, no fallar.
- **Pandapé** tras el correo: si pide contraseña, su dominio pasa a `familias_con_cuenta`.
- **Política v4**: el dueño debe revisar el texto legal del punto nuevo de LinkedIn.

## Criterios de cierre de 6.2

Dos semanas de ensayo; la cobertura por familia sale en el resumen diario; anotarla en
`docs/asistente/portales.md` (sección «LinkedIn»). Ajustar con lo visto: tope diario (15) y pausa
(240 s).

## Después

6.3: quitar `ensayo.plataformas`, 3 sencillas y 3 externas reales del dueño. 6.4: invitados.
