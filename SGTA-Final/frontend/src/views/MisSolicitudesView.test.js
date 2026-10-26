import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { setImmediate } from 'node:timers/promises'
import { parse, compileScript } from '@vue/compiler-sfc'
import * as Vue from 'vue'

test('R06: confirma, actualiza sin duplicar y respeta la autorización del servidor', async () => {
  const { descriptor } = parse(readFileSync(new URL('./MisSolicitudesView.vue', import.meta.url), 'utf8'))
  const script = compileScript(descriptor, { id: 'r06-solicitudes' }).content
    .replace(/import\s+(\w+)\s+from\s+['"][^'"]+\.vue['"]/g, (_, nombre) => `const ${nombre} = null`)
    .replace(/import\s+\{([\s\S]*?)\}\s+from\s+['"]vue['"]/g, 'const {$1} = Vue')
    .replace(/import\s+\{([\s\S]*?)\}\s+from\s+['"]vue-router['"]/g, 'const {$1} = mocks')
    .replace('export default', 'return')
  const componente = new Function('Vue', 'mocks', script)(Vue, {
    useRoute: () => ({ meta: {}, query: {} }), useRouter: () => ({ push() {} }),
  })
  componente.render = () => null
  const renderer = Vue.createRenderer({
    createComment: texto => ({ texto }), insert() {}, remove() {},
    parentNode: () => null, nextSibling: () => null,
  })
  const anteriores = { fetch: globalThis.fetch, localStorage: globalThis.localStorage, window: globalThis.window }
  const cerrado = {
    id: 16, codigo: 'SOP-R06', estado_codigo: 'CERRADO', estado_nombre: 'Cerrado',
    cerrado_en: '2026-10-24T10:00:00-04:00', titulo: 'Solicitud original',
    reapertura: { mostrar: true, permitida: true, dias: 3, motivo: '' },
  }
  let servidor = structuredClone(cerrado)
  let confirmar = false
  let rechazar = false
  let envios = 0
  globalThis.localStorage = { getItem: () => 'token-prueba' }
  globalThis.window = { confirm: () => confirmar }
  globalThis.fetch = async (url, opciones = {}) => {
    if (url.endsWith('/reabrir/')) {
      assert.equal(opciones.method, 'POST')
      envios++
      if (rechazar) {
        servidor.reapertura = { mostrar: true, permitida: false, dias: 3, motivo: 'Plazo vencido según el servidor.' }
        return { ok: false, status: 400, json: async () => ({ detalle: servidor.reapertura.motivo }) }
      }
      servidor = { ...servidor, estado_codigo: 'EN_EJECUCION', estado_nombre: 'En ejecución', reapertura: { mostrar: false, permitida: false } }
      return { ok: true, status: 200, json: async () => ({ ticket: structuredClone(servidor), mensaje: 'Ticket reabierto.' }) }
    }
    return { ok: true, status: 200, json: async () => url.includes('/tickets/') ? [structuredClone(servidor)] : [] }
  }
  const app = renderer.createApp(componente)
  try {
    app.mount({})
    await setImmediate()
    const estado = app._instance.setupState
    assert.equal(estado.solicitudes.length, 1)
    estado.verDetalle(estado.solicitudes[0])
    await estado.reabrirTicket()
    assert.equal(envios, 0) // Cancelar la confirmación no modifica el ticket.
    confirmar = true
    await estado.reabrirTicket()
    assert.equal(envios, 1)
    assert.equal(estado.solicitudes.length, 1)
    assert.equal(estado.solicitudSeleccionada.estado_codigo, 'EN_EJECUCION')
    assert.equal(estado.solicitudSeleccionada.cerrado_en, cerrado.cerrado_en)
    assert.equal(estado.solicitudSeleccionada.reapertura.permitida, false)

    servidor = structuredClone(cerrado)
    await estado.cargarTodo()
    estado.verDetalle(estado.solicitudes[0])
    rechazar = true // El plazo puede vencer después de haber cargado el detalle.
    await estado.reabrirTicket()
    assert.equal(envios, 2)
    assert.equal(estado.solicitudes.length, 1)
    assert.equal(estado.solicitudSeleccionada.estado_codigo, 'CERRADO')
    assert.equal(estado.mensajeReapertura, 'Plazo vencido según el servidor.')
    assert.equal(estado.solicitudSeleccionada.reapertura.permitida, false)
    await estado.reabrirTicket()
    assert.equal(envios, 2)

    // La plantilla exige permiso y visibilidad del servidor, no un plazo local fijo.
    const pendientes = [...descriptor.template.ast.children]
    let boton
    while (pendientes.length) {
      const nodo = pendientes.pop()
      if (nodo.tag === 'button' && nodo.props.some(p => p.name === 'on' && p.exp?.content === 'reabrirTicket')) boton = nodo
      pendientes.push(...(nodo.children || []))
    }
    assert.ok(boton)
    const condicion = boton.props.find(p => p.name === 'if').exp.content
    assert.match(condicion, /reapertura\?\.mostrar/)
    assert.match(condicion, /reapertura\.permitida/)
    assert.match(condicion, /SOPORTE/)
  } finally {
    app.unmount()
    for (const [clave, valor] of Object.entries(anteriores)) {
      if (valor === undefined) delete globalThis[clave]
      else globalThis[clave] = valor
    }
  }
})
