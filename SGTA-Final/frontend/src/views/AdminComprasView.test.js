import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { setImmediate } from 'node:timers/promises'
import { parse, compileScript } from '@vue/compiler-sfc'
import * as Vue from 'vue'
import { coincideProceso } from '../utils/portal.js'

test('R09: muestra el rechazo financiero sin éxito y refresca saldo tras aprobar', async () => {
  const { descriptor } = parse(readFileSync(new URL('./AdminComprasView.vue', import.meta.url), 'utf8'))
  const script = compileScript(descriptor, { id: 'r09-aprobacion' }).content
    .replace(/import\s+(\w+)\s+from\s+['"][^'"]+\.vue['"]/g, (_, nombre) => `const ${nombre} = null`)
    .replace(/import\s+\{([^}]*?)\}\s+from\s+['"]vue['"]/g, 'const {$1} = Vue')
    .replace(/import\s+\{([^}]*?)\}\s+from\s+['"](?:vue-router|\.\.\/utils\/portal)['"]/g, 'const {$1} = mocks')
    .replace('export default', 'return')
  const componente = new Function('Vue', 'mocks', script)(Vue, { coincideProceso, useRoute: () => ({ meta: {}, query: {} }), useRouter: () => ({ push() {} }) })
  componente.render = () => null
  const renderer = Vue.createRenderer({ createComment: t => ({ t }), insert() {}, remove() {}, parentNode: () => null, nextSibling: () => null })
  const anteriores = { fetch: globalThis.fetch, localStorage: globalThis.localStorage, window: globalThis.window }
  const compra = { id: 9, codigo: 'CMP-R09-UI', estado: 'VERIFICADO_PENDIENTE_AUTORIZACION', monto_estimado: '700.00' }
  let permitir = false
  let saldo = '600.00'
  const error = 'No se puede aprobar la compra porque el saldo disponible de Caja Chica es insuficiente.'
  globalThis.localStorage = { getItem: k => k === 'sigta_usuario' ? '{}' : 'token-prueba' }
  globalThis.window = { sigtaConfirm: async () => true }
  globalThis.fetch = async (url, opciones = {}) => {
    if (opciones.method === 'POST') {
      if (!permitir) return { ok: false, status: 400, json: async () => ({ detalle: error }) }
      compra.estado = 'APROBADO_PARA_DESEMBOLSO'
      saldo = '300.00'
      return { ok: true, status: 200, json: async () => structuredClone(compra) }
    }
    return { ok: true, status: 200, json: async () => url === '/api/caja-chica/saldo/' ? {
      mes: '2026-10', fondo_mensual: '5000.00', total_aprobado: '4400.00', saldo_disponible: saldo, saldo_verificable: true,
    } : [structuredClone(compra)] }
  }
  const app = renderer.createApp(componente)
  try {
    app.mount({})
    await setImmediate()
    const estado = app._instance.setupState
    estado.compraSeleccionada = structuredClone(compra)
    await estado.aprobarCompra()
    assert.equal(estado.errorAccion, error)
    assert.equal(estado.mostrarModalExito, false)
    assert.equal(estado.compraSeleccionada.estado, 'VERIFICADO_PENDIENTE_AUTORIZACION')
    assert.equal(estado.saldoCaja.saldo_disponible, '600.00')
    permitir = true
    await estado.aprobarCompra()
    assert.equal(estado.mostrarModalExito, true)
    assert.equal(estado.saldoCaja.saldo_disponible, '300.00')
  } finally {
    app.unmount()
    for (const [k, v] of Object.entries(anteriores)) {
      if (v === undefined) delete globalThis[k]
      else globalThis[k] = v
    }
  }
})
