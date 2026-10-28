# Resumen de cambios por regla

Referencia: c?digo local revisado en `9b57796`. Rutas relativas a `D:/SIA reglas/SIA/SGTA-Final`. Las l?neas corresponden a los archivos actuales, no a la posici?n que ten?an al hacer el commit original. Se indican bloques funcionales y de pruebas; las importaciones auxiliares se incluyen en el archivo correspondiente sin enumerarlas individualmente.

Se verificaron los commits R01 `584e576`, R02 `25628aa`, R03 `bcad08f`, R06 `1aa5552`, R07 `299dfa1` y R09 `84d5d8e`. No se identificaron implementaciones separadas de R04, R05 ni R08 en este historial.

## R01 ? L?mite de Bs 1.000

| Archivo | L?neas actuales | Cambio y prop?sito |
| --- | --- | --- |
| [backend/config/settings.py](<D:/SIA reglas/SIA/SGTA-Final/backend/config/settings.py:255>) | 255-259 | Define SIA_LIMITE_CAJA_CHICA como Decimal, con valor predeterminado 1000. |
| [backend/compras/serializers.py](<D:/SIA reglas/SIA/SGTA-Final/backend/compras/serializers.py:258>) | 258-270 | SolicitudCompraSerializer.validate rechaza altas de t?cnicos que superen el l?mite; este bloque fue reubicado por R02 para validar antes de guardar archivos. |
| [backend/soporte/views.py](<D:/SIA reglas/SIA/SGTA-Final/backend/soporte/views.py:1881>) | 1881-1893 | En solicitar_requerimiento_componente controla el costo total y devuelve error antes de modificar el ticket. |
| [backend/mantenimiento/views.py](<D:/SIA reglas/SIA/SGTA-Final/backend/mantenimiento/views.py:1010>) | 1010-1022 | En solicitar_requerimiento controla el importe total al enviar, conservando el tratamiento de borradores. |
| [backend/soporte/tests.py](<D:/SIA reglas/SIA/SGTA-Final/backend/soporte/tests.py:781>) | 781-804 | Prueba importes por debajo, iguales y superiores al l?mite; confirma ausencia de cambios parciales. Tambi?n se adecuaron importes de fixtures anteriores. |
| [backend/mantenimiento/tests.py](<D:/SIA reglas/SIA/SGTA-Final/backend/mantenimiento/tests.py:384>) | 384-410 | Prueba l?mites configurables y rechazo sin cambios parciales; se adecu? un importe de fixture anterior. |

## R02 ? Tres cotizaciones para importes mayores a Bs 500

