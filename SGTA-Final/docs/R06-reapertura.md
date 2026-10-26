# R06 — Reapertura dentro del plazo configurado

## Base y alcance

Se verificó la rama `regla-06-reapertura`, inicialmente en `b006e9b`. Contiene el `main` disponible (`23d062a`) y R03 (`bcad08f`). Las referencias locales de `main` y `origin/main` todavía apuntaban a la integración de R02; no se hizo fetch, merge ni cambio de rama. Se conservó sin modificar el informe R02 que ya estaba sin seguimiento.

Se implementa exclusivamente la transición especial de Soporte **CERRADO → EN_EJECUCION**, el estado existente equivalente a En proceso. No se crea otro ticket ni una máquina de estados general. **R05 no se implementó.**

## Funcionamiento

- Única acción nueva necesaria en el `TicketViewSet` existente: `POST /api/soporte/tickets/{id}/reabrir/`. No había una acción de reapertura que ampliar.
- Se utiliza la consulta autorizada existente y se exige que el usuario sea el solicitante original y conserve el permiso existente `INFORMAR_CONFORMIDAD`, utilizado para operar sobre su atención. No se modifican roles ni permisos generales; un administrador ajeno tampoco puede reabrir el ticket.
- La fecha de cierre debe existir, ser consciente de zona horaria y no estar en el futuro. No se utilizan `creado_en` ni `actualizado_en` para inventar cierres históricos.
- El plazo procede de `SIA_DIAS_REAPERTURA`, leído del entorno al iniciar Django, con valor predeterminado **7**. Se compara `ahora > cerrado_en + timedelta(days=dias)`: exactamente siete días se acepta; siete días y un microsegundo se rechaza.
- Se bloquea el registro con `select_for_update` dentro de `transaction.atomic`. La transición y la bitácora `REABRIR_TICKET` se confirman conjuntamente. Un fallo de auditoría revierte la reapertura.
- Solo cambian el estado y `actualizado_en`. Se conservan identificador, código, solicitante, técnico, prioridad, SLA, solución, informes, documentos y fecha del cierre anterior. La auditoría registra el cierre anterior y la transición. Un segundo envío ya no cumple el estado Cerrado.
- Las validaciones devuelven el formato habitual `{"detalle": "..."}`: 400 para estado/fecha/plazo, 403 para usuario o permiso no autorizado y 404 cuando la consulta autorizada no permite ver el ticket. Sin autenticación se conserva el 401 existente.

## Fecha de cierre y persistencia

Se reutiliza **`Ticket.cerrado_en`**, ya existente y de solo lectura en la API. El cierre oficial, `elaborar_informe_final`, ya lo registraba con `timezone.now()`. Se conservan `TIME_ZONE = 'America/La_Paz'` y `USE_TZ = True`.

Se corrigió únicamente su asignación al reemitir un informe de un ticket que ya estaba Cerrado: esa reemisión conserva la fecha original y no reinicia el plazo. Si un ticket histórico cerrado no tiene fecha, continúa sin ella y su reapertura automática se rechaza. Un cierre nuevo, al pasar realmente a Cerrado, registra la fecha actual.

La fecha anterior se conserva al reabrir para mantener trazabilidad. La presentación del SLA comprueba también el estado actual, de modo que esa fecha histórica no haga aparecer el ticket reabierto como todavía cerrado. No se recalcula ni se amplía el SLA original.

**No se agregaron campos ni se requieren migraciones.**

## Interfaz

El detalle de Soporte en `MisSolicitudesView.vue` ofrece **Reabrir ticket**, con confirmación, únicamente cuando los metadatos `reapertura` devueltos por el servidor lo permiten. Muestra el motivo del rechazo cuando el propietario ya está fuera del plazo o no tiene una fecha válida. Otros usuarios no reciben la indicación de mostrar el botón. No se modifica Mantenimiento.

El plazo no está fijado en Vue: el servidor envía disponibilidad, motivo, días configurados y fecha límite. Tras la operación se recarga la lista y se actualiza el registro seleccionado, sin añadir otra fila. Si la ventana vence después de cargar la página, la API rechaza la solicitud, el formulario muestra el mensaje recibido y refresca la disponibilidad. La comprobación definitiva siempre se repite en el servidor.

