from django.test import override_settings
from decimal import Decimal
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from django.core.management import call_command
from rest_framework.test import APITestCase

from usuarios.models import Area, Rol, Usuario, UsuarioRol

from compras.models import SolicitudCompra

from .models import CategoriaTicket, EstadoTicket, Ticket


class FlujoSoporteCompraTests(APITestCase):
    """Cubre el disparo real del subproceso de Compra Caja Chica
    desde un ticket de Soporte Técnico ("¿Requiere compra?"), con
    la cadena Especialista solicita -> Jefe UTIC evalúa viabilidad
    que exige el BPMN oficial."""

    def setUp(self):
        call_command("cargar_permisos_sigta")

        # Los estados (NUEVO, EN_ANALISIS, ...) y categorías ya se
        # siembran con soporte.0006_seed_estados_categorias /
        # 0008_seed_estado_cerrado_sin_compra.
        self.categoria = CategoriaTicket.objects.get(codigo="HARDWARE")
        self.area = Area.objects.create(codigo="TEST", nombre="Área de prueba")

        self.usuarios = {}
        for codigo in ("SOLICITANTE", "JEFE_UTIC", "ESPECIALISTA"):
            rol = Rol.objects.get(codigo=codigo)
            usuario = Usuario.objects.create_user(
                username=codigo.lower(),
                email=f"{codigo.lower()}@emi.edu.bo",
                nombre_completo=codigo,
                password="Prueba#2026",
            )
            UsuarioRol.objects.create(usuario=usuario, rol=rol, activo=True)
            self.usuarios[codigo] = usuario

    def autenticar(self, codigo):
        self.client.force_authenticate(self.usuarios[codigo])

    def test_r03_prioridad_por_categoria_desde_api(self):
        red = CategoriaTicket.objects.get(codigo='RED')
        # Categoría solo de prueba: no se asume un código de producción para Servidores.
        servidores = CategoriaTicket.objects.create(codigo='R03_CATALOGO', nombre=' Servidores ')
        self.autenticar('SOLICITANTE')
        for categoria in (red, servidores, self.categoria):
            for prioridad in ('BAJA', 'MEDIA', 'ALTA', 'CRITICA', None):
                with self.subTest(categoria=categoria.nombre, prioridad=prioridad):
                    datos = {
                        'titulo': 'Prueba R03', 'descripcion': 'Solicitud de soporte para probar prioridad.',
                        'area': self.area.pk, 'categoria': categoria.pk,
                        'ubicacion': 'Laboratorio', 'equipo_afectado': 'Equipo de prueba',
                    }
                    if prioridad is not None:
                        datos['prioridad'] = prioridad
                    r = self.client.post('/api/soporte/tickets/', datos, format='json')
                    self.assertEqual(r.status_code, 201, r.data)
                    ticket = Ticket.objects.get(pk=r.data['ticket']['id'])
                    esperada = prioridad if categoria == self.categoria else 'ALTA'
                    self.assertEqual(r.data['ticket']['prioridad'], esperada)
                    self.assertEqual(ticket.prioridad, esperada)
                    self.assertEqual(ticket.estado.codigo, 'NUEVO')
                    self.assertIsNone(ticket.tecnico_asignado_id)
                    self.assertIsNone(ticket.clasificado_en)
                    self.assertIsNone(ticket.sla_horas)

    def test_r03_creacion_comun_conserva_tickets_historicos(self):
        ticket = Ticket.objects.create(
            codigo='SOP-R03-HISTORICO', titulo='Creación desde el modelo', descripcion='Descripción',
            solicitante=self.usuarios['SOLICITANTE'], area=self.area,
            ubicacion='Laboratorio', equipo_afectado='Router',
            categoria=CategoriaTicket.objects.get(codigo='RED'),
            estado=EstadoTicket.objects.get(codigo='NUEVO'), prioridad='BAJA',
        )
        ticket.refresh_from_db()
        self.assertEqual(ticket.prioridad, 'ALTA')
        # Simula un registro anterior a R03 y comprueba que guardarlo no lo reclasifica.
        Ticket.objects.filter(pk=ticket.pk).update(prioridad='BAJA')
        ticket.refresh_from_db()
        ticket.titulo = 'Título editado'
        ticket.save()
        ticket.refresh_from_db()
        self.assertEqual(ticket.prioridad, 'BAJA')
        self.autenticar('SOLICITANTE')
        r = self.client.patch(f'/api/soporte/tickets/{ticket.pk}/', {'prioridad': 'ALTA'}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        ticket.refresh_from_db()
        self.assertEqual(ticket.prioridad, 'BAJA')

    def test_r03_conserva_clasificacion_sla_y_asignacion(self):
        self.autenticar('SOLICITANTE')
        r = self.client.post('/api/soporte/tickets/', {
            'titulo': 'Red sin servicio', 'descripcion': 'No hay conexión en laboratorio.',
            'area': self.area.pk, 'categoria': CategoriaTicket.objects.get(codigo='RED').pk,
            'ubicacion': 'Laboratorio', 'equipo_afectado': 'Router', 'prioridad': 'BAJA',
        }, format='json')
        self.assertEqual(r.status_code, 201, r.data)
        pk = r.data['ticket']['id']
        self.autenticar('JEFE_UTIC')
        self.assertEqual(self.client.post(f'/api/soporte/tickets/{pk}/validar-ticket/', {}).status_code, 200)
        datos_asignacion = {'tecnico_id': self.usuarios['ESPECIALISTA'].pk}
        r = self.client.post(f'/api/soporte/tickets/{pk}/designar-revision/', datos_asignacion, format='json')
        self.assertEqual(r.status_code, 400, r.data)
        self.assertIsNone(Ticket.objects.get(pk=pk).tecnico_asignado_id)
        # R03 es de creación: UTIC conserva la clasificación posterior y su SLA.
        r = self.client.post(f'/api/soporte/tickets/{pk}/clasificar-prioridad/', {
            'prioridad': 'MEDIA', 'criterio_tecnico': 'Existe una conexión de respaldo.',
        }, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        ticket = Ticket.objects.get(pk=pk)
        self.assertEqual(ticket.prioridad, 'MEDIA')
        self.assertIsNotNone(ticket.clasificado_en)
        self.assertIsNotNone(ticket.sla_horas)
        r = self.client.post(f'/api/soporte/tickets/{pk}/designar-revision/', datos_asignacion, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        ticket.refresh_from_db()
        self.assertEqual(ticket.tecnico_asignado_id, self.usuarios['ESPECIALISTA'].pk)
        self.assertEqual(ticket.estado.codigo, 'ASIGNADO')

    def crear_ticket_en_ejecucion(self, titulo, equipo):
        """Lleva un ticket hasta EN_EJECUCION (registrado, validado,
        clasificado, asignado y diagnosticado) para poder probar el
        subflujo de compra de componente."""

        self.autenticar("SOLICITANTE")
        r = self.client.post("/api/soporte/tickets/", {
            "titulo": titulo,
            "descripcion": f"{titulo} - descripción de prueba.",
            "area": self.area.id,
            "ubicacion": "Laboratorio 2",
            "equipo_afectado": equipo,
            "categoria": self.categoria.id,
            "evidencia_archivo": SimpleUploadedFile(
                "evidencia.jpg", b"contenido-de-prueba", content_type="image/jpeg"
            ),
        }, format="multipart")
        self.assertEqual(r.status_code, 201, r.data)
        pk = r.data["ticket"]["id"] if "ticket" in r.data else r.data["id"]

        self.autenticar("JEFE_UTIC")
        r = self.client.post(f"/api/soporte/tickets/{pk}/validar-ticket/", {}, format="json")
        self.assertEqual(r.status_code, 200, r.data)

        r = self.client.post(f"/api/soporte/tickets/{pk}/clasificar-prioridad/", {
            "prioridad": "ALTA",
            "criterio_tecnico": "Afecta clases del laboratorio.",
        }, format="json")
        self.assertEqual(r.status_code, 200, r.data)

        r = self.client.post(f"/api/soporte/tickets/{pk}/designar-revision/", {
            "tecnico_id": self.usuarios["ESPECIALISTA"].id,
        }, format="json")
        self.assertEqual(r.status_code, 200, r.data)

        self.autenticar("ESPECIALISTA")
        r = self.client.post(f"/api/soporte/tickets/{pk}/iniciar-atencion/", {}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        r = self.client.post(f"/api/soporte/tickets/{pk}/registrar-diagnostico/", {
            "diagnostico": "Componente dañado, requiere reemplazo.",
            "plan_solucion": "Solicitar el componente y reemplazarlo.",
        }, format="json")
        self.assertEqual(r.status_code, 200, r.data)

        return pk

    def test_especialista_solicita_jefe_aprueba_genera_expediente_vinculado(self):
        pk = self.crear_ticket_en_ejecucion("Monitor no enciende", "Monitor Dell")

        # El Especialista asignado solicita el componente con su
        # cotización — todavía no existe ningún expediente de compra.
        self.autenticar("ESPECIALISTA")
        r = self.client.post(f"/api/soporte/tickets/{pk}/solicitar-requerimiento-componente/", {
            "informe_compra": SimpleUploadedFile("informe.pdf", b"informe con cuadros"),
            "cotizacion_archivo": SimpleUploadedFile("cotizacion.pdf", b"cotizacion", content_type="application/pdf"),
            "componente_requerido": "Fuente de monitor",
            "especificaciones_tecnicas": "Fuente 19V 2A",
            "cantidad_componente": 2,
            "justificacion_compra": "Es indispensable para recuperar el monitor.",
            "costo_estimado": "250.00",
        }, format="multipart")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["ticket"]["estado_codigo"], "EN_EJECUCION")
        self.assertFalse(r.data["ticket"]["codigo_compra_vinculada"])

        # Mientras la viabilidad no se evalúe, no se puede reparar.
        r = self.client.post(f"/api/soporte/tickets/{pk}/registrar-intervencion/", {
            "solucion": "Se reemplazó la fuente.",
        }, format="json")
        self.assertEqual(r.status_code, 409, r.data)

        # Jefe de UTIC evalúa la viabilidad: al aprobarla, recién
        # ahí se genera el expediente real y vinculado en Compras.
        self.autenticar("JEFE_UTIC")
        informe_generado = Ticket.objects.get(pk=pk).informe_compra.name
        r = self.client.get(f"/api/soporte/tickets/{pk}/informe-requerimiento-pdf/")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(b"".join(r.streaming_content).startswith(b"%PDF-"))
        self.assertEqual(Ticket.objects.get(pk=pk).informe_compra.name, informe_generado)
        r = self.client.post(f"/api/soporte/tickets/{pk}/validar-viabilidad-compra/", {}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        ticket = Ticket.objects.get(pk=pk)
        self.assertEqual(ticket.estado_compra_componente, "VIABLE")
        self.assertEqual(ticket.informe_compra.name, informe_generado)
        self.assertFalse(ticket.codigo_compra_vinculada)
        self.assertFalse(SolicitudCompra.objects.filter(ticket_soporte_id=pk).exists())
        r = self.client.post(f"/api/soporte/tickets/{pk}/evaluar-viabilidad-compra/", {"viable": True}, format="json")
        self.assertEqual(r.status_code, 400, r.data)
        r = self.client.post(f"/api/soporte/tickets/{pk}/evaluar-viabilidad-compra/", {
            "poa": SimpleUploadedFile("poa.pdf", b"poa"),
            "pedido": SimpleUploadedFile("proveido.pdf", b"proveido"),
            "viable": True,
        }, format="multipart")
        self.assertEqual(r.status_code, 200, r.data)

        codigo_compra = r.data["ticket"]["codigo_compra_vinculada"]
        self.assertTrue(codigo_compra)

        solicitud = SolicitudCompra.objects.get(codigo=codigo_compra)
        self.assertEqual(solicitud.origen_modulo, "SOPORTE")
        self.assertEqual(solicitud.ticket_soporte_id, pk)
        self.assertEqual(solicitud.solicitante_id, self.usuarios["ESPECIALISTA"].id)
        self.assertEqual(solicitud.cantidad, 2)
        self.assertTrue(solicitud.informe)
        self.assertTrue(solicitud.proforma)
        self.assertTrue(solicitud.poa)
        self.assertTrue(solicitud.pedido)
        self.assertEqual(solicitud.informe.read(5), b"%PDF-")
        self.assertEqual(solicitud.proforma.read(), b"cotizacion")

        # No se puede duplicar la solicitud de compra para el
        # mismo ticket.
        self.autenticar("ESPECIALISTA")
        r = self.client.post(f"/api/soporte/tickets/{pk}/solicitar-requerimiento-componente/", {
            "informe_compra": SimpleUploadedFile("informe.pdf", b"informe con cuadros"),
            "cotizacion_archivo": SimpleUploadedFile("cotizacion.pdf", b"cotizacion", content_type="application/pdf"),
            "componente_requerido": "Otro componente",
        }, format="multipart")
        self.assertEqual(r.status_code, 409, r.data)

        # Aprobar la viabilidad no basta: el flujo técnico sigue en pausa
        # hasta que Almacén entregue físicamente el componente.
        self.autenticar("ESPECIALISTA")
        r = self.client.post(f"/api/soporte/tickets/{pk}/registrar-intervencion/", {
            "solucion": "Se reemplazó la fuente.",
        }, format="json")
        self.assertEqual(r.status_code, 409, r.data)

        # Almacén despacha el componente: eso reanuda la atención técnica.
        ticket = Ticket.objects.get(pk=pk)
        ticket.estado_compra_componente = "ENTREGADA"
        ticket.componente_entregado_en = timezone.now()
        ticket.save(update_fields=["estado_compra_componente", "componente_entregado_en"])

        r = self.client.post(f"/api/soporte/tickets/{pk}/registrar-intervencion/", {
            "solucion": "Se reemplazó la fuente.",
        }, format="json")
        self.assertEqual(r.status_code, 200, r.data)

    def test_jefe_utic_marca_no_viable_cierra_ticket_sin_compra(self):
        pk = self.crear_ticket_en_ejecucion("Necesita GPU de alta gama", "PC laboratorio")

        self.autenticar("ESPECIALISTA")
        r = self.client.post(f"/api/soporte/tickets/{pk}/solicitar-requerimiento-componente/", {
            "informe_compra": SimpleUploadedFile("informe.pdf", b"informe con cuadros"),
            "cotizacion_archivo": SimpleUploadedFile("cotizacion.pdf", b"cotizacion", content_type="application/pdf"),
            "componente_requerido": "GPU de alta gama",
            "especificaciones_tecnicas": "GPU compatible con el equipo",
            "justificacion_compra": "El equipo no puede operar sin reemplazo.",
            "costo_estimado": "499.00",
        }, format="multipart")
        self.assertEqual(r.status_code, 200, r.data)

        self.autenticar("JEFE_UTIC")
        r = self.client.post(f"/api/soporte/tickets/{pk}/evaluar-viabilidad-compra/", {
            "viable": False,
            "motivo_no_viable": "Excede el presupuesto de caja chica.",
        }, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["ticket"]["estado_codigo"], "CERRADO_SIN_COMPRA")
        self.assertFalse(r.data["ticket"]["activo"])
        self.assertFalse(SolicitudCompra.objects.filter(ticket_soporte_id=pk).exists())

    def test_solicitante_no_puede_solicitar_componente(self):
        pk = self.crear_ticket_en_ejecucion("Teclado dañado", "Teclado Logitech")

        self.autenticar("SOLICITANTE")
        r = self.client.post(f"/api/soporte/tickets/{pk}/solicitar-requerimiento-componente/", {
            "informe_compra": SimpleUploadedFile("informe.pdf", b"informe con cuadros"),
            "cotizacion_archivo": SimpleUploadedFile("cotizacion.pdf", b"cotizacion", content_type="application/pdf"),
            "componente_requerido": "Teclado nuevo",
        }, format="multipart")
        self.assertEqual(r.status_code, 403, r.data)

    def test_especialista_no_puede_evaluar_viabilidad(self):
        pk = self.crear_ticket_en_ejecucion("Mouse dañado", "Mouse Logitech")

        self.autenticar("ESPECIALISTA")
        r = self.client.post(f"/api/soporte/tickets/{pk}/solicitar-requerimiento-componente/", {
            "informe_compra": SimpleUploadedFile("informe.pdf", b"informe con cuadros"),
            "cotizacion_archivo": SimpleUploadedFile("cotizacion.pdf", b"cotizacion", content_type="application/pdf"),
            "componente_requerido": "Mouse nuevo",
            "costo_estimado": "100.00",
            "especificaciones_tecnicas": "Mouse USB",
            "justificacion_compra": "El periférico actual no funciona.",
        }, format="multipart")
        self.assertEqual(r.status_code, 200, r.data)

        r = self.client.post(f"/api/soporte/tickets/{pk}/evaluar-viabilidad-compra/", {
            "poa": SimpleUploadedFile("poa.pdf", b"poa"),
            "pedido": SimpleUploadedFile("proveido.pdf", b"proveido"),
            "viable": True,
        }, format="multipart")
        self.assertEqual(r.status_code, 403, r.data)

    def test_borrador_requerimiento_permanece_visible_y_editable(self):
        pk = self.crear_ticket_en_ejecucion("Fuente pendiente", "PC")
        self.autenticar("ESPECIALISTA")
        r = self.client.post(f"/api/soporte/tickets/{pk}/guardar-borrador-requerimiento/", {
            "componente_requerido": "Fuente ATX",
            "cantidad_componente": 1,
        }, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["ticket"]["estado_compra_componente"], "BORRADOR")
        self.assertEqual(r.data["ticket"]["estado_codigo"], "EN_EJECUCION")

    def test_genera_informe_de_requerimiento_con_respaldo_opcional(self):
        pk = self.crear_ticket_en_ejecucion("Falta documentación", "PC")
        self.autenticar("ESPECIALISTA")
        r = self.client.post(f"/api/soporte/tickets/{pk}/solicitar-requerimiento-componente/", {
            "componente_requerido": "Fuente", "especificaciones_tecnicas": "ATX",
            "justificacion_compra": "Fuente quemada", "costo_estimado": "100.00",
        }, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(Ticket.objects.get(pk=pk).estado_compra_componente, 'SOLICITADA')
        self.assertFalse(SolicitudCompra.objects.filter(ticket_soporte_id=pk).exists())
        pk = self.crear_ticket_en_ejecucion("Con respaldo opcional", "PC")
        self.autenticar("ESPECIALISTA")
        r = self.client.post(f"/api/soporte/tickets/{pk}/solicitar-requerimiento-componente/", {
            "componente_requerido": "Fuente", "especificaciones_tecnicas": "ATX",
            "justificacion_compra": "Fuente quemada", "costo_estimado": "100.00",
            "cotizacion_archivo": SimpleUploadedFile("cotizacion.jpg", b"imagen", content_type="image/jpeg"),
        }, format="multipart")
        self.assertEqual(r.status_code, 200, r.data)
        ticket = Ticket.objects.get(pk=pk)
        self.assertTrue(ticket.informe_compra)
        self.assertTrue(ticket.informe_compra.name.endswith(".pdf"))

    def test_jefatura_completa_expediente_antiguo_y_daf_debe_reevaluar(self):
        pk = self.crear_ticket_en_ejecucion("Expediente antiguo", "PC")
        ticket = Ticket.objects.get(pk=pk)
        compra = SolicitudCompra.objects.create(
            codigo="CMP-LEGADO", titulo="Sin documentos", solicitante=ticket.solicitante,
            area=ticket.area, tipo="COMPONENTE", cantidad=1, ticket_soporte=ticket,
            origen_modulo="SOPORTE", estado="EVALUADO_PENDIENTE_CERTIFICACION",
        )
        url = f"/api/soporte/tickets/{pk}/completar-expediente/"
        self.autenticar("ESPECIALISTA")
        self.assertEqual(self.client.post(url, {}).status_code, 403)
        self.autenticar("JEFE_UTIC")
        self.assertEqual(self.client.post(url, {}).status_code, 400)
        r = self.client.post(url, {
            campo: SimpleUploadedFile(campo + ".pdf", campo.encode())
            for campo in ("informe", "proforma", "poa", "pedido")
        }, format="multipart")
        self.assertEqual(r.status_code, 200, r.data)
        compra.refresh_from_db()
        self.assertEqual(compra.estado, "CREADO_PENDIENTE_DAF")
        self.assertEqual(SolicitudCompra.objects.filter(ticket_soporte=ticket).count(), 1)
        self.assertEqual(self.client.post(url, {}).status_code, 409)

    def test_especialista_solo_lista_ordenes_propias(self):
        pk = self.crear_ticket_en_ejecucion("Orden propia", "PC")
        otro = Usuario.objects.create_user(
            username="otro_especialista", email="otro@emi.edu.bo",
            nombre_completo="Otro Especialista", password="Prueba#2026",
        )
        UsuarioRol.objects.create(
            usuario=otro, rol=Rol.objects.get(codigo="ESPECIALISTA"), activo=True,
        )
        self.client.force_authenticate(otro)
        r = self.client.get("/api/soporte/tickets/")
        self.assertEqual(r.status_code, 200, r.data)
        ids = [item["id"] for item in (r.data if isinstance(r.data, list) else r.data["results"])]
        self.assertNotIn(pk, ids)

    def test_conformidad_positiva_espera_informe_final_del_jefe(self):
        pk = self.crear_ticket_en_ejecucion("Equipo reparado", "PC")
        ticket = Ticket.objects.get(pk=pk)
        ticket.diagnostico = "Falla de memoria"
        ticket.solucion = "Memoria reinstalada"
        ticket.resultado_pruebas = "Pruebas satisfactorias"
        ticket.informe_tecnico = "Informe y cuadros registrados por el técnico."
        ticket.save(update_fields=[
            "estado", "diagnostico", "solucion", "resultado_pruebas", "informe_tecnico",
        ])

        firma_tecnico = [[[10, 20], [120, 60], [200, 30]]]
        url_pruebas = f"/api/soporte/tickets/{pk}/pruebas-tecnicas/"
        cuerpo = {"resultado_pruebas": ticket.resultado_pruebas, "informe_tecnico": ticket.informe_tecnico}
        self.assertEqual(self.client.post(url_pruebas, cuerpo, format="json").status_code, 400)
        ticket.refresh_from_db()
        self.assertEqual(ticket.estado.codigo, "EN_EJECUCION")
        r = self.client.post(url_pruebas, {**cuerpo, "firma": firma_tecnico}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        ticket.refresh_from_db()
        with ticket.informe_tecnico_pdf.open('rb') as archivo:
            self.assertIn(b'1.3 w', archivo.read())

        self.autenticar("SOLICITANTE")
        r = self.client.post(
            f"/api/soporte/tickets/{pk}/informar-conformidad/",
            {"conformidad": True, "observaciones": "El equipo funciona correctamente."},
            format="json",
        )
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["ticket"]["estado_codigo"], "PENDIENTE_INFORME_FINAL")
        self.assertIsNone(Ticket.objects.get(pk=pk).cerrado_en)
        from usuarios.models import DocumentoProceso
        self.assertEqual(DocumentoProceso.objects.get(soporte=ticket, tipo='Conformidad del solicitante').firma, [])

        self.autenticar("JEFE_UTIC")
        r = self.client.post(
            f"/api/soporte/tickets/{pk}/elaborar-informe-final/",
            {"informe_final": "Atención verificada y expediente validado.", "firma": [[[20, 30], [150, 80]]]},
            format="json",
        )
        self.assertEqual(r.status_code, 200, r.data)
        ticket.refresh_from_db()
        self.assertEqual(ticket.estado.codigo, "CERRADO")
        self.assertIsNotNone(ticket.cerrado_en)
        self.assertTrue(ticket.informe_final_pdf)
        with ticket.informe_final_pdf.open('rb') as archivo:
            pdf = archivo.read()
        self.assertIn(b'ESPECIALISTA', pdf)
        self.assertIn(b'JEFE_UTIC', pdf)
        self.assertEqual(pdf.count(b'1.3 w'), 2)

        self.autenticar("SOLICITANTE")
        r = self.client.post(
            f"/api/soporte/tickets/{pk}/elaborar-informe-jefe-carrera/",
            {"informe_jefe_carrera": "Trabajo revisado y conforme para conocimiento de Dirección."},
            format="json",
        )
        self.assertEqual(r.status_code, 200, r.data)
        ticket.refresh_from_db()
        self.assertTrue(ticket.informe_jefe_carrera_pdf)
        self.assertIsNotNone(ticket.informe_jefe_carrera_en)

    def test_no_conformidad_exige_motivo_y_conserva_historial(self):
        pk = self.crear_ticket_en_ejecucion("Falla persistente", "Impresora")
        ticket = Ticket.objects.get(pk=pk)
        ticket.estado = EstadoTicket.objects.get(codigo="PENDIENTE_CONFORMIDAD")
        ticket.diagnostico = "Atasco del alimentador"
        ticket.solucion = "Limpieza de rodillos"
        ticket.resultado_pruebas = "Impresión de prueba"
        ticket.save(update_fields=["estado", "diagnostico", "solucion", "resultado_pruebas"])

        self.autenticar("SOLICITANTE")
        r = self.client.post(
            f"/api/soporte/tickets/{pk}/informar-conformidad/",
            {"conformidad": False, "observaciones": ""},
            format="json",
        )
        self.assertEqual(r.status_code, 400, r.data)

        r = self.client.post(
            f"/api/soporte/tickets/{pk}/informar-conformidad/",
            {"conformidad": False, "observaciones": "El papel vuelve a atascarse."},
            format="json",
        )
        self.assertEqual(r.status_code, 200, r.data)
        ticket.refresh_from_db()
        self.assertEqual(ticket.estado.codigo, "EN_EJECUCION")
        self.assertEqual(ticket.rework_count, 1)
        self.assertEqual(ticket.diagnostico, "Atasco del alimentador")
        self.assertEqual(ticket.solucion, "Limpieza de rodillos")
        self.assertEqual(ticket.resultado_pruebas, "Impresión de prueba")

    def test_recibir_orden_es_idempotente(self):
        pk = self.crear_ticket_en_ejecucion("Recepción idempotente", "PC")
        ticket = Ticket.objects.get(pk=pk)
        ticket.estado = EstadoTicket.objects.get(codigo="EN_DIAGNOSTICO")
        ticket.diagnostico = ""
        ticket.save(update_fields=["estado", "diagnostico"])

        self.autenticar("ESPECIALISTA")
        r = self.client.post(f"/api/soporte/tickets/{pk}/iniciar-atencion/", {}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["ticket"]["estado_codigo"], "EN_DIAGNOSTICO")

    def test_diagnostico_puede_recuperar_recepcion_interrumpida(self):
        pk = self.crear_ticket_en_ejecucion("Recepción interrumpida", "Proyector")
        ticket = Ticket.objects.get(pk=pk)
        ticket.estado = EstadoTicket.objects.get(codigo="ASIGNADO")
        ticket.diagnostico = ""
        ticket.inicio_atencion_en = None
        ticket.save(update_fields=["estado", "diagnostico", "inicio_atencion_en"])

        self.autenticar("ESPECIALISTA")
        r = self.client.post(
            f"/api/soporte/tickets/{pk}/registrar-diagnostico/",
            {
                "diagnostico": "Fuente de alimentación defectuosa.",
                "plan_solucion": "Reemplazar la fuente.",
                "requiere_compra": True,
            },
            format="json",
        )
        self.assertEqual(r.status_code, 200, r.data)
        ticket.refresh_from_db()
        self.assertEqual(ticket.estado.codigo, "EN_EJECUCION")
        self.assertIsNotNone(ticket.inicio_atencion_en)

    def test_r01_limite_total_api_sin_registros_parciales(self):
        # El costo es el total de la cotización, incluso con cantidad > 1.
        for limite, montos in (("1000", ("999", "1000", "1000.01", "1001")), ("800", ("800", "900"))):
            with override_settings(SIA_LIMITE_CAJA_CHICA=Decimal(limite)):
                for monto in montos:
                    pk = self.crear_ticket_en_ejecucion("R01", "Equipo")
                    self.autenticar("ESPECIALISTA")
                    objeto = Ticket.objects.get(pk=pk)
                    anterior = (Ticket.objects.filter(pk=pk).values().get())
                    compras = SolicitudCompra.objects.count()
                    r = self.client.post(f"/api/soporte/tickets/{pk}/solicitar-requerimiento-componente/", {
                        "componente_requerido": "Componentes solicitados", "especificaciones_tecnicas": "Compatibles",
                        "justificacion_compra": "Reemplazo necesario", "cantidad_componente": 3,
                        "costo_estimado": monto,
                        **{f"proveedor_{i}": f"Proveedor {i}" for i in range(1, 4)},
                        **{f"precio_unitario_{i}": "300" for i in range(1, 4)},
                        **{f"cotizacion_{i}": SimpleUploadedFile(f"cotizacion{i}.pdf", f"cotizacion {i}".encode(), content_type="application/pdf") for i in range(1, 4)},
                    }, format="multipart")
                    rechazado = Decimal(monto) > Decimal(limite)
                    self.assertEqual(r.status_code, 400 if rechazado else 200, r.data)
                    self.assertEqual(SolicitudCompra.objects.count(), compras)
                    if rechazado:
                        self.assertEqual(Ticket.objects.filter(pk=pk).values().get(), anterior)
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
                    pk = self.crear_ticket_en_ejecucion("R02", "Equipo")
                    self.autenticar("ESPECIALISTA")
                    usuario = self.usuarios["ESPECIALISTA"]
                    usuario.must_change_password = False
                    usuario.save(update_fields=['must_change_password'])
                    token = Token.objects.get_or_create(user=usuario)[0]
                    self.client.force_authenticate(user=usuario, token=token)
                    anterior = Ticket.objects.filter(pk=pk).values().get()
                    registros = CotizacionCompra.objects.count()
                    archivos = set(Path(settings.SIA_PRIVATE_ROOT).rglob('*'))
                    datos = {
                        "componente_requerido": "Componentes", "cantidad_componente": 2,
                        "especificaciones_tecnicas": "Compatibles", "justificacion_compra": "Necesarios",
                        "costo_estimado": monto,
                    }
                    if Decimal(monto) <= 500 and numero:
                        datos['cotizacion_archivo'] = SimpleUploadedFile('respaldo.png', b'imagen', content_type='image/png')
                    else:
                        for i in range(1, numero + 1):
                            datos[f'proveedor_{i}'] = '  PROVEEDOR  ' if repetido else f'Proveedor {i}'
                            datos[f'precio_unitario_{i}'] = '350'
                            datos[f'cotizacion_{i}'] = SimpleUploadedFile(f'cotizacion{i}.pdf', f'cotizacion {i}'.encode(), content_type='application/pdf')
                    r = self.client.post(f"/api/soporte/tickets/{pk}/solicitar-requerimiento-componente/", datos, format='multipart')
                    self.assertEqual(r.status_code, esperado, r.data)
                    if esperado == 400:
                        self.assertEqual(Ticket.objects.filter(pk=pk).values().get(), anterior)
                        self.assertEqual(CotizacionCompra.objects.count(), registros)
                        self.assertEqual(set(Path(settings.SIA_PRIVATE_ROOT).rglob('*')), archivos)
                        self.assertFalse(SolicitudCompra.objects.filter(ticket_soporte_id=pk).exists())
                        if monto == '1001':
                            self.assertIn('el monto total supera', r.data['costo_estimado'])
                    elif Decimal(monto) > 500:
                        objeto = Ticket.objects.get(pk=pk)
                        self.assertEqual(objeto.cotizaciones.count(), 3)
                        detalle = self.client.get(f"/api/soporte/tickets/{pk}/")
                        self.assertEqual(len(detalle.data['cotizaciones']), 3)
                        for cotizacion in detalle.data['cotizaciones']:
                            archivo = APIClient().get(cotizacion['documento_url'])
                            self.assertEqual(archivo.status_code, 200)
                            self.assertTrue(b''.join(archivo.streaming_content).startswith(b'cotizacion'))
                            archivo.close()
                            self.assertEqual(APIClient().get(cotizacion['documento_url'].split('?')[0]).status_code, 401)

                    if esperado == 200:
                        self.autenticar("JEFE_UTIC")
                        r = self.client.post(f"/api/soporte/tickets/{pk}/validar-viabilidad-compra/", {}, format='json')
                        self.assertEqual(r.status_code, 200, r.data)
                        r = self.client.post(f"/api/soporte/tickets/{pk}/evaluar-viabilidad-compra/", {
                            'viable': True,
                            'poa': SimpleUploadedFile('poa.pdf', b'poa', content_type='application/pdf'),
                            'pedido': SimpleUploadedFile('pedido.pdf', b'pedido', content_type='application/pdf'),
                        }, format='multipart')
                        self.assertEqual(r.status_code, 200, r.data)
                        solicitud = SolicitudCompra.objects.get(ticket_soporte_id=pk)
                        self.assertEqual(solicitud.cotizaciones.count(), 3 if Decimal(monto) > 500 else 0)
                        from compras.expediente import documentos_faltantes
                        self.assertEqual(documentos_faltantes(solicitud), [])