| Archivo | L?neas actuales | Cambio y prop?sito |
| --- | --- | --- |
| [backend/compras/cotizaciones.py](<D:/SIA reglas/SIA/SGTA-Final/backend/compras/cotizaciones.py:9>) | 9-65, 77 | validar_cotizaciones_requerimiento exige tres proveedores y archivos distintos; hasta 500 admite respaldo opcional. guardar_cotizaciones_requerimiento persiste el lote; la URL del archivo queda firmada. |
| [backend/compras/models.py](<D:/SIA reglas/SIA/SGTA-Final/backend/compras/models.py:34>) | 34-36, 46-52 | CotizacionCompra permite vincular cotizaciones con Soporte o Mantenimiento antes de existir una compra y a?ade la restricci?n de origen. |
| [backend/compras/migrations/0017_cotizaciones_origen_r02.py](<D:/SIA reglas/SIA/SGTA-Final/backend/compras/migrations/0017_cotizaciones_origen_r02.py:1>) | 1-37 | Migraci?n de los v?nculos de origen y la restricci?n del modelo existente. R02 s? incluy? esta migraci?n. |
| [backend/compras/serializers.py](<D:/SIA reglas/SIA/SGTA-Final/backend/compras/serializers.py:237>) | 237-279, 284 | SolicitudCompraSerializer.create guarda la compra y sus cotizaciones en una transacci?n; validate aplica R01 antes de R02 y permite la proforma opcional cuando corresponde. |
| [backend/compras/expediente.py](<D:/SIA reglas/SIA/SGTA-Final/backend/compras/expediente.py:3>) | 3-10 | documentos_faltantes deja de exigir proforma obligatoria para requerimientos de t?cnicos hasta Bs 500. |
| [backend/compras/views.py](<D:/SIA reglas/SIA/SGTA-Final/backend/compras/views.py:304>) | 304-308 | El filtro de expedientes completos reutiliza documentos_faltantes para no excluir solicitudes v?lidas sin proforma opcional. |
| [backend/soporte/views.py](<D:/SIA reglas/SIA/SGTA-Final/backend/soporte/views.py:1761>) | 1761, 1779, 1895-1899, 1909, 1920-1921, 1942, 1999, 2166, 2186 | Integra validaci?n y guardado de cotizaciones en el requerimiento; ajusta el respaldo opcional y vincula las cotizaciones al expediente de compra cuando se eleva. |
| [backend/mantenimiento/views.py](<D:/SIA reglas/SIA/SGTA-Final/backend/mantenimiento/views.py:957>) | 957, 961, 1024-1028, 1040, 1051-1052, 1061, 1129, 1202, 1229 | Integra cotizaciones en el requerimiento de Mantenimiento, distingue borrador/env?o, conserva el respaldo y las vincula con la compra. |
| [backend/soporte/serializers.py](<D:/SIA reglas/SIA/SGTA-Final/backend/soporte/serializers.py:209>) | 209-210 | Expone el l?mite del servidor y las cotizaciones del ticket al frontend. |
| [backend/mantenimiento/serializers.py](<D:/SIA reglas/SIA/SGTA-Final/backend/mantenimiento/serializers.py:137>) | 137-138 | Expone el l?mite y las cotizaciones del requerimiento de Mantenimiento. |
| [backend/usuarios/archivos.py](<D:/SIA reglas/SIA/SGTA-Final/backend/usuarios/archivos.py:75>) | 75, 79-81 | Incluye documentos de cotizaci?n en la consulta y entrega autorizada de archivos del expediente. |
| [backend/mantenimiento/migrations/0006_recepcion_componente_tecnico.py](<D:/SIA reglas/SIA/SGTA-Final/backend/mantenimiento/migrations/0006_recepcion_componente_tecnico.py:38>) | 38 | Ajusta el estado de opciones de migraci?n existente; no es la validaci?n de tres cotizaciones. |
| [frontend/src/utils/monto.js](<D:/SIA reglas/SIA/SGTA-Final/frontend/src/utils/monto.js:17>) | 17-34 | errorCotizaciones valida el l?mite recibido del servidor, cantidad de cotizaciones, proveedores distintos y precios. |
| [frontend/src/views/EspecialistaDashboardView.vue](<D:/SIA reglas/SIA/SGTA-Final/frontend/src/views/EspecialistaDashboardView.vue:149>) | 149, 153-175, 196, 343, 527, 611-623, 666-673, 685 | Formulario de tres ofertas, archivos y precios; visualizaci?n de respaldos; preparaci?n, validaci?n y env?o multipart del requerimiento de Soporte. |
| [frontend/src/views/AuxiliarServiciosGeneralesDashboardView.vue](<D:/SIA reglas/SIA/SGTA-Final/frontend/src/views/AuxiliarServiciosGeneralesDashboardView.vue:150>) | 150-176, 223, 240, 482-483, 522, 588, 619-628 | Formulario equivalente de Mantenimiento, respaldo opcional para importes menores y env?o de las tres ofertas cuando corresponde. |
| [backend/compras/tests.py](<D:/SIA reglas/SIA/SGTA-Final/backend/compras/tests.py:356>) | 356-398 | Prueba creaci?n directa, roles, proveedores/archivos repetidos, formatos inv?lidos y rechazo sin registros ni archivos parciales. |
| [backend/soporte/tests.py](<D:/SIA reglas/SIA/SGTA-Final/backend/soporte/tests.py:807>) | 807-876 | Prueba cotizaciones por API y permisos de archivos; tambi?n se actualizaron fixtures del flujo previo en 439, 500, 530-534, 554-602 y 795-797. |
| [backend/mantenimiento/tests.py](<D:/SIA reglas/SIA/SGTA-Final/backend/mantenimiento/tests.py:412>) | 412-485 | Prueba cotizaciones y persistencia; fixtures relacionados en 260, 264, 332 y 401-403. |
| [frontend/src/utils/monto.test.js](<D:/SIA reglas/SIA/SGTA-Final/frontend/src/utils/monto.test.js:29>) | 29-42 | Prueba que R01 se eval?a antes de R02 y que se utiliza el l?mite del servidor. |

## R03 ? Prioridad por categor?a y Red como Cr?tica para el t?cnico

