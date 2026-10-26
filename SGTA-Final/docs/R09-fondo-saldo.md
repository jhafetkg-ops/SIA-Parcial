# R09 — Fondo mensual de Caja Chica

Rama: `regla-09-fondo-saldo`, creada desde `origin/main` actualizado (`ded33f9`). Sin commit, push, merge ni PR.

## Implementación

- `backend/config/settings.py`: `SIA_FONDO_MENSUAL`, Decimal, valor predeterminado 5000; rechaza valores negativos o no finitos. No modifica `.env`.
- `backend/compras/tesoreria.py`: funciones `saldo_mensual` y `puede_consultar_saldo`; actualiza los existentes `pdf_recibo` y `recibos`.
- `backend/compras/views.py`: actualiza `SolicitudCompraViewSet.visto_bueno_director`; añade su método `saldo_caja_chica`; protege las instantáneas financieras en `documentos` y `documento_pdf`.
- `backend/config/urls.py`: registra `GET /api/caja-chica/saldo/` sobre el ViewSet existente.
- `frontend/src/views/AdminComprasView.vue`: muestra saldo autorizado, conserva el error del servidor y refresca tras aprobar.
- `frontend/src/views/DafEmitirView.vue`: la función existente `emitirCertificacion` incorpora los importes del servidor en jsPDF.
- Pruebas: `backend/compras/tests.py`, `frontend/src/views/AdminComprasView.test.js` y `frontend/src/views/DafEmitirView.test.js`.

No se crean clases, modelos, serializers, componentes Vue, tablas ni migraciones. Las pruebas nuevas reutilizan la clase existente `FlujoCajaChicaTests`, ahora transaccional para probar concurrencia real.

## Cálculo y aprobación

Saldo = fondo mensual configurado menos importes aprobados del mes y año de America/La_Paz, con Decimal. Solo se contabiliza la vía `CAJA_CHICA`; la vía `FINANZAS` conserva su aprobación actual. La clasificación existente de vías y R01/R02 no se modifica.

Se incluyen `APROBADO_PARA_DESEMBOLSO`, `FONDOS_DESEMBOLSADOS`, `COMPRA_REGISTRADA`, `COMPRADO_Y_ENTREGADO`, `DESCARGO_PENDIENTE_LIQUIDACION` y `CERRADO_ARCHIVADO`. Pendientes y rechazadas no consumen fondo. Cada compra se suma una vez.

El método real de aprobación es `visto_bueno_director`: conserva permiso `DAR_VISTO_BUENO`, cierre inmutable, estado previo y llamada al helper original `_transicion`, que permanece intacto. Importe mayor al saldo devuelve HTTP 400 con el mensaje solicitado y el saldo disponible. Importe igual al saldo se permite; repetir una aprobación devuelve 409.

La transacción bloquea la compra y adquiere `pg_advisory_xact_lock(0x534941, año*100+mes)` antes de calcular el fondo. No existe una fila única de fondo mensual que pueda bloquearse. El bloqueo asesor transaccional serializa aprobaciones del mismo período incluso sin compras previas, hasta confirmar o revertir. Si la espera cruza de mes, adquiere el bloqueo del período real. Aprobación, bitácora e instantánea se guardan atómicamente. PostgreSQL es obligatorio para aprobar por Caja Chica.

## Datos históricos y permisos

No existe un campo específico de fecha de aprobación. Para nuevas aprobaciones se almacena fecha e importe aprobado (`monto_estimado`) y saldo posterior en el JSON del modelo existente `DocumentoProceso`. Para compras anteriores se utiliza la fecha verificable de `Bitacora` (`VISTO_BUENO_DIRECTOR`, módulo Compras) y el importe existente. No se usa `actualizado_en`, no se inventan fechas y no se alteran compras antiguas.

Si una compra aprobada no tiene fecha o importe verificables, el endpoint devuelve `saldo_disponible: null`, `saldo_verificable: false` y los códigos en `aprobaciones_sin_respaldo`. Nuevas aprobaciones se rechazan hasta revisar esos respaldos. Esto puede bloquear una instalación con datos históricos incompletos; no se ofrece una corrección retrospectiva automática. Un cambio posterior de configuración no reconstruye fondos históricos anteriores.

El endpoint reutiliza autenticación Token e IsAuthenticated. Sin autenticación devuelve 401; sin permisos financieros, 403. Requiere alguno de los permisos existentes `DAR_VISTO_BUENO`, `CERTIFICAR_PRESUPUESTO` o `REGISTRAR_DESEMBOLSO`, respetando el acceso administrativo existente. Devuelve mes, fondo, total aprobado y saldo como cadenas monetarias, además de información de verificabilidad y fecha de consulta. Las instantáneas financieras nuevas no se exponen a otros roles mediante los documentos de compras.

## PDF

El jsPDF existente genera una certificación DAF anterior a la aprobación, por lo que muestra fondo, total y saldo consultados al servidor como **consulta al emitir (no reserva)**, con período y fecha. No calcula el saldo autoritativo desde Vue.

El recibo real de entrega de fondos se genera en el backend: conserva en `ReciboTesoreria.datos` la instantánea de aprobación, con la etiqueta **saldo al aprobar**. No sustituye el dato histórico por el saldo actual al emitir. Sin instantánea previa, indica expresamente que no se registró un saldo histórico verificable. Se mantienen los datos y firmas del comprobante existente.

## Validación

Se utilizó una instancia temporal aislada de PostgreSQL 18 en el puerto 55439, sin modificar la base ni el servicio PostgreSQL del usuario. Las pruebas verifican fondo inicial, consumos de 500 y 1000, saldo exacto, rechazo por insuficiencia, pendientes/rechazadas, duplicación, cambio de mes/año en La Paz, permisos y rollback completo. Dos aprobaciones simultáneas de 700 contra un fondo de 1000 producen una aceptación y un rechazo, con saldo 300.

Backend: 78 pruebas aprobadas sobre PostgreSQL real (`compras`, `soporte.tests` y `mantenimiento.tests`), incluidas las regresiones R01/R02 y tickets. Las pruebas de PDF leen el documento real; la certificación y ambas páginas del recibo también se renderizaron e inspeccionaron visualmente. Frontend: `node --test`, 10 pruebas aprobadas. `npm run build` correcto; mantiene el aviso de tamaño de chunks. Django `check` correcto y `makemigrations compras --check --dry-run` sin cambios.

El ejecutor temporal adapta únicamente el cierre redundante de FileResponse de pruebas anteriores para que no cierre conexiones dentro de APITestCase; no altera código de producción ni los tests de tickets. Se comprobó que soporte, prioridades, reapertura, cupos de técnicos, mantenimiento y el servicio compartido de documentos permanecen sin cambios. No se implementa R05.
