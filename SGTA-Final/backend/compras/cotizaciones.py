from decimal import Decimal
from rest_framework import serializers
from .models import CotizacionCompra
from usuarios.archivos import firmar_urls
import hashlib
import unicodedata


def validar_cotizaciones_requerimiento(request, monto, descripcion, cantidad):
    """Valida el lote completo antes de escribir archivos o registros (R02)."""
    archivos = [key for key in request.FILES if key.startswith('cotizacion_') and key != 'cotizacion_archivo']
    respaldos = request.FILES.getlist('cotizacion_archivo') + request.FILES.getlist('proforma')
    respaldo = respaldos[0] if respaldos else None
    if monto <= Decimal('500'):
        if archivos or len(respaldos) > 1:
            raise serializers.ValidationError({'cotizaciones': 'Hasta Bs 500 se permite un respaldo opcional.'})
        if respaldo:
            serializer = CotizacionCompraSerializer()
            archivo = serializer.fields['documento'].run_validation(respaldo)
            serializer.validate_documento(archivo)
        return []
    mensaje = 'Las solicitudes mayores a Bs 500 requieren tres cotizaciones de proveedores diferentes.'
    if set(archivos) != {'cotizacion_1', 'cotizacion_2', 'cotizacion_3'} or respaldo:
        raise serializers.ValidationError({'cotizaciones': mensaje})
    proveedores, huellas, lote = set(), set(), []
    for indice in range(1, 4):
        clave = f'cotizacion_{indice}'
        if len(request.FILES.getlist(clave)) != 1:
            raise serializers.ValidationError({'cotizaciones': mensaje})
        proveedor = ' '.join(unicodedata.normalize('NFKC', str(request.data.get(f'proveedor_{indice}', ''))).split())
        if not proveedor:
            raise serializers.ValidationError({'cotizaciones': mensaje})
        normalizado = proveedor.casefold()
        if normalizado in proveedores:
            raise serializers.ValidationError({'cotizaciones': 'Las tres cotizaciones deben corresponder a proveedores distintos.'})
        proveedores.add(normalizado)
        serializer = CotizacionCompraSerializer(data={
            'proveedor': proveedor, 'descripcion': descripcion, 'cantidad': cantidad,
            'precio_unitario': request.data.get(f'precio_unitario_{indice}', ''),
            'documento': request.FILES[clave],
        }, context={'request': request})
        serializer.is_valid(raise_exception=True)
        archivo = serializer.validated_data['documento']
        digest = hashlib.sha256()
        for chunk in archivo.chunks():
            digest.update(chunk)
        archivo.seek(0)
        if digest.digest() in huellas:
            raise serializers.ValidationError({'cotizaciones': 'Adjunte tres archivos de cotización diferentes.'})
        huellas.add(digest.digest())
        lote.append(serializer)
    return lote


def guardar_cotizaciones_requerimiento(lote, request, **origen):
    """El llamador incluye el registro del requerimiento en su transacción."""
    guardadas = []
    try:
        for serializer in lote:
            guardadas.append(serializer.save(creada_por=request.user, **origen))
    except Exception:
        for cotizacion in guardadas:
            cotizacion.documento.delete(save=False)
        raise
    return guardadas


class CotizacionCompraSerializer(serializers.ModelSerializer):
    total = serializers.SerializerMethodField()
    documento_url = serializers.SerializerMethodField()
    class Meta:
        model = CotizacionCompra
        fields = ['id', 'proveedor', 'descripcion', 'cantidad', 'precio_unitario', 'total', 'documento', 'documento_url', 'seleccionada', 'creado_en']
        read_only_fields = ['id', 'seleccionada', 'creado_en']
        extra_kwargs = {'documento': {'write_only': True}}
    def get_documento_url(self, obj):
        return firmar_urls('/media/' + obj.documento.name, self.context.get('request'))
    def get_total(self, obj):
        return str(obj.precio_unitario * obj.cantidad)
    def validate_precio_unitario(self, valor):
        if not valor.is_finite() or valor <= Decimal('0'):
            raise serializers.ValidationError('Ingrese un precio positivo.')
        return valor
    def validate_cantidad(self, valor):
        if valor < 1:
            raise serializers.ValidationError('Ingrese una cantidad positiva.')
        return valor
    def validate_documento(self, archivo):
        if archivo.size > 10 * 1024 * 1024:
            raise serializers.ValidationError('El documento supera 10 MB.')
        if archivo.content_type not in {'application/pdf', 'image/jpeg', 'image/png', 'image/webp'}:
            raise serializers.ValidationError('Adjunte PDF, JPG, PNG o WEBP.')
        return archivo
