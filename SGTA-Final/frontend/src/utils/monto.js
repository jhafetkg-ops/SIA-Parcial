// La entrada monetaria admite dígitos y hasta dos decimales, sin exponentes.
const valores = new WeakMap()
export const monto = {
  mounted(el) {
    valores.set(el, el.value || '')
    el.addEventListener('input', () => {
      const valor = el.value.replace(',', '.')
      if (/^\d*(?:\.\d{0,2})?$/.test(valor)) valores.set(el, valor)
      el.value = valores.get(el)
    }, true)
  },
  updated(el) {
    if (/^\d*(?:\.\d{0,2})?$/.test(el.value)) valores.set(el, el.value)
  },
}

// El límite de R01 proviene del servidor; R02 usa el total del requerimiento.
export function errorCotizaciones(form, limite) {
  const monto = String(form.costo_estimado)
  if (!/^\d+(?:\.\d{1,2})?$/.test(monto)) return 'Indique un monto total válido.'
  const total = Math.round(Number(monto) * 100)
  if (limite != null && total > Math.round(Number(limite) * 100)) {
    const valor = new Intl.NumberFormat('es-BO', { maximumFractionDigits: 2 }).format(Number(limite))
    return `No se puede registrar la solicitud porque el monto total supera el límite permitido de Bs ${valor}.`
  }
  if (total <= 50000) return ''
  const cotizaciones = form.cotizaciones || []
  if (cotizaciones.length !== 3 || cotizaciones.some(c => !c.archivo || !c.proveedor.trim() || !/^\d+(?:\.\d{1,2})?$/.test(c.precio_unitario) || Number(c.precio_unitario) <= 0)) {
    return 'Las solicitudes mayores a Bs 500 requieren tres cotizaciones de proveedores diferentes.'
  }
  const proveedores = cotizaciones.map(c => c.proveedor.normalize('NFKC').trim().replace(/\s+/g, ' ').toLocaleLowerCase())
  if (new Set(proveedores).size !== 3) return 'Las tres cotizaciones deben corresponder a proveedores distintos.'
  return ''
}