## Archivos y métodos

| Archivo | Cambios |
| --- | --- |
| `backend/config/settings.py` | Configuración `SIA_DIAS_REAPERTURA` |
| `backend/soporte/views.py` | Función compartida `informacion_reapertura`, acción `TicketViewSet.reabrir` y fecha de `elaborar_informe_final` |
| `backend/soporte/serializers.py` | Metadatos en `TicketSerializer.to_representation`; lectura del estado en `get_sla_estado` y `get_sla_restante_minutos` |
| `backend/soporte/tests.py` | Cuatro métodos de R06 dentro de `FlujoSoporteCompraTests`; comprobación de cierre con zona horaria en la prueba existente |
| `frontend/src/views/MisSolicitudesView.vue` | Botón, confirmación, mensajes, `reabrirTicket` y actualización de la selección |
| `frontend/src/views/MisSolicitudesView.test.js` | Prueba reactiva del componente existente y de su binding de autorización |
| `docs/R06-reapertura.md` | Este informe |

## Pruebas reales

- **69 pruebas Django aprobadas** de `soporte.tests`, `mantenimiento.tests` y `compras`, incluidas las regresiones R01, R02 y R03. Ejecución con Python 3.14 / Django 6.1, SQLite temporal en memoria y hash MD5 únicamente para agilizar las pruebas; no se cambió la configuración de la base del proyecto.
- R06: cierre de hoy, hace cinco días y exactamente siete días aceptados; siete días y un microsegundo, y ocho días, rechazados. Estados Nuevo/En ejecución, otro solicitante, pérdida de permiso, falta de autenticación y fechas inexistentes/futuras rechazados.
- Con `override_settings(SIA_DIAS_REAPERTURA=3)`, un cierre de hace cinco días se rechaza con el mensaje correspondiente a tres días.
- Se comprobó que no cambia la cantidad de tickets, que los documentos históricos y los campos originales se conservan y que la auditoría contiene la transición y su autor. También se verificaron el rechazo de reapertura repetida y la reversión ante un fallo de auditoría.
- Reemitir un informe final no renueva un cierre vencido ni rellena una fecha histórica inexistente. La prueba existente del cierre confirma que la fecha registrada tiene zona horaria.
- **7 pruebas frontend aprobadas**, incluida R06: cancelación de confirmación, envío, actualización sin duplicados, rechazo por vencimiento posterior a la carga y uso de la autorización del servidor. Es una prueba reactiva con API simulada; no es una prueba visual de navegador.
- `npm run build`: correcto, con la advertencia existente de paquetes mayores de 500 kB.
- `check` de Django, `makemigrations soporte --check --dry-run` y `git diff --check`: correctos.

## Integración posterior con R05 y límites

R05 deberá contemplar `reabrir` como transición especial, manteniendo sus comprobaciones de autor, permiso, fecha, plazo y transacción. No debe convertir Cerrado → En ejecución en una transición genérica sin estos controles. Debe respetar que `cerrado_en` puede conservar el cierre anterior de un ticket actualmente abierto y que no debe renovarse al editar un informe ya cerrado.

Los informes, conformidades, firmas y marcas de distribución de ciclos anteriores se conservan: R06 no los vacía ni reinicia el flujo de generación de informes. El tratamiento de varios ciclos de atención y su distribución posterior deberá definirse al desarrollar R05; aquí se implementa la reapertura y su trazabilidad, sin rediseñar esos procesos.

No se ejecutaron pruebas en PostgreSQL ni concurrencia real entre procesos. El intérprete disponible no tiene `psycopg`/`psycopg2`, y el entorno virtual original apunta a un Python inexistente; se usó SQLite aislado para las pruebas funcionales. No se desplegó ni se modificó una base de producción.

No se crearon clases, modelos, serializers, componentes Vue, estados ni migraciones. R01, R02 y R03 permanecen intactas. No se modificaron `.env`, credenciales ni infraestructura, y no se ejecutaron commit, push, merge ni creación de Pull Requests.
