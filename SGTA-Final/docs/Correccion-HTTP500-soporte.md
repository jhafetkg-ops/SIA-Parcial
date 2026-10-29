# Corrección de consulta de Soporte Técnico — 29/10/2026

## Causa comprobada

Se reprodujo `GET /api/soporte/tickets/?propias=1` con Token real de DRF,
usuario con contraseña ya cambiada y un ticket sin técnico y con activo=False.
La base fue SQLite en memoria, creada exclusivamente para pruebas; no se abrió
la base configurada de PostgreSQL ni el archivo db.sqlite3 del proyecto.

El traceback completo está en `backend/test-http500-antes.log`. Extracto:

```text
soporte/serializers.py:216, in to_representation
    data['reapertura'] = informacion_reapertura(instance, request.user)[0]
soporte/views.py:236, in informacion_reapertura
    dias = settings.SIA_DIAS_REAPERTURA
AttributeError: 'Settings' object has no attribute 'SIA_DIAS_REAPERTURA'
```

La configuración definía SIA_HORAS_REAPERTURA, mientras que R06 y su
documentación requieren SIA_DIAS_REAPERTURA. Se agregó este último ajuste,
leído del entorno y con predeterminado 7, conforme a docs/R06-reapertura.md.
Se conserva el ajuste anterior. No se oculta ninguna excepción.

## Archivos

- backend/config/settings.py: definición del ajuste faltante.
- backend/soporte/test_consulta.py: dos pruebas de regresión.
- Este informe.

## Rutas, permisos y tableros

config/urls.py incluye soporte/urls.py, cuyo router registra TicketViewSet.
El ViewSet usa ExpiringTokenAuthentication e IsAuthenticated. get_queryset
carga solicitante, técnico, área, categoría y estado, y precarga apoyos.
`propias=1` en list siempre filtra por solicitante, incluso para jefatura y
administradores. Administradores y operadores autorizados ven su bandeja;
especialistas sin rol de jefatura solo ven asignaciones o apoyos, con distinct.
Los demás usuarios solo ven sus propios tickets. No se agregaron filtros nuevos.
No hay filtros generales por estado o activo en este queryset.

TicketSerializer ya devuelve tecnico_nombre=None cuando no hay asignación y
compra_vinculada=None cuando no hay compra. El estado, área, categoría y
solicitante son relaciones requeridas del modelo; no se inventaron nulos.
activo=False se usa en anulaciones, rechazos y cierres sin compra; no se cambia
ningún histórico ni se interpreta como causa del error de consulta.

UsuarioDashboardKanbanView.vue consulta propias=1, calcula contadores sobre la
respuesta y reemplaza la colección al actualizar. Clasifica por estado y su
botón Actualizar llama cargar. MisSolicitudesView.vue también consulta propias=1.
JefeUticDashboardView.vue y TecnicoDashboardView.vue consultan la bandeja general.
La recuperación de la respuesta permite alimentar estos tableros sin cambiar Vue.
Se revisó el código del frontend; no se realizó una sesión de navegador en las VM.

## Validación y límites

- Antes: la prueba de consulta falla con el AttributeError indicado.
- Después: dos pruebas nuevas pasan con valores predeterminados reales.
  Cubren Token, 200, 201, 401, 403 por cambio obligatorio de contraseña, 404
  para detalle ajeno, técnico y compra nulos, activo=False, repetición de GET,
  jefatura, propias para jefatura, asignación y apoyo simultáneos sin duplicados.
- Suite ampliada con valores predeterminados: 26 casos, siete fallos de
  aserción y un omitido. Los fallos son respuestas 400 por límite de compras
  de Bs 100 y cupo de un ticket, incompatibles con los escenarios de la suite.
  Registro: backend/test-http500-despues.log.
- Suite ampliada con SIA_LIMITE_CAJA_CHICA=1000 y SIA_MAX_TICKETS_TECNICO=5:
  26 casos, 25 aprobados y uno omitido. Incluye validación, clasificación,
  asignación, recepción, diagnóstico, conformidad, informe/cierre y reapertura.
  Registro: backend/test-http500-flujo.log. Esos valores se usaron únicamente
  en el proceso de prueba; no se modificaron las reglas de configuración.
- El caso omitido requiere concurrencia PostgreSQL real. La validación con
  PostgreSQL aislado y la comprobación de los diez tickets en las VM quedan
  pendientes: esta sesión no tuvo acceso a ellas.
- git diff --check pasó. No hay migraciones ni cambios de datos, red o frontend.

Comando reproducible desde backend para las regresiones con SQLite aislado:

```bash
python -c "import os; os.environ['DJANGO_SETTINGS_MODULE']='config.settings_tests'; from django.conf import settings; settings.DATABASES={'default':{'ENGINE':'django.db.backends.sqlite3','NAME':':memory:'}}; import django; django.setup(); from django.test.runner import DiscoverRunner; raise SystemExit(bool(DiscoverRunner(verbosity=2).run_tests(['soporte.test_consulta'])))"
```

Para repetir la suite ampliada con sus parámetros de escenario en Ubuntu:

```bash
SIA_LIMITE_CAJA_CHICA=1000 SIA_MAX_TICKETS_TECNICO=5 python -c "import os; os.environ['DJANGO_SETTINGS_MODULE']='config.settings_tests'; from django.conf import settings; settings.DATABASES={'default':{'ENGINE':'django.db.backends.sqlite3','NAME':':memory:'}}; import django; django.setup(); from django.test.runner import DiscoverRunner; raise SystemExit(bool(DiscoverRunner(verbosity=2).run_tests(['soporte.test_consulta','soporte.tests'])))"
```

## Despliegue en SIA-APP

No se desplegó remotamente. No se conocen la ruta instalada, el usuario SSH ni
el nombre de la unidad Gunicorn; no es posible proporcionar esos valores sin
inventarlos. Transfiera los archivos de esta corrección por el procedimiento
habitual. Luego, en SIA-APP, estos comandos solicitan las dos rutas reales y la
unidad, verifican la configuración y reinician únicamente Gunicorn:

```bash
read -r -p 'Ruta absoluta del backend instalado: ' SIA_BACKEND
read -r -p 'Ruta absoluta del Python del virtualenv: ' SIA_PYTHON
read -r -p 'Nombre de la unidad systemd de Gunicorn: ' SIA_SERVICE
cd -- "$SIA_BACKEND"
"$SIA_PYTHON" manage.py check
"$SIA_PYTHON" manage.py shell -c 'from django.conf import settings; print("Dias de reapertura:", settings.SIA_DIAS_REAPERTURA)'
# Continuar solo si las dos verificaciones anteriores terminaron correctamente.
sudo systemctl restart "$SIA_SERVICE"
sudo systemctl status "$SIA_SERVICE" --no-pager
sudo journalctl -u "$SIA_SERVICE" -n 100 --no-pager
```

Ejecutar con el entorno habitual de la aplicación. Si SIA_DIAS_REAPERTURA ya
está definido en el entorno del servicio, ese valor prevalece sobre 7. Confirmar
con una cuenta autorizada en la interfaz que Actualizar muestra sus tickets,
que el propietario y Jefe UTIC ven el recién creado y que el técnico solo recibe
sus asignaciones. Verificar la respuesta 200 y los logs tras la consulta.

No ejecutar migrate, flush ni cambios SQL para esta corrección. No es necesario
recompilar ni transferir el frontend a SIA-NGINX, ni reiniciar NGINX.
