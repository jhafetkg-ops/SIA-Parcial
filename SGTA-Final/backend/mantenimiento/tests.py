from django.test import override_settings
from decimal import Decimal
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from rest_framework.test import APITestCase

from usuarios.models import Area, Rol, Usuario, UsuarioRol

from compras.models import SolicitudCompra

from .models import RequerimientoMantenimiento


class FlujoMantenimientoTests(APITestCase):
    """Recorre el BPMN de Mantenimiento: registro, validación,
    clasificación, designación, diagnóstico, compra, reparación,
    pruebas, verificación, conformidad e informe final."""

    def setUp(self):
        call_command("cargar_permisos_sigta")

        self.area = Area.objects.create(codigo="TEST", nombre="Área de prueba")
        self.usuarios = {}

        for codigo in (
            "SOLICITANTE",
            "SERVICIOS_GENERALES",
            "AUXILIAR_SERVICIOS_GENERALES",
            "ENCARGADO_COMPRAS_ALMACEN",
            "DAF",
            "TESORERIA",
            "DIRECTOR",
        ):
            rol = Rol.objects.get(codigo=codigo)
            usuario = Usuario.objects.create_user(
                username=codigo.lower(),
                email=f"{codigo.lower()}@emi.edu.bo",
                nombre_completo=codigo,
                password="Prueba#2026",
            )
            UsuarioRol.objects.create(usuario=usuario, rol=rol, activo=True)
            self.usuarios[codigo] = usuario

    def autenticar(self, rol):
        self.client.force_authenticate(self.usuarios[rol])

    def imagen(self):
        return SimpleUploadedFile("evidencia.jpg", b"\xff\xd8\xff", content_type="image/jpeg")

    def archivo(self, nombre="archivo.pdf"):
        return SimpleUploadedFile(nombre, b"contenido de prueba", content_type="application/pdf")

    def registrar(self, titulo="Aire acondicionado sin enfriar"):
        self.autenticar("SOLICITANTE")
        r = self.client.post("/api/mantenimiento/requerimientos/", {
            "titulo": titulo,
            "descripcion": "No enfría desde ayer",
            "ubicacion": "Aula C0-07",
            "evidencia_archivo": self.imagen(),
        }, format="multipart")
        self.assertEqual(r.status_code, 201, r.data)
        return r.data["requerimiento"]["id"]

    def test_director_visualiza_informes_anteriores_sin_modificarlos(self):
        from .models import EstadoMantenimiento
        pk = self.registrar()
        RequerimientoMantenimiento.objects.filter(pk=pk).update(
            estado=EstadoMantenimiento.objects.get(codigo='FINALIZADO'),
            informe_trabajo='Trabajo del tecnico registrado', informe_final='Informe final registrado',
        )
        self.autenticar('DIRECTOR')
        for tipo in ('tecnico', 'final'):
            r = self.client.get(f'/api/mantenimiento/requerimientos/{pk}/informes-pdf/{tipo}/')
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r['Content-Type'], 'application/pdf')
            self.assertTrue(r.content.startswith(b'%PDF'))
        from usuarios.models import DocumentoProceso
        self.assertFalse(DocumentoProceso.objects.filter(mantenimiento_id=pk).exists())
        otro = Usuario.objects.create_user(username='otro-solicitante', email='otro@example.invalid', nombre_completo='Otro solicitante')
        UsuarioRol.objects.create(usuario=otro, rol=Rol.objects.get(codigo='SOLICITANTE'))
        self.client.force_authenticate(otro)
        r = self.client.get(f'/api/mantenimiento/requerimientos/{pk}/informes-pdf/final/')
        self.assertEqual(r.status_code, 404)

    def test_ticket_invalido_no_procede(self):
        pk = self.registrar("Solicitud incompleta")

        self.autenticar("SERVICIOS_GENERALES")
        r = self.client.post(
            f"/api/mantenimiento/requerimientos/{pk}/validar-ticket/",
            {"es_valido": False, "motivo_rechazo": "No indica el equipo afectado."},
            format="json",
        )
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["requerimiento"]["estado_codigo"], "RECHAZADO")

    def test_solicitante_registra_campos_comunes_sin_adjunto(self):
        self.autenticar("SOLICITANTE")
        r = self.client.post("/api/mantenimiento/requerimientos/", {
            "titulo": "Luminaria averiada",
            "descripcion": "La luminaria parpadea durante la jornada.",
            "area": self.area.id,
            "ubicacion": "Aula C0-07",
            "referencia_ubicacion": "Bloque C, planta baja",
            "equipo_afectado": "Luminaria del aula",
            "tipo": "CORRECTIVO",
        }, format="multipart")

        self.assertEqual(r.status_code, 201, r.data)
        creado = r.data["requerimiento"]
        self.assertEqual(creado["solicitante"], self.usuarios["SOLICITANTE"].id)
        self.assertEqual(creado["estado_codigo"], "RECIBIDO")
        self.assertEqual(creado["referencia_ubicacion"], "Bloque C, planta baja")
        self.assertEqual(creado["equipo_afectado"], "Luminaria del aula")

    def test_flujo_completo_sin_compra(self):
        pk = self.registrar()

        # Jefatura: validar, clasificar y designar.
        self.autenticar("SERVICIOS_GENERALES")
        r = self.client.post(f"/api/mantenimiento/requerimientos/{pk}/validar-ticket/", {"es_valido": True}, format="json")
        self.assertEqual(r.data["requerimiento"]["estado_codigo"], "VALIDADO", r.data)

        r = self.client.post(
            f"/api/mantenimiento/requerimientos/{pk}/clasificar-prioridad/",
            {"prioridad": "ALTA", "criterio_prioridad": "Aula en uso permanente."},
            format="json",
        )
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data['requerimiento']['sla_horas'], 8)
        from datetime import datetime, timedelta
        clasificado = datetime.fromisoformat(r.data['requerimiento']['clasificado_en'].replace('Z', '+00:00'))
        limite = datetime.fromisoformat(r.data['requerimiento']['sla_fecha_limite'].replace('Z', '+00:00'))
        self.assertEqual(limite - clasificado, timedelta(hours=8))

        r = self.client.post(
            f"/api/mantenimiento/requerimientos/{pk}/designar-revision/",
            {"tecnico_id": self.usuarios["AUXILIAR_SERVICIOS_GENERALES"].id},
            format="json",
        )
        self.assertEqual(r.data["requerimiento"]["estado_codigo"], "DERIVADO", r.data)

        # Técnico: diagnóstico, reparación y pruebas.
        self.autenticar("AUXILIAR_SERVICIOS_GENERALES")
        r = self.client.post(
            f"/api/mantenimiento/requerimientos/{pk}/registrar-diagnostico/",
            {"diagnostico": "Filtro saturado", "plan_solucion": "Limpieza profunda"},
            format="json",
        )
        self.assertEqual(r.data["requerimiento"]["estado_codigo"], "EN_MANTENIMIENTO", r.data)

        r = self.client.post(
            f"/api/mantenimiento/requerimientos/{pk}/realizar-mantenimiento/",
            {"trabajo_realizado": "Se limpió el filtro y se recargó gas."},
            format="json",
        )
        self.assertEqual(r.status_code, 200, r.data)

        r = self.client.post(
            f"/api/mantenimiento/requerimientos/{pk}/pruebas-tecnicas/",
            {"resultado_pruebas": "Enfría correctamente."},
            format="json",
        )
        self.assertEqual(r.status_code, 200, r.data)

        r = self.client.post(
            f"/api/mantenimiento/requerimientos/{pk}/registrar-informe/",
            {"informe_trabajo": "Mantenimiento correctivo concluido."},
            format="json",
        )
        self.assertEqual(r.data["requerimiento"]["estado_codigo"], "INFORME_REGISTRADO", r.data)

        self.autenticar("SERVICIOS_GENERALES")
        r = self.client.post(f"/api/mantenimiento/requerimientos/{pk}/elaborar-informe-final/", {"informe_final": "Cierre prematuro"}, format="json")
        self.assertEqual(r.status_code, 409, r.data)

        # Solicitante: verificación con ciclo de retorno.
        self.autenticar("SOLICITANTE")
        r = self.client.post(
            f"/api/mantenimiento/requerimientos/{pk}/verificar-funcionamiento/",
            {"problema_resuelto": False, "observaciones": "La falla continúa"},
            format="json",
        )
        self.assertEqual(r.data["requerimiento"]["estado_codigo"], "EN_MANTENIMIENTO", r.data)
        self.assertEqual(r.data["requerimiento"]["rework_count"], 1)

        self.autenticar("AUXILIAR_SERVICIOS_GENERALES")
        r = self.client.post(f"/api/mantenimiento/requerimientos/{pk}/realizar-mantenimiento/", {"trabajo_realizado": "Corrección de la falla persistente."}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.client.post(
            f"/api/mantenimiento/requerimientos/{pk}/pruebas-tecnicas/",
            {"resultado_pruebas": "Segunda prueba conforme."}, format="json",
        )
        self.client.post(
            f"/api/mantenimiento/requerimientos/{pk}/registrar-informe/",
            {"informe_trabajo": "Se sustituyó el termostato."}, format="json",
        )

        self.autenticar("SERVICIOS_GENERALES")
        r = self.client.post(
            f"/api/mantenimiento/requerimientos/{pk}/verificar-funcionamiento/",
            {"problema_resuelto": True},
            format="json",
        )
        self.assertEqual(r.status_code, 403, r.data)

        self.autenticar("SOLICITANTE")
        r = self.client.post(f"/api/mantenimiento/requerimientos/{pk}/verificar-funcionamiento/", {"problema_resuelto": True, "firma": [[[10, 10], [50, 40], [90, 20]]]}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["requerimiento"]["estado_codigo"], "CONFORMIDAD_INFORMADA", r.data)
        self.assertTrue(r.data["requerimiento"]["conformidad_solicitante"])
        self.autenticar("SERVICIOS_GENERALES")
        r = self.client.post(f"/api/mantenimiento/requerimientos/{pk}/informar-conformidad/", {}, format="json")
        self.assertEqual(r.status_code, 403, r.data)

        # La respuesta ya registrada de un expediente anterior tambien
        # habilita el informe, sin pedir al jefe que confirme conformidad.
        from .models import EstadoMantenimiento
        RequerimientoMantenimiento.objects.filter(pk=pk).update(
            estado=EstadoMantenimiento.objects.get(codigo="INFORME_REGISTRADO")
        )

        r = self.client.post(
            f"/api/mantenimiento/requerimientos/{pk}/elaborar-informe-final/",
            {"informe_final": "Informe consolidado del mantenimiento."},
            format="json",
        )
        self.assertEqual(r.status_code, 200, r.data)
        self.assertTrue(r.data["requerimiento"]["informe_elevado_en"])

        # Dirección: recibe el informe y el proceso termina.
        self.autenticar("DIRECTOR")
        r = self.client.post(f"/api/mantenimiento/requerimientos/{pk}/recibir-informe/", {}, format="json")
        self.assertEqual(r.data["requerimiento"]["estado_codigo"], "FINALIZADO", r.data)
        self.assertTrue(r.data["requerimiento"]["proceso_finalizado_en"])

    def test_requerimiento_con_compra_no_viable(self):
        pk = self.registrar("Requiere compresor nuevo")

        self.autenticar("SERVICIOS_GENERALES")
        self.client.post(f"/api/mantenimiento/requerimientos/{pk}/validar-ticket/", {"es_valido": True}, format="json")
        self.client.post(
            f"/api/mantenimiento/requerimientos/{pk}/clasificar-prioridad/",
            {"prioridad": "MEDIA", "criterio_prioridad": "Puede esperar."}, format="json",
        )
        self.client.post(
            f"/api/mantenimiento/requerimientos/{pk}/designar-revision/",
            {"tecnico_id": self.usuarios["AUXILIAR_SERVICIOS_GENERALES"].id}, format="json",
        )

        self.autenticar("AUXILIAR_SERVICIOS_GENERALES")
        self.client.post(
            f"/api/mantenimiento/requerimientos/{pk}/registrar-diagnostico/",
            {"diagnostico": "Compresor quemado", "plan_solucion": "Reemplazar"}, format="json",
        )
        r = self.client.post(
            f"/api/mantenimiento/requerimientos/{pk}/solicitar-requerimiento/",
            {
            "informe_compra": SimpleUploadedFile("informe.pdf", b"informe con cuadros"),
            "cotizacion_archivo": SimpleUploadedFile("cotizacion.pdf", b"cotizacion", content_type="application/pdf"),
                "producto_requerido": "Compresor 12000 BTU",
                "especificacion_producto": "Marca X",
                "cantidad_requerida": 1,
                "costo_estimado": "450",
            },
            format="multipart",
        )
        self.assertEqual(r.data["requerimiento"]["estado_codigo"], "EN_ESPERA_COMPRA", r.data)

        # El técnico no puede continuar mientras la compra esté en curso.
        r = self.client.post(
            f"/api/mantenimiento/requerimientos/{pk}/realizar-mantenimiento/",
            {"trabajo_realizado": "x"}, format="json",
        )
        self.assertIn(r.status_code, (400, 409), r.data)

        self.autenticar("SERVICIOS_GENERALES")
        jefe = self.usuarios["SERVICIOS_GENERALES"]
        jefe.must_change_password = False
        jefe.save(update_fields=["must_change_password"])
        detalle = self.client.get(f"/api/mantenimiento/requerimientos/{pk}/")
        self.assertEqual(detalle.status_code, 200, detalle.data)
        proforma = self.client.get(detalle.data["cotizacion_archivo"])
        self.assertEqual(proforma.status_code, 200, getattr(proforma, "data", None))
        try:
            self.assertEqual(b"".join(proforma.streaming_content), b"cotizacion")
        finally:
            proforma.close()
        r = self.client.post(
            f"/api/mantenimiento/requerimientos/{pk}/evaluar-viabilidad-compra/",
            {"viable": False, "motivo_no_viable": "Excede el presupuesto disponible."},
            format="json",
        )
        self.assertEqual(r.data["requerimiento"]["estado_codigo"], "CERRADO_SIN_COMPRA", r.data)

    def test_requerimiento_con_compra_viable_genera_expediente(self):
        pk = self.registrar("Requiere repuesto")

        self.autenticar("SERVICIOS_GENERALES")
        self.client.post(f"/api/mantenimiento/requerimientos/{pk}/validar-ticket/", {"es_valido": True}, format="json")
        self.client.post(
            f"/api/mantenimiento/requerimientos/{pk}/clasificar-prioridad/",
            {"prioridad": "ALTA", "criterio_prioridad": "Urgente."}, format="json",
        )
        self.client.post(
            f"/api/mantenimiento/requerimientos/{pk}/designar-revision/",
            {"tecnico_id": self.usuarios["AUXILIAR_SERVICIOS_GENERALES"].id}, format="json",
        )

        self.autenticar("AUXILIAR_SERVICIOS_GENERALES")
        self.client.post(
            f"/api/mantenimiento/requerimientos/{pk}/registrar-diagnostico/",
            {"diagnostico": "Falta repuesto", "plan_solucion": "Comprar"}, format="json",
        )
        url = f"/api/mantenimiento/requerimientos/{pk}"
        r = self.client.post(url + "/solicitar-requerimiento/", {"producto_requerido": "Ventilador"}, format="json")
        self.assertEqual(r.status_code, 400, r.data)
        r = self.client.post(url + "/guardar-borrador-requerimiento/", {
            "producto_requerido": "Ventilador", "especificacion_producto": "Cuadro técnico",
            "informe_compra": SimpleUploadedFile("borrador.pdf", b"cuadros"),
        }, format="multipart")
        self.assertEqual(r.status_code, 200, r.data)
        guardado = RequerimientoMantenimiento.objects.get(pk=pk)
        self.assertFalse(guardado.estado_compra_componente)
        self.assertEqual(guardado.especificacion_producto, "Cuadro técnico")
        self.assertEqual(guardado.informe_compra.read(), b"cuadros")
        self.assertFalse(SolicitudCompra.objects.filter(requerimiento_mantenimiento_id=pk).exists())
        self.client.post(
            f"/api/mantenimiento/requerimientos/{pk}/solicitar-requerimiento/",
            {
            "informe_compra": SimpleUploadedFile("informe.pdf", b"informe con cuadros"),
            "cotizacion_archivo": SimpleUploadedFile("cotizacion.pdf", b"cotizacion", content_type="application/pdf"),"producto_requerido": "Ventilador", "cantidad_requerida": 1, "costo_estimado": "300"},
            format="multipart",
        )

        self.autenticar("SERVICIOS_GENERALES")
        RequerimientoMantenimiento.objects.filter(pk=pk).update(informe_compra="")
        r = self.client.get(url + "/informe-requerimiento-pdf/")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(b"".join(r.streaming_content).startswith(b"%PDF-"))
        self.assertTrue(RequerimientoMantenimiento.objects.get(pk=pk).informe_compra)
        r = self.client.post(url + "/validar-viabilidad-compra/", {}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        validado = RequerimientoMantenimiento.objects.get(pk=pk)
        self.assertEqual(validado.estado_compra_componente, "VIABLE")
        self.assertFalse(validado.derivado_compra)
        self.assertFalse(SolicitudCompra.objects.filter(requerimiento_mantenimiento_id=pk).exists())
        r = self.client.get(url + "/")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["estado_compra_componente"], "VIABLE")
        r = self.client.post(url + "/validar-viabilidad-compra/", {}, format="json")
        self.assertEqual(r.status_code, 400, r.data)
        r = self.client.post(url + "/evaluar-viabilidad-compra/", {"viable": True}, format="json")
        self.assertEqual(r.status_code, 400, r.data)
        self.assertFalse(SolicitudCompra.objects.filter(requerimiento_mantenimiento_id=pk).exists())
        self.autenticar("SERVICIOS_GENERALES")
        r = self.client.post(
            f"/api/mantenimiento/requerimientos/{pk}/evaluar-viabilidad-compra/",
            {
            "poa": SimpleUploadedFile("poa.pdf", b"poa"),
            "pedido": SimpleUploadedFile("proveido.pdf", b"proveido"),"viable": True}, format="multipart",
        )
        self.assertEqual(r.status_code, 200, r.data)

        codigo = r.data["requerimiento"]["codigo_compra_vinculada"]
        self.assertTrue(codigo)

        solicitud = SolicitudCompra.objects.get(codigo=codigo)
        self.assertEqual(solicitud.origen_modulo, "MANTENIMIENTO")
        self.assertEqual(solicitud.requerimiento_mantenimiento_id, pk)
        self.assertEqual(solicitud.estado, "CREADO_PENDIENTE_DAF")
        self.assertEqual(solicitud.informe.read(5), b"%PDF-")
        self.assertEqual(solicitud.proforma.read(), b"cotizacion")
        self.assertTrue(solicitud.poa)
        self.assertTrue(solicitud.pedido)

        r = self.client.post(url + "/evaluar-viabilidad-compra/", {"viable": True}, format="json")
        self.assertEqual(r.status_code, 400, r.data)
        self.assertEqual(SolicitudCompra.objects.filter(requerimiento_mantenimiento_id=pk).count(), 1)

        requerimiento = RequerimientoMantenimiento.objects.get(pk=pk)
        self.assertEqual(requerimiento.estado_compra_componente, "VIABLE")

    def test_r01_limite_total_api_sin_registros_parciales(self):
        # El costo es el total de la cotización, incluso con cantidad > 1.
        for limite, montos in (("1000", ("999", "1000", "1000.01", "1001")), ("800", ("800", "900"))):
            with override_settings(SIA_LIMITE_CAJA_CHICA=Decimal(limite)):
                for monto in montos:
                    from .models import EstadoMantenimiento
                    pk = self.registrar("R01")
                    objeto = RequerimientoMantenimiento.objects.get(pk=pk)
                    objeto.estado = EstadoMantenimiento.objects.get(codigo="EN_MANTENIMIENTO")
                    objeto.auxiliar_asignado = self.usuarios["AUXILIAR_SERVICIOS_GENERALES"]
                    objeto.save()
                    self.autenticar("AUXILIAR_SERVICIOS_GENERALES")
                    anterior = (RequerimientoMantenimiento.objects.filter(pk=pk).values().get())
                    compras = SolicitudCompra.objects.count()
                    r = self.client.post(f"/api/mantenimiento/requerimientos/{pk}/solicitar-requerimiento/", {
                        "producto_requerido": "Componentes solicitados", "cantidad_requerida": 3,
                        "costo_estimado": monto,
                        **{f"proveedor_{i}": f"Proveedor {i}" for i in range(1, 4)},
                        **{f"precio_unitario_{i}": "300" for i in range(1, 4)},
                        **{f"cotizacion_{i}": SimpleUploadedFile(f"cotizacion{i}.pdf", f"cotizacion {i}".encode(), content_type="application/pdf") for i in range(1, 4)},
                    }, format="multipart")
                    rechazado = Decimal(monto) > Decimal(limite)
                    self.assertEqual(r.status_code, 400 if rechazado else 200, r.data)
                    self.assertEqual(SolicitudCompra.objects.count(), compras)
                    if rechazado:
                        self.assertEqual(RequerimientoMantenimiento.objects.filter(pk=pk).values().get(), anterior)
                        self.assertIn("el monto total supera", r.data["costo_estimado"])

    def test_r02_cotizaciones_api_y_archivos(self):
        from compras.models import CotizacionCompra
        from pathlib import Path
        from django.conf import settings
        from rest_framework.authtoken.models import Token
        from rest_framework.test import APIClient
        casos = (("500", 0, False, 200), ("500", 1, False, 200),
                 ("500.01", 0, False, 400), ("700", 0, False, 400),
                 ("700", 2, False, 400), ("700", 3, True, 400),
                 ("700", 3, False, 200), ("900", 3, False, 200),
                 ("1001", 3, False, 400))
        for monto, numero, repetido, esperado in casos:
            with self.subTest(monto=monto, numero=numero, repetido=repetido):
                    from .models import EstadoMantenimiento
                    pk = self.registrar("R02")
                    RequerimientoMantenimiento.objects.filter(pk=pk).update(
                        estado=EstadoMantenimiento.objects.get(codigo="EN_MANTENIMIENTO"),
                        auxiliar_asignado=self.usuarios["AUXILIAR_SERVICIOS_GENERALES"],
                    )
                    self.autenticar("AUXILIAR_SERVICIOS_GENERALES")
                    usuario = self.usuarios["AUXILIAR_SERVICIOS_GENERALES"]
                    usuario.must_change_password = False
                    usuario.save(update_fields=['must_change_password'])
                    token = Token.objects.get_or_create(user=usuario)[0]
                    self.client.force_authenticate(user=usuario, token=token)
                    anterior = RequerimientoMantenimiento.objects.filter(pk=pk).values().get()
                    registros = CotizacionCompra.objects.count()
                    archivos = set(Path(settings.SIA_PRIVATE_ROOT).rglob('*'))
                    datos = {
                        "producto_requerido": "Componentes", "cantidad_requerida": 2,
                        "costo_estimado": monto,
                    }
                    if Decimal(monto) <= 500 and numero:
                        datos['cotizacion_archivo'] = SimpleUploadedFile('respaldo.png', b'imagen', content_type='image/png')
                    else:
                        for i in range(1, numero + 1):
                            datos[f'proveedor_{i}'] = '  PROVEEDOR  ' if repetido else f'Proveedor {i}'
                            datos[f'precio_unitario_{i}'] = '350'
                            datos[f'cotizacion_{i}'] = SimpleUploadedFile(f'cotizacion{i}.pdf', f'cotizacion {i}'.encode(), content_type='application/pdf')
                    r = self.client.post(f"/api/mantenimiento/requerimientos/{pk}/solicitar-requerimiento/", datos, format='multipart')
                    self.assertEqual(r.status_code, esperado, r.data)
                    if esperado == 400:
                        self.assertEqual(RequerimientoMantenimiento.objects.filter(pk=pk).values().get(), anterior)
                        self.assertEqual(CotizacionCompra.objects.count(), registros)
                        self.assertEqual(set(Path(settings.SIA_PRIVATE_ROOT).rglob('*')), archivos)
                        self.assertFalse(SolicitudCompra.objects.filter(requerimiento_mantenimiento_id=pk).exists())
                        if monto == '1001':
                            self.assertIn('el monto total supera', r.data['costo_estimado'])
                    elif Decimal(monto) > 500:
                        objeto = RequerimientoMantenimiento.objects.get(pk=pk)
                        self.assertEqual(objeto.cotizaciones.count(), 3)
                        detalle = self.client.get(f"/api/mantenimiento/requerimientos/{pk}/")
                        self.assertEqual(len(detalle.data['cotizaciones']), 3)
                        for cotizacion in detalle.data['cotizaciones']:
                            archivo = APIClient().get(cotizacion['documento_url'])
                            self.assertEqual(archivo.status_code, 200)
                            self.assertTrue(b''.join(archivo.streaming_content).startswith(b'cotizacion'))
                            archivo.close()
                            self.assertEqual(APIClient().get(cotizacion['documento_url'].split('?')[0]).status_code, 401)

                    if esperado == 200:
                        self.autenticar("SERVICIOS_GENERALES")
                        r = self.client.post(f"/api/mantenimiento/requerimientos/{pk}/validar-viabilidad-compra/", {}, format='json')
                        self.assertEqual(r.status_code, 200, r.data)
                        r = self.client.post(f"/api/mantenimiento/requerimientos/{pk}/evaluar-viabilidad-compra/", {
                            'viable': True,
                            'poa': SimpleUploadedFile('poa.pdf', b'poa', content_type='application/pdf'),
                            'pedido': SimpleUploadedFile('pedido.pdf', b'pedido', content_type='application/pdf'),
                        }, format='multipart')
                        self.assertEqual(r.status_code, 200, r.data)
                        solicitud = SolicitudCompra.objects.get(requerimiento_mantenimiento_id=pk)
                        self.assertEqual(solicitud.cotizaciones.count(), 3 if Decimal(monto) > 500 else 0)
                        from compras.expediente import documentos_faltantes
                        self.assertEqual(documentos_faltantes(solicitud), [])
