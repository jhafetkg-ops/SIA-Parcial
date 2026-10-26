import { test } from 'node:test'
import assert from 'node:assert/strict'
import { coincideProceso, opcionSolicitudesActiva, prioridadTecnico } from './portal.js'

test('el menú marca una sola opción para solicitudes y verificaciones', () => {
  const solicitudes = { path: '/usuario/mis-solicitudes', query: {} }
  assert.equal(opcionSolicitudesActiva(solicitudes), true)
  assert.equal(opcionSolicitudesActiva(solicitudes, true), false)

  const verificaciones = {
    path: '/usuario/mis-solicitudes', query: { vista: 'verificaciones' },
  }
  assert.equal(opcionSolicitudesActiva(verificaciones), false)
  assert.equal(opcionSolicitudesActiva(verificaciones, true), true)
})

test('el filtro separa soporte y mantenimiento', () => {
  assert.equal(coincideProceso({ proceso: 'SOPORTE' }, 'SOPORTE'), true)
  assert.equal(coincideProceso({ origen_modulo: 'MANTENIMIENTO' }, 'SOPORTE'), false)
  assert.equal(coincideProceso({ jefatura: 'UTIC' }, 'SOPORTE'), true)
  assert.equal(coincideProceso({ proceso: 'SOPORTE' }, ''), true)
})

test('el técnico ve Red como Crítica y conserva la clasificación de UTIC y su SLA', () => {
  for (const prioridad of ['BAJA', 'MEDIA', 'ALTA', 'CRITICA']) {
    const ticket = Object.freeze({ categoria_codigo: 'RED', prioridad, sla_horas: 48 })
    assert.equal(prioridadTecnico(ticket), 'CRITICA')
    assert.equal(ticket.prioridad, prioridad)
    assert.equal(ticket.sla_horas, 48)
    for (const categoria_codigo of ['HARDWARE', 'SOFTWARE', 'SERVIDORES', 'OTRO']) {
      assert.equal(prioridadTecnico({ categoria_codigo, prioridad }), prioridad)
    }
  }
  assert.equal(prioridadTecnico(undefined), undefined)
})
