import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { setImmediate } from 'node:timers/promises'
import { parse, compileScript } from '@vue/compiler-sfc'
import * as Vue from 'vue'
import { usarGuardado } from '../utils/guardado.js'

test('R03: el formulario fuerza Alta, restaura la prioridad manual y conserva Mantenimiento', async () => {
  const fuente = readFileSync(new URL('./FormularioSolicitud.vue', import.meta.url), 'utf8')
  const { descriptor } = parse(fuente)
  const script = compileScript(descriptor, { id: 'r03-formulario' }).content
    .replace(/import\s+(\w+)\s+from\s+['"][^'"]+\.vue['"]/g, (_, nombre) => `const ${nombre} = null`)
    .replace(/import\s+\{([\s\S]*?)\}\s+from\s+['"]vue['"]/g, 'const {$1} = Vue')
    .replace(/import\s+\{([\s\S]*?)\}\s+from\s+['"](?:vue-router|\.\.\/utils\/guardado\.js)['"]/g, 'const {$1} = mocks')
    .replace('export default', 'return')
  const componente = new Function('Vue', 'mocks', script)(Vue, {
    usarGuardado, useRoute: () => ({ meta: {} }), useRouter: () => ({ push() {} }),
  })
  // Se monta el setup real sin DOM ni componentes hijos; se comprueban sus bindings.
  componente.render = () => null
  const renderer = Vue.createRenderer({
    createComment: texto => ({ texto }), insert() {}, remove() {},
    parentNode: () => null, nextSibling: () => null,
  })
  const anteriorFetch = globalThis.fetch
  const anteriorStorage = globalThis.localStorage
  globalThis.localStorage = { getItem: () => 'token-prueba' }
  globalThis.fetch = async url => ({
    ok: true, status: 200, json: async () => url.includes('/categorias/') ? [
      { id: 31, codigo: 'OTRO', nombre: 'Otro' },
      { id: 72, codigo: 'RED', nombre: 'Redes y conectividad' },
      { id: 95, codigo: 'R03_CATALOGO', nombre: ' Servidores ' },
    ] : [{ id: 12, codigo: 'UTIC', nombre: 'UTIC' }],
  })
  const aplicaciones = []
  try {
    const app = renderer.createApp(componente, { tipoSolicitud: 'UTIC' })
    aplicaciones.push(app)
    app.mount({})
    await setImmediate()
    const estado = app._instance.setupState
    assert.equal(estado.form.categoria, 31)
    estado.form.prioridad = 'BAJA'
    estado.form.categoria = 72
    assert.equal(estado.prioridadAutomatica, true)
    assert.equal(estado.form.prioridad, 'ALTA')
    estado.form.categoria = 95
    assert.equal(estado.prioridadAutomatica, true)
    assert.equal(estado.form.prioridad, 'ALTA')
    estado.form.categoria = 31
    assert.equal(estado.prioridadAutomatica, false)
    assert.equal(estado.form.prioridad, 'BAJA')
    estado.form.prioridad = 'MEDIA'
    estado.form.categoria = 95
    assert.equal(estado.form.prioridad, 'ALTA')
    estado.form.categoria = 31
    assert.equal(estado.form.prioridad, 'MEDIA')
    estado.form.categoria = 72
    estado.limpiarFormulario()
    assert.equal(estado.form.prioridad, 'ALTA')
    estado.form.categoria = 31
    assert.equal(estado.form.prioridad, '')

    // El bloqueo del selector usa precisamente la condición reactiva comprobada.
    const pendientes = [...descriptor.template.ast.children]
    let selectorPrioridad
    while (pendientes.length) {
      const nodo = pendientes.pop()
      if (nodo.tag === 'select' && nodo.props.some(p => p.name === 'model' && p.exp?.content === 'form.prioridad')) selectorPrioridad = nodo
      pendientes.push(...(nodo.children || []))
    }
    assert.ok(selectorPrioridad)
    assert.ok(selectorPrioridad.props.some(p => p.name === 'bind' && p.arg?.content === 'disabled' && p.exp?.content === 'prioridadAutomatica'))

    const mantenimiento = renderer.createApp(componente, { tipoSolicitud: 'MANTENIMIENTO' })
    aplicaciones.push(mantenimiento)
    mantenimiento.mount({})
    await setImmediate()
    const estadoMantenimiento = mantenimiento._instance.setupState
    estadoMantenimiento.categorias = [{ id: 72, codigo: 'RED', nombre: 'Redes' }]
    estadoMantenimiento.form.categoria = 72
    assert.equal(estadoMantenimiento.prioridadAutomatica, false)
    assert.equal(estadoMantenimiento.form.prioridad, '')
  } finally {
    aplicaciones.forEach(app => app.unmount())
    globalThis.fetch = anteriorFetch
    if (anteriorStorage === undefined) delete globalThis.localStorage
    else globalThis.localStorage = anteriorStorage
  }
})
