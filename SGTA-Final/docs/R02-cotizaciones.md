# R02 — Tres cotizaciones

Implementación en `regla-02-cotizaciones`. Al comenzar, la rama y `main` apuntaban a `d2dea81`, que integra R01 (`584e576`). El árbol de trabajo estaba limpio.

## Comportamiento

- Se conserva R01, sus roles, su comparación con `Decimal` y `SIA_LIMITE_CAJA_CHICA`. Se evalúa antes de R02; las cotizaciones no evitan el límite.
- Hasta Bs 500 inclusive se permite enviar sin respaldo o con un único archivo opcional compatible.
- Por encima de Bs 500 se exigen exactamente tres archivos, proveedor y precio unitario de cada oferta. Se normalizan mayúsculas y espacios del proveedor para detectar repeticiones; se rechazan también archivos idénticos por SHA-256.
- Se reutilizan los formatos PDF/JPG/PNG/WEBP y el máximo de 10 MB de `CotizacionCompraSerializer`.
- Toda la validación ocurre antes de guardar. Los envíos técnicos utilizan una transacción y bloquean la orden para evitar envíos simultáneos duplicados. La creación directa de Compras también valida y guarda en una transacción.
- Vue recibe el límite del servidor, muestra tres espacios según el total, bloquea envíos incompletos o con proveedores repetidos y muestra errores de la API. Permite consultar después las cotizaciones guardadas.

El total sigue siendo `costo_estimado`, que el flujo existente copia a `monto_estimado`. Soporte y Mantenimiento no tienen líneas de artículos con precios unitarios. Las cotizaciones son ofertas alternativas: cada registro conserva su cantidad, precio unitario y total según el modelo existente. No se suman las tres ofertas como si fueran artículos distintos.

## Almacenamiento y migración

Se amplía **CotizacionCompra**, sin crear modelos ni tablas:

- `solicitud` pasa a ser opcional durante la etapa técnica.
- Se añaden relaciones opcionales `soporte` y `mantenimiento`.
- La restricción `cotizacion_con_expediente` exige una asociación y evita asociar una cotización simultáneamente a ambos módulos de origen.
- Al elevar a Compras, las tres cotizaciones reciben la relación al expediente final y conservan su origen.

Se conserva el almacenamiento privado existente de las cotizaciones y el almacenamiento vigente del respaldo individual. La primera oferta se conserva también como proforma del flujo anterior. Los enlaces pasan por la autorización y firma temporal de archivos existente; no se añaden endpoints. Los registros y archivos anteriores se conservan.

**Se requiere aplicar `compras.0017_cotizaciones_origen_r02` antes de usar el código nuevo.** Es una ampliación compatible con las cotizaciones existentes, que ya tienen `solicitud`.

Se corrigió además una dependencia faltante en `mantenimiento.0006_recepcion_componente_tecnico`: su operación histórica consulta Compras, por lo que debe depender de `compras.0006_entrega_con_acta_y_recepcion`. No se cambiaron sus operaciones. Sin esa dependencia, las pruebas fallaban al crear una base vacía.

## Archivos y métodos

