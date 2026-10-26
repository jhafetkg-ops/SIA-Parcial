import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { setImmediate } from 'node:timers/promises'
import { parse, compileScript } from '@vue/compiler-sfc'
import * as Vue from 'vue'

test('R07: cuenta activos del servidor y no anuncia éxito ante un rechazo de cupo', async () => {
  const { descriptor } = parse(readFileSync(new URL('./JefeUticDashboardView.vue', import.meta.url), 'utf8'))
  const script = compileScript(descriptor, { id: 'r07-utic' }).content
    .replace(/import\s+(\w+)\s+from\s+['"][^'"]+\.vue['"]/g, (_, nombre) => `const ${nombre} = null`)
    .replace(/import\s+\{([^}]*?)\}\s+from\s+['"]vue['"]/g, 'const {$1} = Vue')
    .replace(/import\s+\{([^}]*?)\}\s+from\s+['"](?:vue-router|\.\.\/utils\/firma)['"]/g, 'const {$1} = mocks')
    .replace('export default', 'return')
  const componente = new Function('Vue', 'mocks', script)(Vue, {
    useRouter: () => ({ push() {} }), solicitarFirma: async () => null,
  })
  componente.render = () => null
  const renderer = Vue.createRenderer({
    createComment: texto => ({ texto }), insert() {}, remove() {},
    parentNode: () => null, nextSibling: () => null,
  })
  const anteriores = { fetch: globalThis.fetch, localStorage: globalThis.localStorage }
  const registros = Array.from({ length: 5 }, (_, i) => ({ id: i + 1, tecnico_asignado: 8, cuenta_carga_activa: true, estado_codigo: 'ASIGNADO' }))
  registros.push({ id: 6, tecnico_asignado: 8, cuenta_carga_activa: false, estado_codigo: 'PENDIENTE_CONFORMIDAD' })
  registros.push({ id: 7, tecnico_asignado: 8, cuenta_carga_activa: false, estado_codigo: 'CERRADO' })
  const candidato = { id: 9, tecnico_asignado: null, cuenta_carga_activa: true, estado_codigo: 'EN_ANALISIS', clasificado_en: '2026-10-26T10:00:00Z' }
  registros.push(candidato)
  const mensaje = 'El técnico seleccionado ya tiene 5 tickets activos asignados. No es posible asignarle otro ticket hasta que libere un cupo.'
  let permitir = false
  globalThis.localStorage = { getItem: clave => clave === 'sigta_usuario' ? '{}' : 'token-prueba' }
  globalThis.fetch = async (url, opciones = {}) => {
    if (opciones.method === 'POST') {
      assert.match(url, /\/9\/designar-revision\/$/)
      if (!permitir) return { ok: false, status: 400, json: async () => ({ detalle: [mensaje] }) }
      candidato.tecnico_asignado = 8
      candidato.estado_codigo = 'ASIGNADO'
      return { ok: true, status: 200, json: async () => ({ ok: true }) }
    }
    return { ok: true, status: 200, json: async () => url.includes('usuarios-por-rol') ? [{ id: 8, nombre_completo: 'Especialista' }] : structuredClone(registros) }
  }
  const app = renderer.createApp(componente)
  try {
    app.mount({})
    await setImmediate()
    const estado = app._instance.setupState
    assert.equal(estado.cargaEspecialista(8), 5)
    estado.verTicket(estado.tickets.find(t => t.id === 9))
    estado.tecnicoId = 8
    estado.confirmar('asignar')
    await estado.ejecutar()
    assert.equal(estado.mensaje.tipo, 'error')
    assert.equal(estado.mensaje.texto, mensaje)
    assert.equal(estado.confirmacion, 'asignar')
    assert.equal(estado.ticket.tecnico_asignado, null)
    registros[0].cuenta_carga_activa = false
    registros[0].estado_codigo = 'CERRADO'
    permitir = true
    await estado.cargar()
    assert.equal(estado.cargaEspecialista(8), 4)
    await estado.ejecutar()
    assert.equal(estado.mensaje.tipo, 'ok')
    assert.equal(estado.confirmacion, null)
    assert.equal(estado.ticket.tecnico_asignado, 8)
    assert.equal(estado.cargaEspecialista(8), 5)
  } finally {
    app.unmount()
    for (const [clave, valor] of Object.entries(anteriores)) {
      if (valor === undefined) delete globalThis[clave]
      else globalThis[clave] = valor
    }
  }
})
