import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync, mkdirSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { setImmediate } from 'node:timers/promises'
import { parse, compileScript } from '@vue/compiler-sfc'
import * as Vue from 'vue'
import { jsPDF } from 'jspdf'

test('R09: la certificación jsPDF incluye la consulta real del servidor sin descontar desde Vue', async () => {
  const { descriptor } = parse(readFileSync(new URL('./DafEmitirView.vue', import.meta.url), 'utf8'))
  const script = compileScript(descriptor, { id: 'r09-pdf' }).content
    .replace(/import\s+(\w+)\s+from\s+['"][^'"]+\.vue['"]/g, (_, nombre) => `const ${nombre} = null`)
    .replace(/import\s+\{([^}]*?)\}\s+from\s+['"]vue['"]/g, 'const {$1} = Vue')
    .replace(/import\s+\{([^}]*?)\}\s+from\s+['"](?:vue-router|jspdf)['"]/g, 'const {$1} = mocks')
    .replace('export default', 'return')
  const componente = new Function('Vue', 'mocks', script)(Vue, { jsPDF, useRouter: () => ({ push() {} }) })
  componente.render = () => null
  const renderer = Vue.createRenderer({ createComment: t => ({ t }), insert() {}, remove() {}, parentNode: () => null, nextSibling: () => null })
  const claves = ['fetch', 'localStorage', 'window', 'Image', 'document', 'alert']
  const anteriores = Object.fromEntries(claves.map(k => [k, globalThis[k]]))
  const compra = { id: 9, codigo: 'CMP-R09-PDF', estado: 'EVALUADO_PENDIENTE_CERTIFICACION', monto_estimado: '700.00', area_nombre: 'UTIC', descripcion: 'Repuestos para laboratorio' }
  const logo = readFileSync(new URL('../../public/img/emi.jpg', import.meta.url)).toString('base64')
  let pdf
  let saldoConsultado = false
  let emitida = false
  globalThis.localStorage = { getItem: k => k === 'sigta_usuario' ? '{}' : 'token-prueba' }
  globalThis.window = { dispatchEvent() {} }
  globalThis.alert = mensaje => { throw new Error(mensaje) }
  globalThis.Image = function () {
    this.width = 1; this.height = 1
    Object.defineProperty(this, 'src', { set: () => this.onload() })
  }
  globalThis.document = { createElement: () => ({ getContext: () => ({ drawImage() {} }), toDataURL: () => `data:image/jpeg;base64,${logo}` }) }
  globalThis.fetch = async (url, opciones = {}) => {
    if (url === '/api/caja-chica/saldo/') {
      saldoConsultado = true
      return { ok: true, json: async () => ({ mes: '2026-10', fondo_mensual: '5000.00', total_aprobado: '4200.00', saldo_disponible: '800.00', saldo_verificable: true, calculado_en: '2026-10-26T10:00:00-04:00' }) }
    }
    if (opciones.method === 'POST') {
      assert.equal(saldoConsultado, true)
      assert.match(url, /\/9\/certificar-daf\/$/)
      pdf = Buffer.from(await opciones.body.get('certificacion_presupuestaria').arrayBuffer())
      emitida = true
      return { ok: true, json: async () => ({}) }
    }
    return { ok: true, json: async () => emitida ? [] : [compra] }
  }
  const app = renderer.createApp(componente)
  try {
    app.mount({})
    await setImmediate()
    const estado = app._instance.setupState
    estado.abrir(compra)
    estado.formCert.partida = { codigo: '43120', descripcion: 'Equipos y repuestos' }
    await estado.emitirCertificacion()
    assert.ok(pdf?.subarray(0, 5).equals(Buffer.from('%PDF-')))
    const contenido = pdf.toString('latin1')
    for (const texto of ['5000.00', '4200.00', '800.00', 'no reserva', 'CAJA CHICA 2026-10']) assert.ok(contenido.includes(texto), texto)
    assert.equal(estado.mostrarModalExito, true)
    if (process.env.SIA_R09_PDF_DIR) {
      mkdirSync(process.env.SIA_R09_PDF_DIR, { recursive: true })
      writeFileSync(join(process.env.SIA_R09_PDF_DIR, 'certificacion-r09.pdf'), pdf)
    }
  } finally {
    app.unmount()
    for (const [k, v] of Object.entries(anteriores)) {
      if (v === undefined) delete globalThis[k]
      else globalThis[k] = v
    }
  }
})
