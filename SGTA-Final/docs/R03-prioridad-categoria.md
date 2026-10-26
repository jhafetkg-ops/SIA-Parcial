# R03 — Prioridad Alta al crear tickets de Red o Servidores

Rama: `regla-03-prioridad-categoria`, inicialmente en `23d062a`, igual que `main` y con R01/R02 integradas. Se conservó el informe R02 que ya estaba sin seguimiento al comenzar.

## Implementación

- Ajuste solicitado después: **solo en la vista del técnico, Red se muestra como Crítica**, aunque UTIC la clasifique como Baja, Media, Alta o Crítica. La prioridad de la base de datos y el SLA conservan la decisión de UTIC. Esta presentación se aplica a las bandejas, detalle, historial y filtro de prioridad del Especialista; no se extiende a Servidores ni modifica el backend.
- Se sobrescribe `save` en la clase **Ticket existente**. Solo cuando `self._state.adding` es verdadero, Red o Servidores reciben `ALTA`. Esto cubre la API, el administrador de Django y las creaciones normales mediante el modelo. Los guardados posteriores no reclasifican tickets históricos.
- Red se identifica mediante el código real `RED` de `CategoriaTicket`. El repositorio no incluye una categoría Servidores ni su código; se identifica por el nombre **Servidores** de la relación existente, ignorando mayúsculas y espacios externos. No se inventaron identificadores ni se crearon categorías operativas.
- `TicketSerializer.create` acepta las prioridades existentes (`BAJA`, `MEDIA`, `ALTA`, `CRITICA`) y conserva la seleccionada para las otras categorías. Si no se envía prioridad, las otras categorías mantienen el comportamiento previo de prioridad pendiente. El campo sigue siendo de solo lectura en las actualizaciones generales.
- `FormularioSolicitud.vue` no tenía selectores visibles de categoría/prioridad. Se añadieron al mismo formulario y únicamente para Soporte. Red/Servidores muestran Alta y deshabilitan el selector. Al cambiar a otra categoría se recupera la prioridad manual anterior; limpiar el formulario evita dejar una prioridad forzada residual. Se reutilizaron sus estilos existentes.
- Para conservar la clasificación previa a la asignación, sus indicadores usan `clasificado_en` en las interfaces de UTIC/Administración; el control existente de `designar_revision` comprueba también ese marcador. Así la prioridad inicial no sustituye la clasificación de SLA. Los permisos, responsables posibles y transiciones de estado no se modifican. La clasificación posterior por UTIC sigue funcionando: R03 aplica a la creación.

Existe un único endpoint REST de alta de tickets, que usa `TicketSerializer`. El comando preventivo crea mediante el modelo y utiliza la categoría `PREVENTIVO`, cuyo comportamiento se conserva. No se encontraron creaciones de tickets mediante `bulk_create` en el proyecto.

## Archivos y métodos

| Archivo | Cambio |
| --- | --- |
| `backend/soporte/models.py` | Sobrescritura de `Ticket.save` en el modelo existente; sin campos nuevos |
| `backend/soporte/serializers.py` | `TicketSerializer.create` |
| `backend/soporte/views.py` | Control de clasificación existente en `TicketViewSet.designar_revision` |
| `backend/soporte/tests.py` | Tres métodos nuevos de prueba dentro de `FlujoSoporteCompraTests`, sin clases nuevas |
| `frontend/src/components/FormularioSolicitud.vue` | Selectores y lógica reactiva; `crearTicket` y `limpiarFormulario` |
| `frontend/src/views/JefeUticDashboardView.vue` | Indicadores `necesitaClasificar` y `necesitaAsignar` |
| `frontend/src/views/AdminSoporteView.vue` | Indicadores de clasificación/asignación del ticket seleccionado |
| `frontend/src/components/FormularioSolicitud.test.js` | Prueba reactiva del componente existente y de sus bindings de plantilla; no añade componentes |
| `frontend/src/views/EspecialistaDashboardView.vue` | Prioridad presentada al técnico y filtro coherente para Red |
| `frontend/src/utils/portal.js`, `frontend/src/utils/portal.test.js` | Función de presentación y prueba de las cuatro prioridades, sin mutar prioridad ni SLA |
| `docs/R03-prioridad-categoria.md` | Este informe |

## Pruebas reales

- **65 pruebas Django aprobadas**, correspondientes a `soporte.tests`, `mantenimiento.tests` y `compras`, incluidas las regresiones R01/R02. Se ejecutaron con Python 3.14 / Django 6.1, SQLite temporal en memoria y hash MD5 solo para pruebas, sin modificar la configuración del proyecto.
- API JSON: Red y Servidores con Baja, Media, Alta, Crítica y prioridad omitida se guardan y responden con Alta. Otra categoría conserva la prioridad enviada y mantiene prioridad pendiente cuando se omite.
- Creación mediante el modelo, conservación de un ticket histórico al guardarlo y actualización general sin cambiar su prioridad.
- Conservación del estado NUEVO, ausencia de asignación/SLA al crear y flujo posterior: validación, clasificación con SLA y asignación. La prioridad precargada no permite saltar la clasificación.
- **6 pruebas frontend aprobadas**, incluido el ajuste posterior de presentación para Red: las cuatro prioridades elegidas por UTIC se muestran como Crítica al técnico, sin mutar la prioridad ni el SLA. La prueba del formulario monta el `setup` real de Vue con catálogos simulados y comprueba también el binding que bloquea el selector; no es una prueba visual en navegador.
- `npm run build`: correcto, con la advertencia existente de paquetes mayores de 500 kB.
- `check` de Django, `makemigrations soporte --check --dry-run` y `git diff --check`: correctos. **No se requieren migraciones.**

## Límites y conservación

No se pudo verificar el catálogo real de PostgreSQL ni ejecutar allí las pruebas: faltan `psycopg`/`psycopg2` en el intérprete disponible y el entorno virtual original apunta a un Python inexistente. La categoría Servidores se creó únicamente como dato de prueba aislado; para seleccionarla en producción debe existir en el catálogo con ese nombre. Si se proporciona su código real, podrá utilizarse ese identificador estable.

No se crearon clases, modelos, serializers, tablas, migraciones, endpoints ni componentes Vue nuevos. R01 y R02 permanecen intactas y sus pruebas pasan. No se modificaron `.env`, credenciales ni infraestructura; no se ejecutaron commit, push, merge ni creación de PR. No se implementó R04.
