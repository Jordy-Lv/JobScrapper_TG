# Diagnóstico del dueño — 24 de octubre de 2026

> Texto original del dueño, tal como lo dejó en `docs/Diagnostico241026.txt`. El plan que lo atiende está en [README.md](README.md).

Diagonostico del estado del scrapper:
Revisando el bot de vacantes, el módulo de scraping, me di cuenta de que el día de hoy, 24 de octubre, la última vacante que hemos recibido en el grupo de Telegram fue a las 8:33. Lo cual me parece raro teniendo en cuenta que estamos haciendo scraping de muchas fuentes.
La sugerencia para mitigar esto sería:
1. Revisar cómo está funcionando hoy el scraping y cuáles son las acciones de mejora.
2. Validar si la IA está dirigiendo la intervención, en este caso DeepSeek, al momento de aprobar o rechazar vacantes. ¿Cuáles son las reglas internas?
3. También como sugerencia sería borrar todos esos registros de vacantes que se han descartado o también las que se han aprobado pero no hemos visto, teniendo en cuenta que antes había mucho spam de vacantes. Al inicio hay muchas que no logramos ver. Es muy importante recuperar esas vacantes que una vez salieron, siempre y cuando la vacante no supere una semana de antigüedad.
Identificando las últimas vacantes me di cuenta de que se están enviando muchas ofertas laborales, las cuales van enfocadas más a personas con experiencia. Necesito que desactives o priorices en un 95% las vacantes que vayan dirigidas a aprendices: contratos de aprendizaje, vacantes que no soliciten experiencia. Es la prioridad absoluta actualmente. Quiero que revises el estado de las reglas y les des prioridad, por lo menos ahora, a las vacantes que sean de aprendices, contrato de aprendizaje, sin experiencia, todo lo relacionado a Trainee, todo eso. 
4. Y para terminar quiero que me sugieras que actúes como un senior de scraping de automatizaciones y me sugieras todo lo que me puedas sugerir para mejorar este aplicativo (por lo menos en el módulo de scraping). Porque, viendo el código, te debes dar cuenta de que hay dos módulos: módulo de scraping y módulo de aplicación automática a vacantes. Entonces nos vamos a centrar en mitigar y pulir al máximo el módulo de scraping.
5. Necesito que me ayudes con un tema: no de priorizar o no priorizar, sino de que le des más visibilidad a las vacantes que estén relacionadas con las siguientes áreas:
- administración de bases de datos
- programación
- infraestructura
- QA testing
Que la visibilidad sea con emojis, poniéndole un texto más grande. Eso queda a tu criterio y a tu imaginación. Tú me vas a ofrecer esa forma de darle más legibilidad o visibilidad a esas vacantes que cumplan o que se adapten a lo que estamos buscando.
No estoy diciendo que no nos envíes contratos de aprendizaje o vacantes de cero experiencia que sean de otras áreas de tech, ya sea como support, por ejemplo. Lo que estoy diciendo es que les des más legibilidad a las vacantes que más se adapten a nuestra búsqueda, por decirlo de esa manera.
6. Quiero que seas más transparente con la fecha o más específico con la fecha en la que se publicó la vacante por favor. 
