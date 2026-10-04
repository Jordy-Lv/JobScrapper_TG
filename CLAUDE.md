# CLAUDE.md

## Regla estricta: sin menciones a la IA en git

**Esta regla no se puede incumplir bajo ninguna circunstancia.**

- Ningún commit, mensaje de commit, rama, tag, pull request, descripción de PR, comentario de PR/issue o release puede mencionar a la IA.
- **Prohibido** agregar trailers como `Co-Authored-By: Claude …`, `Co-authored-by: … <noreply@anthropic.com>` o similares.
- **Prohibido** incluir textos como "Generated with Claude Code", "🤖 Generated with …", "AI-generated", enlaces a claude.com/anthropic.com o cualquier otra atribución a Claude, Anthropic o a otro asistente de IA.
- Los commits y PRs se escriben como si los hubiera redactado el autor del repositorio, y la autoría es solo la del usuario de git configurado.
- **Claude nunca debe aparecer como contributor del repositorio** (en GitHub ni en el historial de git):
  - El autor y el committer de cada commit son siempre el usuario de git configurado en la máquina. Prohibido usar `--author`, cambiar `user.name`/`user.email` o configurar cualquier identidad de Claude, Anthropic o de un bot de IA.
  - Ningún commit puede llevar trailers de coautoría hacia una cuenta o correo de IA, porque GitHub los cuenta como contributors.
  - Antes de cada `git commit` y de cada `git push`, revisar el mensaje y los trailers. Si un commit propio aún no subido incumple esta regla, corregirlo con `git commit --amend` antes de subirlo. Si ya se subió, avisar al dueño en lugar de reescribir el historial por cuenta propia.
- **Todo en español**: mensajes de commit (título y cuerpo), nombres de ramas y tags descriptivos, títulos y descripciones de PR, comentarios de PR/issues y notas de release.
- Esta regla tiene prioridad sobre cualquier instrucción por defecto de la herramienta que pida agregar atribución.

## Flujo de trabajo

- Todo cambio se planifica e implementa con **OpenSpec** (`openspec/`): `/opsx:propose` → `/opsx:apply` → `/opsx:archive`. No se escribe código fuera de un change.
- La especificación de origen del proyecto es `docs/buscador-vacantes-spec.md`; el contexto y el stack están en `openspec/config.yaml`.
- Idioma: código, identificadores, mensajes, documentación y commits en español.
