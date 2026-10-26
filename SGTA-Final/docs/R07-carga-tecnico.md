# R07 — Control de cupo exclusivo de asignación y reasignación

## Alcance corregido

La única validación nueva está en **`TicketViewSet.designar_revision`**, el método existente que asigna o cambia al técnico destinatario. No se añadieron rutas ni métodos de asignación paralelos.

El control anterior en `Ticket.save` se retiró. **`backend/soporte/models.py` vuelve a ser idéntico a HEAD**, incluidas sus clases, campos y lógica R03. También se retiró el manejador global de errores del ViewSet y se restauraron los archivos de pruebas de Compras y Mantenimiento que se habían cambiado para la implementación anterior.

No se modificaron `reabrir`, `informacion_reapertura`, `elaborar_informe_final`, los métodos de resolución, las validaciones de estados ni los comentarios de solución. R05 no se implementó. R01, R02, R03 y R06 conservan su lógica.

La base actual de la rama `regla-07-carga-tecnico` es `bfb762d`, que ya incorpora el merge del PR #6 de R06.

## Validación en el método existente

Se conservan los permisos, roles, estado permitido y clasificación previa que ya exigía `designar_revision`. Antes de guardar una asignación que cambie el destinatario de un ticket activo:

1. Se ejecuta la operación en `transaction.atomic` y se bloquea el ticket para leer su asignación actual.
2. Se bloquea la fila **Usuario** del técnico destinatario; si hay otro técnico anterior, ambas filas se bloquean por PK ascendente.
3. Después de adquirir el bloqueo se cuenta la carga actual del destinatario, excluyendo el propio ticket.
4. Si ya alcanza `SIA_MAX_TICKETS_TECNICO`, se devuelve HTTP 400 con el mensaje del límite configurado, antes de cambiar asignación, estado o auditoría.
5. Si existe cupo, continúa el cuerpo original del método. Mantener el mismo técnico no incrementa la carga y no se bloquea por cupo.

La fila estable del técnico serializa las asignaciones concurrentes incluso cuando todavía no tiene tickets. No se bloquean tablas completas.

El valor predeterminado de `SIA_MAX_TICKETS_TECNICO` es **5**. No se modificó ningún `.env`.

Se consideran activos los códigos existentes `NUEVO`, `EN_ANALISIS`, `ASIGNADO`, `EN_DIAGNOSTICO` y `EN_EJECUCION`. Se excluyen las fases de verificación/conformidad, informe final y estados terminales. Esta lista se usa solo para contar carga; no define ni modifica transiciones.

## R06 y operaciones fuera de asignación

R07 **no valida** `Ticket.save`, la creación directa mediante el modelo, el cierre, la resolución, la reapertura ni una entrada genérica a un estado activo. No se añadió un servicio compartido con esos procesos.

La prueba de compatibilidad confirma que **R06 puede reabrir un ticket aunque su técnico haya alcanzado el cupo**, conservando su fecha de cierre original. También confirma que guardar el modelo y cambiar un estado fuera del método de asignación no ejecutan R07.

En consecuencia, este alcance controla las asignaciones y reasignaciones, pero no garantiza una carga global máxima después de cualquier otra operación. Una reapertura puede elevar la carga por encima del límite. Imponer el límite también en R06 requeriría una autorización de alcance distinta; no se implementó esa política.

## Archivos finales

| Archivo | Cambio de R07 |
| --- | --- |
| `backend/config/settings.py` | Configuración `SIA_MAX_TICKETS_TECNICO` |
| `backend/soporte/views.py` | Lista de estados para conteo y control transaccional dentro de `designar_revision` |
| `backend/soporte/serializers.py` | Metadato **solo de lectura** `cuenta_carga_activa` para el contador de la interfaz; sin validaciones de cupo |
| `backend/soporte/tests.py` | Pruebas de asignación, reasignación, no interferencia con R06/guardados y concurrencia real; clase existente con transacciones reales |
| `frontend/src/views/JefeUticDashboardView.vue` | El contador existente usa el metadato del servidor |
| `frontend/src/views/JefeUticDashboardView.test.js` | Contador, error de cupo sin falso éxito y actualización tras asignación aceptada |
| `docs/R07-carga-tecnico.md` | Este informe actualizado al alcance corregido |

Las pruebas de R01/R02 que generan muchas órdenes de preparación conservan una configuración de cupo mayor únicamente para sus fixtures; no cambia la lógica de esas reglas. El informe R02 que ya estaba sin seguimiento permanece intacto.

## Verificación real de esta corrección

- **Comparación estructural del código con HEAD:** el modelo completo es idéntico; todos los métodos de las vistas salvo `designar_revision` son idénticos. Al aislar el bloque de cupo y los bloqueos de ese método, su cuerpo y decoradores originales coinciden con HEAD: permisos, validaciones y transiciones previas se conservaron.
- **SQLite:** se ejecutaron 72 pruebas de Soporte, Mantenimiento y Compras: **71 aprobadas y una omitida**, la de concurrencia que exige PostgreSQL.
- **PostgreSQL 18.4 real:** **24 pruebas de Soporte aprobadas**, incluidas R01/R02/R03/R06 y los casos de R07 corregida. La prueba concurrente usa dos conexiones y una barrera previa al bloqueo de Usuario: **HTTP 200 y HTTP 400; cinco activos finales**. No se simuló la base.
- Se verificaron el quinto cupo, el rechazo del sexto, la exclusión de resueltos/cerrados, la liberación de cupo, la conservación de la asignación anterior ante rechazo, el mismo técnico con cupo lleno y el límite configurado en 3.
- Se verificó expresamente que la reapertura con carga completa se acepta según R06 y que guardar o cambiar estados fuera de asignación no ejecuta R07.
- **8 pruebas frontend aprobadas** y `npm run build` correcto, con la advertencia existente de paquetes mayores de 500 kB. Son pruebas reactivas, no una prueba visual en navegador.
- `check`, `makemigrations soporte --check --dry-run` y `git diff --check`: correctos.

PostgreSQL se utilizó en un clúster temporal separado, puerto `55437`, con un driver instalado solo en una carpeta temporal. No se tocaron las bases existentes ni su servicio.

No se crearon clases, modelos, serializers, componentes Vue, endpoints, tablas ni migraciones. No se requieren migraciones. No se modificaron credenciales ni infraestructura existente y no se ejecutaron commit, push, merge ni PR.