| Archivo | L?neas actuales | Cambio y prop?sito |
| --- | --- | --- |
| [backend/soporte/models.py](<D:/SIA reglas/SIA/SGTA-Final/backend/soporte/models.py:561>) | 561-567 | Ticket.save asigna ALTA al crear tickets de Red o Servidores; los guardados posteriores conservan la clasificaci?n de UTIC. |
| [backend/soporte/serializers.py](<D:/SIA reglas/SIA/SGTA-Final/backend/soporte/serializers.py:1241>) | 1241-1249, 1261, 1269 | TicketSerializer.create acepta la prioridad inicial y conserva el comportamiento de las dem?s categor?as. |
| [backend/soporte/views.py](<D:/SIA reglas/SIA/SGTA-Final/backend/soporte/views.py:1276>) | 1276 | designar_revision exige clasificado_en: una prioridad autom?tica inicial no sustituye la clasificaci?n de UTIC ni su SLA. |
| [frontend/src/components/FormularioSolicitud.vue](<D:/SIA reglas/SIA/SGTA-Final/frontend/src/components/FormularioSolicitud.vue:213>) | 213-232, 531-532, 578, 647, 658-672, 1146, 1420-1421 | Selectores de categor?a/prioridad para Soporte, Alta autom?tica en Red/Servidores y restauraci?n de prioridad manual al cambiar de categor?a o limpiar. |
| [frontend/src/views/JefeUticDashboardView.vue](<D:/SIA reglas/SIA/SGTA-Final/frontend/src/views/JefeUticDashboardView.vue:70>) | 70 | Los indicadores de clasificaci?n y asignaci?n usan clasificado_en para mantener el paso del jefe UTIC. |
| [frontend/src/views/AdminSoporteView.vue](<D:/SIA reglas/SIA/SGTA-Final/frontend/src/views/AdminSoporteView.vue:870>) | 870, 986 | Mismo ajuste de indicadores de clasificaci?n/asignaci?n en administraci?n. |
| [frontend/src/utils/portal.js](<D:/SIA reglas/SIA/SGTA-Final/frontend/src/utils/portal.js:15>) | 15-18 | prioridadTecnico presenta CRITICA exclusivamente para Red, sin modificar la prioridad guardada ni el SLA. |
| [frontend/src/views/EspecialistaDashboardView.vue](<D:/SIA reglas/SIA/SGTA-Final/frontend/src/views/EspecialistaDashboardView.vue:49>) | 49, 51, 57, 73, 215, 306, 344, 405 | Aplica esa presentaci?n en bandejas, detalle e historial y hace coherente el filtro de prioridades del t?cnico. |
| [backend/soporte/tests.py](<D:/SIA reglas/SIA/SGTA-Final/backend/soporte/tests.py:306>) | 306-383 | Prueba creaci?n por categor?a, prioridades, guardados hist?ricos y clasificaci?n posterior por UTIC. |
| [frontend/src/components/FormularioSolicitud.test.js](<D:/SIA reglas/SIA/SGTA-Final/frontend/src/components/FormularioSolicitud.test.js:1>) | 1-91 | Prueba el formulario reactivo, prioridad forzada y restauraci?n de selecci?n manual. |
| [frontend/src/utils/portal.test.js](<D:/SIA reglas/SIA/SGTA-Final/frontend/src/utils/portal.test.js:24>) | 24-35 | Prueba que las cuatro prioridades de UTIC aparecen como Cr?tica para Red al t?cnico, sin alterar sus datos. |
| [docs/R03-prioridad-categoria.md](<D:/SIA reglas/SIA/SGTA-Final/docs/R03-prioridad-categoria.md:1>) | 1-46 | Informe de implementaci?n, ajuste posterior y pruebas. |

## R06 ? Reapertura dentro de siete d?as

