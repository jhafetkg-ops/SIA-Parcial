"""Regresiones de consulta con la configuración real, sin suplir ajustes ausentes."""
from rest_framework.authtoken.models import Token
from rest_framework.test import APITransactionTestCase

from . import tests as flujo
from .models import EstadoTicket, Ticket


class ConsultaTicketsTests(APITransactionTestCase):
    serialized_rollback = True
    setUp = flujo.FlujoSoporteCompraTests.setUp
    autenticar = flujo.FlujoSoporteCompraTests.autenticar
    # Reutilizar los datos del flujo sin heredar sus casos de prueba.
    def test_consulta_propias_relaciones_nulas_y_visibilidad(self):
        propio = Ticket.objects.create(
            codigo='SOP-CONSULTA-1', titulo='Sin asignación', descripcion='Prueba',
            solicitante=self.usuarios['SOLICITANTE'], area=self.area,
            categoria=self.categoria, estado=EstadoTicket.objects.get(codigo='NUEVO'),
            activo=False,
        )
        ajeno = Ticket.objects.create(
            codigo='SOP-CONSULTA-2', titulo='Ajeno', descripcion='Prueba',
            solicitante=self.usuarios['JEFE_UTIC'], area=self.area,
            categoria=self.categoria, estado=propio.estado,
        )
        usuario = self.usuarios['SOLICITANTE']
        token = Token.objects.create(user=usuario)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
        self.assertEqual(self.client.get('/api/soporte/tickets/?propias=1').status_code, 403)
        usuario.must_change_password = False
        usuario.save(update_fields=['must_change_password'])
        for _ in range(2):
            respuesta = self.client.get('/api/soporte/tickets/?propias=1')
            self.assertEqual(respuesta.status_code, 200)
            self.assertEqual([t['id'] for t in respuesta.data], [propio.pk])
            self.assertIsNone(respuesta.data[0]['tecnico_nombre'])
            self.assertIsNone(respuesta.data[0]['compra_vinculada'])
            self.assertFalse(respuesta.data[0]['activo'])
        self.assertEqual(self.client.get(f'/api/soporte/tickets/{ajeno.pk}/').status_code, 404)
        self.client.credentials()
        self.assertEqual(self.client.get('/api/soporte/tickets/?propias=1').status_code, 401)
        self.autenticar('JEFE_UTIC')
        self.assertEqual(len(self.client.get('/api/soporte/tickets/').data), 2)
        self.assertEqual([t['id'] for t in self.client.get('/api/soporte/tickets/?propias=1').data], [ajeno.pk])
        self.autenticar('ESPECIALISTA')
        self.assertEqual(self.client.get('/api/soporte/tickets/').data, [])
        propio.tecnico_asignado = self.usuarios['ESPECIALISTA']
        propio.save(update_fields=['tecnico_asignado'])
        propio.especialistas_apoyo.add(self.usuarios['ESPECIALISTA'])
        self.assertEqual([t['id'] for t in self.client.get('/api/soporte/tickets/').data], [propio.pk])

    def test_creacion_y_recuperacion(self):
        self.autenticar('SOLICITANTE')
        respuesta = self.client.post('/api/soporte/tickets/', {
            'titulo': 'Solicitud de prueba', 'descripcion': 'Equipo no enciende',
            'ubicacion': 'Oficina', 'equipo_afectado': 'Computadora',
            'area': self.area.pk, 'categoria': self.categoria.pk,
        }, format='json')
        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        respuesta = self.client.get('/api/soporte/tickets/?propias=1')
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(len(respuesta.data), 1)