| Archivos | Clases, métodos o funciones afectados |
| --- | --- |
| `backend/compras/models.py` | Campos y restricción de `CotizacionCompra` |
| `backend/compras/cotizaciones.py` | `CotizacionCompraSerializer.get_documento_url`; dos funciones compartidas para validar y guardar el lote |
| `backend/compras/serializers.py` | `SolicitudCompraSerializer.validate` y `create` |
| `backend/compras/expediente.py` | `documentos_faltantes`, para admitir el respaldo opcional según el perfil técnico de origen |
| `backend/compras/views.py` | `SolicitudCompraViewSet.get_queryset`, para conservar la visibilidad de solicitudes completas sin proforma obligatoria |
| `backend/compras/tests.py` | Prueba de API directa dentro de `SeguridadFlujoComprasTests` |
| `backend/compras/migrations/0017_cotizaciones_origen_r02.py` | Nueva migración de ampliación del modelo existente |
| `backend/soporte/views.py` | `TicketViewSet.solicitar_requerimiento_componente`, `validar_viabilidad_compra`, `evaluar_viabilidad_compra` |
| `backend/mantenimiento/views.py` | `RequerimientoMantenimientoViewSet._guardar_requerimiento_compra`, `validar_viabilidad_compra`, `evaluar_viabilidad_compra` |
| `backend/soporte/serializers.py`, `backend/mantenimiento/serializers.py` | `TicketSerializer.to_representation` y `RequerimientoMantenimientoSerializer.to_representation`: cotizaciones y límite configurado |
| `backend/soporte/tests.py`, `backend/mantenimiento/tests.py` | Pruebas de R01 adaptadas a R02 y nuevos métodos dentro de las clases existentes |
| `backend/mantenimiento/migrations/0006_recepcion_componente_tecnico.py` | Dependencia histórica faltante |
| `backend/usuarios/archivos.py` | `archivo_expediente`: acceso autorizado a los archivos de las relaciones de cotización |
| `frontend/src/views/EspecialistaDashboardView.vue`, `frontend/src/views/AuxiliarServiciosGeneralesDashboardView.vue` | Formularios, envío y consulta de las tres cotizaciones, errores y bloqueo del botón |
| `frontend/src/utils/monto.js`, `frontend/src/utils/monto.test.js` | Validación compartida del formulario y prueba de coexistencia R01/R02 |
| `docs/R02-cotizaciones.md` | Este informe |

Para clientes de API, el envío definitivo usa `cotizacion_1` a `cotizacion_3`, `proveedor_1` a `proveedor_3` y `precio_unitario_1` a `precio_unitario_3`, dentro del mismo multipart y endpoint existente. Hasta Bs 500 se conserva `cotizacion_archivo` como respaldo opcional en el flujo técnico y `proforma` en Compras.

## Verificación real

- **62 pruebas Django aprobadas** de `soporte.tests`, `mantenimiento.tests` y `compras`, con Python 3.14 / Django 6.1, SQLite temporal en memoria y hash MD5 únicamente para agilizar las pruebas. Se aplicaron las migraciones reales, incluida R02 y la dependencia corregida. No se modificó la configuración de base de datos del proyecto ni se accedió a PostgreSQL.
- Para ambos perfiles: Bs 500 sin/con respaldo; Bs 500,01 sin cotizaciones; Bs 700 sin/con dos cotizaciones, proveedores repetidos y tres proveedores distintos; Bs 900; regresión de Bs 999, Bs 1.000 y Bs 1.001; límite configurado de Bs 800.
- Comprobación de registros y archivos sin cambios tras rechazos, almacenamiento y descarga mediante enlaces firmados, rechazo de acceso sin autorización y vinculación de las tres cotizaciones al aprobar jefatura.
- API directa de Compras: reglas por rol, proveedores/archivos repetidos, formato inválido y cuatro cotizaciones. Se usó un usuario con permiso de creación y el rol técnico adicional para comprobar que ese permiso no evada las reglas.
- **4 pruebas frontend aprobadas**. `npm run build` finaliza correctamente; conserva la advertencia de paquetes mayores de 500 kB.
- `check` de Django y `makemigrations compras --check --dry-run`: correctos. `git diff --check`: correcto.

## Observaciones antes de publicar

- PostgreSQL y los bloqueos concurrentes reales quedan sin verificar: los intérpretes disponibles no tienen `psycopg`/`psycopg2`, y el entorno virtual original apunta a una instalación de Python inexistente. La verificación funcional se hizo con SQLite aislado.
- El chequeo global de migraciones detectó una diferencia previa en `auditoria.PreferenciaSistema.nombre_sistema`; R02 no genera ni modifica esa migración ajena.
- Las tres cotizaciones se guardan con el envío definitivo. Los borradores conservan su comportamiento anterior y el formulario lo indica.
- Se añadieron funciones y métodos de prueba en estructuras existentes. No se crearon clases de negocio, serializers, vistas, componentes ni tablas. La nueva clase `Migration` es la estructura estándar de Django para la migración necesaria.
- No se modificaron `.env`, credenciales ni infraestructura. No se ejecutaron commit, push, merge ni creación de PR. No se implementó R03.