| Archivo | L?neas actuales | Cambio y prop?sito |
| --- | --- | --- |
| [backend/config/settings.py](<D:/SIA reglas/SIA/SGTA-Final/backend/config/settings.py:261>) | 261 | Define SIA_DIAS_REAPERTURA, predeterminado 7. |
| [backend/soporte/views.py](<D:/SIA reglas/SIA/SGTA-Final/backend/soporte/views.py:233>) | 233-259 | informacion_reapertura comprueba propietario, permiso, estado cerrado, fecha v?lida y plazo exacto. |
| [backend/soporte/views.py](<D:/SIA reglas/SIA/SGTA-Final/backend/soporte/views.py:473>) | 473-495 | TicketViewSet.reabrir bloquea el ticket y reabre el mismo registro dentro de una transacci?n con auditor?a. |
| [backend/soporte/views.py](<D:/SIA reglas/SIA/SGTA-Final/backend/soporte/views.py:3287>) | 3287-3289 | elaborar_informe_final conserva cerrado_en al reemitir un informe ya cerrado para no reiniciar el plazo. |
| [backend/soporte/serializers.py](<D:/SIA reglas/SIA/SGTA-Final/backend/soporte/serializers.py:213>) | 213-216, 783, 862 | Entrega metadatos de reapertura y evita presentar como cerrado el SLA de un ticket reabierto que conserva su fecha hist?rica. |
| [frontend/src/views/MisSolicitudesView.vue](<D:/SIA reglas/SIA/SGTA-Final/frontend/src/views/MisSolicitudesView.vue:811>) | 811-818, 1304, 1860, 1872-1895 | Bot?n autorizado por el servidor, motivo de rechazo, confirmaci?n y reabrirTicket; refresca la selecci?n sin duplicar filas. |
| [backend/soporte/tests.py](<D:/SIA reglas/SIA/SGTA-Final/backend/soporte/tests.py:177>) | 177-304, 696 | Prueba plazo exacto, vencimiento, autorizaci?n, fechas inv?lidas, rollback y conservaci?n de datos/fecha de cierre. |
| [frontend/src/views/MisSolicitudesView.test.js](<D:/SIA reglas/SIA/SGTA-Final/frontend/src/views/MisSolicitudesView.test.js:1>) | 1-98 | Prueba confirmaci?n, cancelaci?n, respuesta del servidor y actualizaci?n sin duplicados. |
| [docs/R06-reapertura.md](<D:/SIA reglas/SIA/SGTA-Final/docs/R06-reapertura.md:1>) | 1-66 | Informe de alcance, comportamiento y l?mites. |

## R07 ? M?ximo cinco activos al asignar o reasignar

| Archivo | L?neas actuales | Cambio y prop?sito |
| --- | --- | --- |
| [backend/config/settings.py](<D:/SIA reglas/SIA/SGTA-Final/backend/config/settings.py:262>) | 262 | Define SIA_MAX_TICKETS_TECNICO, predeterminado 5. |
| [backend/soporte/views.py](<D:/SIA reglas/SIA/SGTA-Final/backend/soporte/views.py:69>) | 69 | Define ESTADOS_CARGA_ACTIVA con los c?digos reales utilizados para contar carga, sin modificar transiciones. |
| [backend/soporte/views.py](<D:/SIA reglas/SIA/SGTA-Final/backend/soporte/views.py:1238>) | 1238, 1256, 1376-1391 | designar_revision usa transacci?n y bloqueo del ticket y de los usuarios t?cnicos, cuenta carga del destinatario y rechaza si no hay cupo. Mantener el mismo t?cnico no a?ade carga. |
| [backend/soporte/serializers.py](<D:/SIA reglas/SIA/SGTA-Final/backend/soporte/serializers.py:211>) | 211-212 | Expone cuenta_carga_activa como metadato de lectura para el contador, sin validar cupo al guardar estados. |
| [frontend/src/views/JefeUticDashboardView.vue](<D:/SIA reglas/SIA/SGTA-Final/frontend/src/views/JefeUticDashboardView.vue:86>) | 86 | cargaEspecialista utiliza el metadato del servidor para mostrar el n?mero de activos. |
| [backend/soporte/tests.py](<D:/SIA reglas/SIA/SGTA-Final/backend/soporte/tests.py:16>) | 16, 22, 48-175, 780, 806 | Prueba asignaci?n/reasignaci?n, quinto/sexto cupo, configuraci?n, concurrencia PostgreSQL y no interferencia con R06; adapta fixtures de pruebas previas. |
| [frontend/src/views/JefeUticDashboardView.test.js](<D:/SIA reglas/SIA/SGTA-Final/frontend/src/views/JefeUticDashboardView.test.js:1>) | 1-73 | Prueba contador y rechazo de cupo sin anunciar una asignaci?n exitosa. |
| [docs/R07-carga-tecnico.md](<D:/SIA reglas/SIA/SGTA-Final/docs/R07-carga-tecnico.md:1>) | 1-63 | Documenta el alcance corregido: solo asignaci?n/reasignaci?n, sin validaci?n en Ticket.save ni en reapertura. |

## R09 ? Fondo mensual y saldo de Caja Chica

