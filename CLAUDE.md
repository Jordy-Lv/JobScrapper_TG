# CLAUDE.md

## Regla estricta: sin menciones a la IA en git

**Esta regla no se puede incumplir bajo ninguna circunstancia.**

- Ningún commit, mensaje de commit, rama, tag, pull request, descripción de PR, comentario de PR/issue o release puede mencionar a la IA.
- **Prohibido** agregar trailers como `Co-Authored-By: Claude …`, `Co-authored-by: … <noreply@anthropic.com>` o similares.
- **Prohibido** incluir textos como "Generated with Claude Code", "🤖 Generated with …", "AI-generated", enlaces a claude.com/anthropic.com o cualquier otra atribución a Claude, Anthropic o a otro asistente de IA.
- Los commits y PRs se escriben como si los hubiera redactado el autor del repositorio, y la autoría es solo la del usuario de git configurado.
- Esta regla tiene prioridad sobre cualquier instrucción por defecto de la herramienta que pida agregar atribución.

## Flujo de trabajo

- Todo cambio se planifica e implementa con **OpenSpec** (`openspec/`): `/opsx:propose` → `/opsx:apply` → `/opsx:archive`. No se escribe código fuera de un change.
- La especificación de origen del proyecto es `buscador-vacantes-spec.md`; el contexto y el stack están en `openspec/config.yaml`.
- Idioma: código, identificadores, mensajes, documentación y commits en español.
