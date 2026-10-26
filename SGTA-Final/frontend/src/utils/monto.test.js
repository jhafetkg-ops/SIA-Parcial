import { test } from 'node:test'
import assert from 'node:assert/strict'
import { monto, errorCotizaciones } from './monto.js'

test('monto conserva el último valor válido al escribir o pegar caracteres inválidos', () => {
  let listener
  const el = { value: '', addEventListener: (name, callback, capture) => {
    assert.equal(name, 'input')
    assert.equal(capture, true)
    listener = callback
  } }
  monto.mounted(el)
  for (const [entrada, esperado] of [
    ['1250', '1250'], ['1250.5', '1250.5'], ['1250.50', '1250.50'],
    ['1250.501', '1250.50'], ['abc', '1250.50'], ['1e3', '1250.50'],
    ['-20', '1250.50'], ['$100', '1250.50'], ['100,25', '100.25'], ['', ''],
  ]) {
    el.value = entrada
    listener()
    assert.equal(el.value, esperado)
  }
  el.value = '50.00'
  monto.updated(el)
  el.value = 'letras'
  listener()
  assert.equal(el.value, '50.00')
})

test('R01 precede a R02 y el formulario usa el límite del servidor', () => {
  const form = { costo_estimado: '500', cotizaciones: [] }
  assert.equal(errorCotizaciones(form, '1000'), '')
  form.costo_estimado = '500.01'
  assert.match(errorCotizaciones(form, '1000'), /tres cotizaciones/)
  form.costo_estimado = '1001'
  assert.match(errorCotizaciones(form, '1000'), /monto total supera/)
  form.costo_estimado = '900'
  assert.match(errorCotizaciones(form, '800'), /monto total supera/)
  form.cotizaciones = [1, 2, 3].map(i => ({ proveedor: `Proveedor ${i}`, precio_unitario: '300', archivo: {} }))
  assert.equal(errorCotizaciones(form, '1000'), '')
  form.cotizaciones[1].proveedor = '  PROVEEDOR  1 '
  assert.match(errorCotizaciones(form, '1000'), /proveedores distintos/)
})