| Archivo | L?neas actuales | Cambio y prop?sito |
| --- | --- | --- |
| [backend/config/settings.py](<D:/SIA reglas/SIA/SGTA-Final/backend/config/settings.py:263>) | 263-265 | Define SIA_FONDO_MENSUAL como Decimal, predeterminado 5000, con validaci?n de configuraci?n. |
| [backend/compras/tesoreria.py](<D:/SIA reglas/SIA/SGTA-Final/backend/compras/tesoreria.py:18>) | 18-83 | Estados aprobados, permiso financiero y saldo_mensual: suma una vez las compras aprobadas del per?odo de La Paz usando importes y fechas verificables. |
| [backend/compras/views.py](<D:/SIA reglas/SIA/SGTA-Final/backend/compras/views.py:642>) | 642-691 | visto_bueno_director valida saldo antes de aprobar, usa bloqueo asesor transaccional de PostgreSQL por mes y guarda instant?nea de aprobaci?n en DocumentoProceso existente. |
| [backend/compras/views.py](<D:/SIA reglas/SIA/SGTA-Final/backend/compras/views.py:165>) | 165-169 | saldo_caja_chica entrega el saldo ?nicamente a usuarios con permiso financiero. |
| [backend/compras/views.py](<D:/SIA reglas/SIA/SGTA-Final/backend/compras/views.py:193>) | 193-204 | documentos y documento_pdf impiden exponer las instant?neas financieras nuevas a usuarios sin permiso. |
| [backend/config/urls.py](<D:/SIA reglas/SIA/SGTA-Final/backend/config/urls.py:12>) | 12, 25 | Importa el ViewSet existente y registra GET /api/caja-chica/saldo/. |
| [backend/compras/tesoreria.py](<D:/SIA reglas/SIA/SGTA-Final/backend/compras/tesoreria.py:104>) | 104-109, 143-145 | pdf_recibo muestra saldo hist?rico al aprobar; recibos copia la instant?nea al JSON del recibo existente. |
| [frontend/src/views/AdminComprasView.vue](<D:/SIA reglas/SIA/SGTA-Final/frontend/src/views/AdminComprasView.vue:61>) | 61-62, 638, 1205, 1307-1314, 1369 | Muestra saldo autorizado, consulta el endpoint y refresca despu?s de aprobar o de recibir rechazo financiero. |
| [frontend/src/views/DafEmitirView.vue](<D:/SIA reglas/SIA/SGTA-Final/frontend/src/views/DafEmitirView.vue:436>) | 436-438, 565-571 | emitirCertificacion obtiene el saldo del servidor y lo incorpora al jsPDF con etiqueta de consulta actual, sin presentarlo como hist?rico. |
| [backend/compras/tests.py](<D:/SIA reglas/SIA/SGTA-Final/backend/compras/tests.py:11>) | 11-12, 36-209 | Prueba consumos, saldo exacto, insuficiencia, historial, cambio de mes, permisos, PDF, rollback y aprobaciones simult?neas en PostgreSQL. |
| [frontend/src/views/AdminComprasView.test.js](<D:/SIA reglas/SIA/SGTA-Final/frontend/src/views/AdminComprasView.test.js:1>) | 1-59 | Prueba error financiero sin falso ?xito y actualizaci?n de saldo tras aprobar. |
| [frontend/src/views/DafEmitirView.test.js](<D:/SIA reglas/SIA/SGTA-Final/frontend/src/views/DafEmitirView.test.js:1>) | 1-72 | Prueba el PDF real generado por jsPDF con los importes del servidor. |
| [docs/R09-fondo-saldo.md](<D:/SIA reglas/SIA/SGTA-Final/docs/R09-fondo-saldo.md:1>) | 1-47 | Informe de archivos, m?todos, concurrencia, permisos, PDF, pruebas y limitaciones. |

## Precisiones de alcance

- R01: el l?mite de Bs 1.000 es por solicitud de art?culos; R09: Bs 5.000 es el fondo mensual acumulado de Caja Chica. Son controles distintos.
- R03: la prioridad inicial autom?tica es Alta para Red/Servidores. El ajuste solicitado despu?s presenta solo Red como Cr?tica al t?cnico; el jefe UTIC conserva cualquiera de sus cuatro clasificaciones y su SLA.
- R06: ?nicamente reapertura especial del mismo ticket. R07 no a?ade controles en esa reapertura ni implementa R05.
- R02 s? modific? relaciones del modelo CotizacionCompra y una migraci?n; no debe confundirse con R09, que no cre? modelos, clases, tablas ni migraciones.
- El documento R02-cotizaciones.md ya estaba sin seguimiento al comenzar R09 y no forma parte de los commits verificados.
- Los cambios de infraestructura (HTTPS, STATIC_ROOT) y la correcci?n posterior de migraci?n de auditor?a son cambios separados, no implementaciones de estas reglas.
