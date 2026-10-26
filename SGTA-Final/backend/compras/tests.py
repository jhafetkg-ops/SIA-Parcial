from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from rest_framework.test import APITestCase
from rest_framework.test import APITransactionTestCase
from django.test import override_settings
from decimal import Decimal

from usuarios.models import Area, Rol, Usuario, UsuarioRol


class FlujoCajaChicaTests(APITransactionTestCase):
    serialized_rollback = True
    def setUp(self):
        # Carga el catálogo real de roles/permisos (Permiso +
        # RolPermiso) para que las pruebas verifiquen la misma
        # autorización que corre en producción (tiene_permiso).
        call_command("cargar_permisos_sigta")

        self.area = Area.objects.create(codigo="TEST", nombre="Área de prueba")
        self.usuarios = {}
        for codigo in ("SOLICITANTE", "DAF", "TESORERIA", "DIRECTOR", "ENCARGADO_COMPRAS_ALMACEN", "ADMIN"):
            rol = Rol.objects.get(codigo=codigo)
            usuario = Usuario.objects.create_user(
                username=codigo.lower(), email=f"{codigo.lower()}@emi.edu.bo",
                nombre_completo=codigo, password="Prueba#2026",
            )
            UsuarioRol.objects.create(usuario=usuario, rol=rol, activo=True)
            self.usuarios[codigo] = usuario

    def archivo(self, nombre="archivo.pdf"):
        return SimpleUploadedFile(nombre, b"contenido de prueba", content_type="application/pdf")

    def autenticar(self, rol):
        self.client.force_authenticate(self.usuarios[rol])

    def compra_r09(self, monto, codigo, estado='VERIFICADO_PENDIENTE_AUTORIZACION'):
        from compras.models import SolicitudCompra
        return SolicitudCompra.objects.create(
            codigo=codigo, titulo='Compra R09', descripcion='Prueba de fondo mensual',
            solicitante=self.usuarios['SOLICITANTE'], area=self.area, tipo='BIEN', cantidad=1,
            monto_estimado=Decimal(monto), estado=estado,
        )

    @override_settings(SIA_FONDO_MENSUAL=Decimal('5000'))
    def test_r09_fondo_aprobaciones_y_saldo_exacto(self):
        from usuarios.models import DocumentoProceso
        from compras.tesoreria import TIPO_APROBACION_CAJA_CHICA
        self.autenticar('DIRECTOR')
        self.compra_r09('900', 'R09-PENDIENTE', 'CREADO_PENDIENTE_DAF')
        self.compra_r09('300', 'R09-RECHAZADA', 'RECHAZADO')
        self.compra_r09('9000', 'R09-FINANZAS', 'APROBADO_PARA_DESEMBOLSO')
        self.assertEqual(self.client.get('/api/caja-chica/saldo/').data['saldo_disponible'], '5000.00')
        for indice, monto, esperado in ((0, '500', '4500.00'), (1, '1000', '3500.00'), (2, '1500', '2000.00'), (3, '1500', '500.00')):
            compra = self.compra_r09(monto, f'R09-APR-{indice}')
            r = self.client.post(f'/api/compras/solicitudes/{compra.pk}/visto-bueno-director/', {}, format='json')
            self.assertEqual(r.status_code, 200, r.data)
            self.assertEqual(self.client.get('/api/caja-chica/saldo/').data['saldo_disponible'], esperado)
            self.assertEqual(self.client.post(f'/api/compras/solicitudes/{compra.pk}/visto-bueno-director/', {}).status_code, 409)
        rechazada = self.compra_r09('600', 'R09-SIN-SALDO')
        anterior = type(rechazada).objects.filter(pk=rechazada.pk).values().get()
        r = self.client.post(f'/api/compras/solicitudes/{rechazada.pk}/visto-bueno-director/', {})
        self.assertEqual(r.status_code, 400, r.data)
        self.assertIn('saldo disponible de Caja Chica es insuficiente', r.data['detalle'])
        self.assertEqual(type(rechazada).objects.filter(pk=rechazada.pk).values().get(), anterior)
        exacta = self.compra_r09('500', 'R09-SALDO-EXACTO')
        self.assertEqual(self.client.post(f'/api/compras/solicitudes/{exacta.pk}/visto-bueno-director/', {}).status_code, 200)
        saldo = self.client.get('/api/caja-chica/saldo/').data
        self.assertEqual(saldo['total_aprobado'], '5000.00')
        self.assertEqual(saldo['saldo_disponible'], '0.00')
        self.assertEqual(DocumentoProceso.objects.filter(tipo=TIPO_APROBACION_CAJA_CHICA).count(), 5)
        # Un guardado posterior no cambia el importe aprobado de la instantánea.
        exacta.refresh_from_db()
        exacta.monto_estimado = Decimal('900')
        exacta.estado = 'FONDOS_DESEMBOLSADOS'
        exacta.save()
        self.assertEqual(self.client.get('/api/caja-chica/saldo/').data['total_aprobado'], '5000.00')

    @override_settings(SIA_FONDO_MENSUAL=Decimal('5000'))
    def test_r09_periodo_la_paz_y_antecedentes_sin_fecha(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from unittest.mock import patch
        from auditoria.models import Bitacora
        zona = ZoneInfo('America/La_Paz')
        for codigo, fecha, monto in (
            ('R09-LEGADO', datetime(2026, 11, 1, 2, 30, tzinfo=ZoneInfo('UTC')), '100'),
            ('R09-OTRO-ANIO', datetime(2025, 10, 31, 20, tzinfo=zona), '300'),
        ):
            compra = self.compra_r09(monto, codigo, 'CERRADO_ARCHIVADO')
            registro = Bitacora.objects.create(accion='VISTO_BUENO_DIRECTOR', modulo='Compras', detalle=f'{codigo}: Director autorizó.')
            Bitacora.objects.filter(pk=registro.pk).update(fecha=fecha)
        self.autenticar('DIRECTOR')
        with patch('django.utils.timezone.now', return_value=datetime(2026, 10, 31, 23, tzinfo=zona)):
            saldo = self.client.get('/api/caja-chica/saldo/').data
            self.assertEqual(saldo['mes'], '2026-10')
            self.assertEqual(saldo['saldo_disponible'], '4900.00')
        with patch('django.utils.timezone.now', return_value=datetime(2026, 11, 1, 0, tzinfo=zona)):
            saldo = self.client.get('/api/caja-chica/saldo/').data
            self.assertEqual(saldo['mes'], '2026-11')
            self.assertEqual(saldo['saldo_disponible'], '5000.00')
            historica = self.compra_r09('100', 'R09-SIN-FECHA', 'APROBADO_PARA_DESEMBOLSO')
            pendiente = self.compra_r09('100', 'R09-BLOQUEADA')
            saldo = self.client.get('/api/caja-chica/saldo/').data
            self.assertFalse(saldo['saldo_verificable'])
            self.assertIsNone(saldo['saldo_disponible'])
            self.assertIn(historica.codigo, saldo['aprobaciones_sin_respaldo'])
            self.assertEqual(self.client.post(f'/api/compras/solicitudes/{pendiente.pk}/visto-bueno-director/', {}).status_code, 400)
            pendiente.refresh_from_db()
            self.assertEqual(pendiente.estado, 'VERIFICADO_PENDIENTE_AUTORIZACION')

    def test_r09_saldo_y_snapshot_solo_para_roles_financieros(self):
        from usuarios.models import DocumentoProceso
        from compras.tesoreria import TIPO_APROBACION_CAJA_CHICA
        self.client.force_authenticate(user=None)
        self.assertEqual(self.client.get('/api/caja-chica/saldo/').status_code, 401)
        for rol in ('SOLICITANTE', 'ENCARGADO_COMPRAS_ALMACEN'):
            self.autenticar(rol)
            self.assertEqual(self.client.get('/api/caja-chica/saldo/').status_code, 403)
        for rol in ('DIRECTOR', 'DAF', 'TESORERIA', 'ADMIN'):
            self.autenticar(rol)
            self.assertEqual(self.client.get('/api/caja-chica/saldo/').status_code, 200)
        compra = self.compra_r09('500', 'R09-SEGURIDAD')
        self.autenticar('DIRECTOR')
        self.assertEqual(self.client.post(f'/api/compras/solicitudes/{compra.pk}/visto-bueno-director/', {}).status_code, 200)
        documento = DocumentoProceso.objects.get(compra=compra, tipo=TIPO_APROBACION_CAJA_CHICA)
        self.autenticar('SOLICITANTE')
        documentos = self.client.get(f'/api/compras/solicitudes/{compra.pk}/documentos/')
        self.assertEqual(documentos.status_code, 200)
        self.assertNotIn(documento.pk, [d['id'] for d in documentos.data])
        self.assertEqual(self.client.get(f'/api/compras/solicitudes/{compra.pk}/documentos/{documento.pk}/pdf/').status_code, 403)

    @override_settings(SIA_FONDO_MENSUAL=Decimal('1000'))
    def test_r09_aprobaciones_concurrentes_postgresql(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from django.db import connection, connections
        from rest_framework.test import APIClient
        from usuarios.models import DocumentoProceso
        from compras.tesoreria import TIPO_APROBACION_CAJA_CHICA
        if connection.vendor != 'postgresql':
            self.skipTest('R09 requiere PostgreSQL real para comprobar el bloqueo asesor.')
        candidatos = [self.compra_r09('700', f'R09-PG-{i}').pk for i in range(2)]
        segundo = Usuario.objects.create_user(username='director-r09', email='director-r09@example.invalid', nombre_completo='Otro Director')
        UsuarioRol.objects.create(usuario=segundo, rol=Rol.objects.get(codigo='DIRECTOR'))
        barrera = Barrier(2)

        def sincronizar(execute, sql, params, many, context):
            if 'pg_advisory_xact_lock' in sql:
                barrera.wait(timeout=20)
            return execute(sql, params, many, context)

        def aprobar(datos):
            pk, usuario = datos
            try:
                cliente = APIClient()
                cliente.force_authenticate(usuario)
                with connections['default'].execute_wrapper(sincronizar):
                    return cliente.post(f'/api/compras/solicitudes/{pk}/visto-bueno-director/', {}).status_code
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as ejecutor:
            resultados = list(ejecutor.map(aprobar, zip(candidatos, (self.usuarios['DIRECTOR'], segundo))))
        self.assertEqual(sorted(resultados), [200, 400])
        self.assertEqual(DocumentoProceso.objects.filter(tipo=TIPO_APROBACION_CAJA_CHICA).count(), 1)
        self.autenticar('DIRECTOR')
        self.assertEqual(self.client.get('/api/caja-chica/saldo/').data['saldo_disponible'], '300.00')

    @override_settings(SIA_FONDO_MENSUAL=Decimal('5000'))
    def test_r09_pdf_recibo_conserva_saldo_al_aprobar(self):
        import os
        from pathlib import Path
        from io import BytesIO
        from pypdf import PdfReader
        self.autenticar('DIRECTOR')
        primera = self.compra_r09('500', 'R09-PDF-PRIMERA')
        segunda = self.compra_r09('1000', 'R09-PDF-SEGUNDA')
        for compra in (primera, segunda):
            self.assertEqual(self.client.post(f'/api/compras/solicitudes/{compra.pk}/visto-bueno-director/', {}).status_code, 200)
        self.autenticar('TESORERIA')
        with override_settings(SIA_FONDO_MENSUAL=Decimal('8000')):
            r = self.client.post(f'/api/compras/solicitudes/{primera.pk}/recibos-tesoreria/', {
                'monto_desembolsado': '500', 'responsable_adquisicion': 'Juan Pérez', 'tipo_desembolso': 'Efectivo',
            }, format='json')
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(r.data['datos']['saldo_aprobacion']['saldo_disponible'], '4500.00')
        archivo = self.client.get(r.data['original_url'])
        contenido = b''.join(archivo.streaming_content)
        texto = '\n'.join(p.extract_text() for p in PdfReader(BytesIO(contenido)).pages)
        for esperado in ('5000.00', '500.00', '4500.00', 'SALDO AL APROBAR'):
            self.assertIn(esperado, texto)
        if os.environ.get('SIA_R09_PDF_DIR'):
            destino = Path(os.environ['SIA_R09_PDF_DIR'])
            destino.mkdir(parents=True, exist_ok=True)
            (destino / 'recibo-r09.pdf').write_bytes(contenido)

    def test_r09_aprobacion_y_snapshot_son_atomicos(self):
        from unittest.mock import patch
        from auditoria.models import Bitacora
        from usuarios.models import DocumentoProceso
        compra = self.compra_r09('500', 'R09-ATOMICA')
        anterior = type(compra).objects.filter(pk=compra.pk).values().get()
        self.autenticar('DIRECTOR')
        with patch('usuarios.documentos.emitir_documento', side_effect=RuntimeError('Fallo del respaldo')):
            with self.assertRaises(RuntimeError):
                self.client.post(f'/api/compras/solicitudes/{compra.pk}/visto-bueno-director/', {})
        self.assertEqual(type(compra).objects.filter(pk=compra.pk).values().get(), anterior)
        self.assertFalse(DocumentoProceso.objects.filter(compra=compra).exists())
        self.assertFalse(Bitacora.objects.filter(accion='VISTO_BUENO_DIRECTOR').exists())

    def test_daf_no_aprueba_incompletos_y_solo_certifica_evaluados(self):
        from compras.models import SolicitudCompra
        self.autenticar("DAF")
        solicitud = SolicitudCompra.objects.create(
            codigo="CMP-TEST-DOCUMENTOS", titulo="Expediente incompleto",
            solicitante=self.usuarios["SOLICITANTE"], area=self.area,
            tipo="BIEN", cantidad=1, origen_modulo="SOPORTE",
            estado="CREADO_PENDIENTE_DAF",
        )
        url = f"/api/compras/solicitudes/{solicitud.pk}"
        self.assertEqual(self.client.post(url + "/evaluar-daf/", {"califica": True}).status_code, 400)
        solicitud.refresh_from_db()
        self.assertEqual(solicitud.estado, "CREADO_PENDIENTE_DAF")
        self.assertEqual(self.client.get("/api/compras/solicitudes/?bandeja=certificacion").data, [])
        self.assertEqual(self.client.post(url + "/certificar-daf/", {
            "certificacion_presupuestaria": self.archivo(),
        }, format="multipart").status_code, 409)
        for campo in ("informe", "poa", "proforma"):
            setattr(solicitud, campo, self.archivo(campo + ".pdf"))
        solicitud.save()
        self.assertEqual(self.client.post(url + "/evaluar-daf/", {"califica": True}).status_code, 400)
        solicitud.pedido = self.archivo("proveido.pdf")
        solicitud.save()
        self.assertEqual(self.client.get("/api/compras/solicitudes/?bandeja=certificacion").data, [])
        self.assertEqual(self.client.post(url + "/evaluar-daf/", {"califica": True}).status_code, 200)
        bandeja = self.client.get("/api/compras/solicitudes/?bandeja=certificacion").data
        self.assertEqual([r["id"] for r in bandeja], [solicitud.pk])

    def test_monto_rechaza_letras_signos_exponentes_y_decimales_excesivos(self):
        from compras.serializers import MontoEstimadoField
        from rest_framework.exceptions import ValidationError
        campo = MontoEstimadoField(max_digits=12, decimal_places=2, min_value=0)
        for valor in ("abc", "100$", "-1", "+2", "1e3", "NaN", "Infinity", "12.345"):
            with self.subTest(valor=valor), self.assertRaises(ValidationError):
                campo.run_validation(valor)
        self.assertEqual(str(campo.run_validation("1250.50")), "1250.50")

    def test_bandeja_direccion_excluye_compras_propias(self):
        from compras.models import SolicitudCompra
        director = self.usuarios["DIRECTOR"]
        propia = SolicitudCompra.objects.create(
            codigo="CMP-DIR-PROPIA", titulo="Compra propia del director",
            solicitante=director, area=self.area, tipo="BIEN", cantidad=1,
            estado="VERIFICADO_PENDIENTE_AUTORIZACION",
        )
        ajena = SolicitudCompra.objects.create(
            codigo="CMP-DIR-AJENA", titulo="Compra elevada por otra persona",
            solicitante=self.usuarios["SOLICITANTE"], area=self.area,
            tipo="BIEN", cantidad=1,
            estado="VERIFICADO_PENDIENTE_AUTORIZACION",
        )
        self.autenticar("DIRECTOR")
        respuesta = self.client.get("/api/compras/solicitudes/?bandeja=direccion")
        ids = [item["id"] for item in respuesta.data]
        self.assertIn(ajena.id, ids)
        self.assertNotIn(propia.id, ids)

    def test_ciclo_completo_caja_chica(self):
        self.autenticar("SOLICITANTE")
        respuesta = self.client.post("/api/compras/solicitudes/", {
            "titulo": "Compra de prueba", "descripcion": "Prueba integral",
            "area": self.area.id, "tipo": "BIEN", "cantidad": 1,
            "especificaciones": "Especificaciones", "justificacion": "Necesario",
            "monto_estimado": "100.00", "informe": self.archivo("informe.pdf"),
            "poa": self.archivo("poa.pdf"), "pedido": self.archivo("pedido.pdf"),
            "proforma": self.archivo("proforma.pdf"),
        }, format="multipart")
        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        pk = respuesta.data["id"]
        self.assertEqual(respuesta.data["estado"], "CREADO_PENDIENTE_DAF")

        self.autenticar("DAF")
        r = self.client.post(f"/api/compras/solicitudes/{pk}/evaluar-daf/", {"califica": True}, format="json")
        self.assertEqual(r.data["estado"], "EVALUADO_PENDIENTE_CERTIFICACION")
        r = self.client.post(f"/api/compras/solicitudes/{pk}/certificar-daf/", {"certificacion_presupuestaria": self.archivo("certificacion.pdf")}, format="multipart")
        # La certificación de la DAF pasa directo al Director: Tesorería
        # solo desembolsa (no hay verificación previa en el BPMN).
        self.assertEqual(r.data["estado"], "VERIFICADO_PENDIENTE_AUTORIZACION")

        self.autenticar("DIRECTOR")
        r = self.client.post(f"/api/compras/solicitudes/{pk}/visto-bueno-director/", {}, format="json")
        self.assertEqual(r.data["estado"], "APROBADO_PARA_DESEMBOLSO")

        self.autenticar("TESORERIA")
        recibo = self.client.post(f"/api/compras/solicitudes/{pk}/recibos-tesoreria/", {
            "monto_desembolsado": "100.00", "responsable_adquisicion": "Responsable de Almacén", "tipo_desembolso": "Efectivo",
        }, format="json")
        self.assertEqual(recibo.status_code, 201, recibo.data)
        r = self.client.post(f"/api/compras/solicitudes/{pk}/desembolsar/", {
            "monto_desembolsado": "100.00",
            "responsable_adquisicion": "Responsable de Almacén",
            "tipo_desembolso": "Efectivo",
            "recibo_id": recibo.data['id'],
            "recibo_firmado": SimpleUploadedFile('firmado.pdf', b'%PDF-1.4\n', content_type='application/pdf'),
        }, format="multipart")
        self.assertEqual(r.data["estado"], "FONDOS_DESEMBOLSADOS")

        self.autenticar("ENCARGADO_COMPRAS_ALMACEN")
        r = self.client.post(f"/api/compras/solicitudes/{pk}/confirmar-recepcion-fondos/", {'firma': [[[10, 10], [50, 40], [90, 20]]]}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        r = self.client.post(f"/api/compras/solicitudes/{pk}/registrar-compra/", {
            "monto_real": "100.00",
            "proveedor": "Proveedor",
            "componente_verificado": True,
            "comprobante_compra": self.archivo("compra.pdf"),
        }, format="multipart")
        self.assertEqual(r.data["estado"], "COMPRA_REGISTRADA", r.data)
        r = self.client.post(f"/api/compras/solicitudes/{pk}/registrar-ingreso-almacen/", {
            "cantidad_recibida": 1,
            "responsable_recepcion": "Almacén",
        }, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        # Salida de almacén y entrega con acta son dos registros distintos.
        r = self.client.post(f"/api/compras/solicitudes/{pk}/registrar-despacho-almacen/", {
            "cantidad_entregada": 1,
            "entregado_a": "Sección solicitante",
        }, format="json")
        self.assertEqual(r.data["estado"], "COMPRA_REGISTRADA", r.data)

        acta_generada = self.client.post(f"/api/compras/solicitudes/{pk}/actas-almacen/", {"recibe": "Juan Perez", "entrega_confirmada": True}, format="json")
        self.assertEqual(acta_generada.status_code, 201, acta_generada.data)
        r = self.client.post(f"/api/compras/solicitudes/{pk}/entregar-con-acta/", {
            "acta_id": acta_generada.data["id"],
            "acta_conformidad": SimpleUploadedFile("acta-firmada.pdf", b"%PDF-1.4\nDocumento firmado", content_type="application/pdf"),
        }, format="multipart")
        self.assertEqual(r.data["estado"], "COMPRADO_Y_ENTREGADO", r.data)

        # El cierre ocurre en el carril del solicitante: firma el acta y
        # recibe formalmente el bien.
        self.autenticar("SOLICITANTE")
        r = self.client.post(f"/api/compras/solicitudes/{pk}/firmar-acta/", {'firma': [[[10, 10], [50, 40], [90, 20]]]}, format="json")
        self.assertEqual(r.data["estado"], "DESCARGO_PENDIENTE_LIQUIDACION", r.data)

        r = self.client.post(f"/api/compras/solicitudes/{pk}/recibir-solicitud/", {}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["estado"], "CERRADO_ARCHIVADO")
        self.assertTrue(r.data["cerrado_inmutable"])


class SeguridadFlujoComprasTests(APITestCase):
    """'Modo Teniente': intenta romper el flujo de Caja Chica
    saltando estados, actuando fuera de rol y alterando el
    monto estimado una vez que el expediente ya está en
    evaluación/aprobación."""

    def test_r02_creacion_directa_respeta_roles_y_no_guarda_rechazos(self):
        from pathlib import Path
        from django.conf import settings
        from compras.models import SolicitudCompra, CotizacionCompra
        usuario = self.usuarios['ADMIN']
        # ADMIN habilita el endpoint; el rol técnico debe seguir imponiendo R01/R02.
        for codigo in ('ESPECIALISTA', 'AUXILIAR_SERVICIOS_GENERALES'):
            asignacion = UsuarioRol.objects.create(usuario=usuario, rol=Rol.objects.get(codigo=codigo))
            for monto, numero, modo, esperado in (
                ('500', 0, '', 201), ('700', 0, '', 400), ('700', 3, '', 201),
                ('1001', 3, '', 400), ('700', 3, 'proveedor', 400),
                ('700', 3, 'archivo', 400), ('700', 3, 'formato', 400), ('700', 4, '', 400),
            ):
                with self.subTest(rol=codigo, monto=monto, modo=modo, numero=numero):
                    self.client.force_authenticate(usuario)
                    datos = {
                        'titulo': 'R02 directa', 'descripcion': 'Componentes de prueba',
                        'area': self.area.pk, 'tipo': 'COMPONENTE', 'cantidad': 2,
                        'especificaciones': 'Compatibles', 'justificacion': 'Reposición',
                        'monto_estimado': monto, 'informe': self.archivo('informe.pdf'), 'poa': self.archivo('poa.pdf'),
                    }
                    for i in range(1, numero + 1):
                        datos[f'proveedor_{i}'] = ' proveedor ' if modo == 'proveedor' else f'Proveedor {i}'
                        datos[f'precio_unitario_{i}'] = '350'
                        datos[f'cotizacion_{i}'] = SimpleUploadedFile(
                            f'cotizacion{i}.pdf', b'igual' if modo == 'archivo' else f'oferta {i}'.encode(),
                            content_type='text/plain' if modo == 'formato' else 'application/pdf',
                        )
                    compras, cotizaciones = SolicitudCompra.objects.count(), CotizacionCompra.objects.count()
                    archivos = set(Path(settings.SIA_PRIVATE_ROOT).rglob('*')) | set(Path(settings.MEDIA_ROOT).rglob('*'))
                    respuesta = self.client.post('/api/compras/solicitudes/', datos, format='multipart')
                    self.assertEqual(respuesta.status_code, esperado, respuesta.data)
                    if esperado == 400:
                        self.assertEqual(SolicitudCompra.objects.count(), compras)
                        self.assertEqual(CotizacionCompra.objects.count(), cotizaciones)
                        self.assertEqual(set(Path(settings.SIA_PRIVATE_ROOT).rglob('*')) | set(Path(settings.MEDIA_ROOT).rglob('*')), archivos)
                        if monto == '1001':
                            self.assertIn('el monto total supera', str(respuesta.data))
                    elif numero:
                        solicitud = SolicitudCompra.objects.get(pk=respuesta.data['id'])
                        self.assertEqual(solicitud.cotizaciones.count(), 3)
                        self.assertTrue(solicitud.proforma.storage.exists(solicitud.proforma.name))
            asignacion.delete()

    def setUp(self):
        call_command("cargar_permisos_sigta")

        self.area = Area.objects.create(codigo="TEST2", nombre="Área de prueba 2")
        self.usuarios = {}
        for codigo in ("ADMIN", "SOLICITANTE", "DAF", "TESORERIA", "DIRECTOR", "ENCARGADO_COMPRAS_ALMACEN"):
            rol = Rol.objects.get(codigo=codigo)
            usuario = Usuario.objects.create_user(
                username=f"{codigo.lower()}2", email=f"{codigo.lower()}2@emi.edu.bo",
                nombre_completo=codigo, password="Prueba#2026",
            )
            UsuarioRol.objects.create(usuario=usuario, rol=rol, activo=True)
            self.usuarios[codigo] = usuario

    def archivo(self, nombre="archivo.pdf"):
        return SimpleUploadedFile(nombre, b"contenido de prueba", content_type="application/pdf")

    def autenticar(self, rol):
        self.client.force_authenticate(self.usuarios[rol])

    def crear_solicitud(self):
        self.autenticar("SOLICITANTE")
        r = self.client.post("/api/compras/solicitudes/", {
            "titulo": "Compra de prueba", "descripcion": "Prueba de seguridad",
            "area": self.area.id, "tipo": "BIEN", "cantidad": 1,
            "especificaciones": "Especificaciones", "justificacion": "Necesario",
            "monto_estimado": "100.00", "informe": self.archivo("informe.pdf"),
            "poa": self.archivo("poa.pdf"), "pedido": self.archivo("pedido.pdf"),
            "proforma": self.archivo("proforma.pdf"),
        }, format="multipart")
        self.assertEqual(r.status_code, 201, r.data)
        return r.data["id"]

    def test_no_se_puede_saltar_directo_a_desembolsar(self):
        pk = self.crear_solicitud()
        self.autenticar("TESORERIA")
        r = self.client.post(f"/api/compras/solicitudes/{pk}/desembolsar/", {
            "monto_desembolsado": "100.00", "responsable_adquisicion": "Almacén",
        }, format="json")
        self.assertEqual(r.status_code, 409, r.data)

    def test_tesoreria_no_puede_desembolsar_sin_autorizacion_del_director(self):
        pk = self.crear_solicitud()
        self.autenticar("DAF")
        self.client.post(f"/api/compras/solicitudes/{pk}/evaluar-daf/", {"califica": True}, format="json")
        self.client.post(f"/api/compras/solicitudes/{pk}/certificar-daf/", {"certificacion_presupuestaria": self.archivo("cert.pdf")}, format="multipart")

        self.autenticar("TESORERIA")
        r = self.client.post(f"/api/compras/solicitudes/{pk}/desembolsar/", {
            "monto_desembolsado": "100.00", "responsable_adquisicion": "Almacén",
        }, format="json")
        self.assertEqual(r.status_code, 409, r.data)

        r = self.client.get(f"/api/compras/solicitudes/{pk}/")
        self.assertEqual(r.data["estado"], "VERIFICADO_PENDIENTE_AUTORIZACION")

    def test_tesoreria_no_puede_ejecutar_accion_de_daf(self):
        pk = self.crear_solicitud()
        self.autenticar("TESORERIA")
        r = self.client.post(f"/api/compras/solicitudes/{pk}/evaluar-daf/", {"califica": True}, format="json")
        self.assertEqual(r.status_code, 403, r.data)

    def test_encargado_almacen_no_puede_dar_visto_bueno_director(self):
        pk = self.crear_solicitud()
        self.autenticar("ENCARGADO_COMPRAS_ALMACEN")
        r = self.client.post(f"/api/compras/solicitudes/{pk}/visto-bueno-director/", {}, format="json")
        self.assertEqual(r.status_code, 403, r.data)

    def test_solicitante_no_puede_ver_ni_editar_solicitud_ajena(self):
        pk = self.crear_solicitud()

        otro_solicitante = Usuario.objects.create_user(
            username="intruso", email="intruso@emi.edu.bo",
            nombre_completo="Intruso", password="Prueba#2026",
        )
        UsuarioRol.objects.create(usuario=otro_solicitante, rol=Rol.objects.get(codigo="SOLICITANTE"), activo=True)
        self.client.force_authenticate(otro_solicitante)

        # No aparece en su bandeja (get_queryset filtra por dueño).
        r = self.client.get("/api/compras/solicitudes/")
        self.assertNotIn(pk, [item["id"] for item in r.data])

        # Tampoco puede modificarla directamente por id.
        r = self.client.patch(f"/api/compras/solicitudes/{pk}/", {"titulo": "Hackeado"}, format="json")
        self.assertIn(r.status_code, (403, 404))

    def test_nadie_puede_modificar_monto_estimado_en_evaluacion(self):
        pk = self.crear_solicitud()

        self.autenticar("DAF")
        r = self.client.post(f"/api/compras/solicitudes/{pk}/evaluar-daf/", {"califica": True}, format="json")
        self.assertEqual(r.status_code, 200, r.data)

        # Ni siquiera ADMIN puede reescribir el monto una vez
        # que el expediente entró al flujo de aprobación.
        self.autenticar("ADMIN")
        r = self.client.patch(f"/api/compras/solicitudes/{pk}/", {"monto_estimado": "999999.00"}, format="json")
        self.assertEqual(r.status_code, 403, r.data)

        r = self.client.get(f"/api/compras/solicitudes/{pk}/")
        self.assertEqual(r.data["monto_estimado"], "100.00")

    def test_expediente_cerrado_es_inmutable_incluso_para_admin(self):
        # Ciclo feliz completo hasta el cierre.
        pk = self.crear_solicitud()
        self.autenticar("DAF")
        self.client.post(f"/api/compras/solicitudes/{pk}/evaluar-daf/", {"califica": True}, format="json")
        self.client.post(f"/api/compras/solicitudes/{pk}/certificar-daf/", {"certificacion_presupuestaria": self.archivo("cert.pdf")}, format="multipart")
        self.autenticar("DIRECTOR")
        self.client.post(f"/api/compras/solicitudes/{pk}/visto-bueno-director/", {}, format="json")
        self.autenticar("TESORERIA")
        recibo = self.client.post(f"/api/compras/solicitudes/{pk}/recibos-tesoreria/", {
            "monto_desembolsado": "100.00", "responsable_adquisicion": "Responsable de Almacén", "tipo_desembolso": "Efectivo",
        }, format="json")
        self.assertEqual(recibo.status_code, 201, recibo.data)
        self.client.post(f"/api/compras/solicitudes/{pk}/desembolsar/", {
            "monto_desembolsado": "100.00",
            "responsable_adquisicion": "Responsable de Almacén",
            "tipo_desembolso": "Efectivo",
            "recibo_id": recibo.data['id'],
            "recibo_firmado": SimpleUploadedFile('firmado.pdf', b'%PDF-1.4\n', content_type='application/pdf'),
        }, format="multipart")
        self.autenticar("ENCARGADO_COMPRAS_ALMACEN")
        self.client.post(f"/api/compras/solicitudes/{pk}/confirmar-recepcion-fondos/", {'firma': [[[10, 10], [50, 40], [90, 20]]]}, format="json")
        self.client.post(f"/api/compras/solicitudes/{pk}/registrar-compra/", {
            "monto_real": "100.00",
            "proveedor": "Proveedor",
            "componente_verificado": True,
            "comprobante_compra": self.archivo("compra.pdf"),
        }, format="multipart")
        self.client.post(f"/api/compras/solicitudes/{pk}/registrar-ingreso-almacen/", {
            "cantidad_recibida": 1,
            "responsable_recepcion": "Almacén",
        }, format="json")
        self.client.post(f"/api/compras/solicitudes/{pk}/registrar-despacho-almacen/", {
            "cantidad_entregada": 1,
            "entregado_a": "Sección solicitante",
        }, format="json")
        acta_generada = self.client.post(f"/api/compras/solicitudes/{pk}/actas-almacen/", {"recibe": "Juan Perez", "entrega_confirmada": True}, format="json")
        self.assertEqual(acta_generada.status_code, 201, acta_generada.data)
        self.client.post(f"/api/compras/solicitudes/{pk}/entregar-con-acta/", {
            "acta_id": acta_generada.data["id"],
            "acta_conformidad": SimpleUploadedFile("acta-firmada.pdf", b"%PDF-1.4\nDocumento firmado", content_type="application/pdf"),
        }, format="multipart")

        # Solo la sección solicitante cierra el proceso.
        self.autenticar("TESORERIA")
        r = self.client.post(f"/api/compras/solicitudes/{pk}/firmar-acta/", {'firma': [[[10, 10], [50, 40], [90, 20]]]}, format="json")
        self.assertEqual(r.status_code, 403, r.data)

        self.autenticar("SOLICITANTE")
        self.client.post(f"/api/compras/solicitudes/{pk}/firmar-acta/", {'firma': [[[10, 10], [50, 40], [90, 20]]]}, format="json")
        r = self.client.post(f"/api/compras/solicitudes/{pk}/recibir-solicitud/", {}, format="json")
        self.assertEqual(r.status_code, 200, r.data)

        # Ya cerrado: ninguna transición vuelve a aplicarse,
        # ni con el rol correcto.
        self.autenticar("TESORERIA")
        r = self.client.post(f"/api/compras/solicitudes/{pk}/desembolsar/", {"monto_desembolsado": "1.00", "responsable_adquisicion": "X"}, format="json")
        self.assertEqual(r.status_code, 409, r.data)
