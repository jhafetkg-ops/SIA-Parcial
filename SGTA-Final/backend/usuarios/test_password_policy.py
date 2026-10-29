from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase
from rest_framework.exceptions import ValidationError as SerializerValidationError

from recuperacion.views import validar_password
from .serializers import UsuarioSerializer, generar_password_temporal


class PasswordPolicyTests(SimpleTestCase):
    def test_rechaza_23_y_acepta_24_o_mas(self):
        for longitud in (23, 24, 25):
            password = 'Q7!v' + 'x' * (longitud - 4)
            with self.subTest(longitud=longitud):
                if longitud < 24:
                    with self.assertRaises(ValidationError) as error:
                        validate_password(password)
                    self.assertIn('password_too_short', [e.code for e in error.exception.error_list])
                    with self.assertRaises(SerializerValidationError):
                        UsuarioSerializer().validate_password(password)
                    self.assertTrue(validar_password(password))
                else:
                    validate_password(password)
                    self.assertEqual(UsuarioSerializer().validate_password(password), password)
                    self.assertFalse(validar_password(password))

    def test_temporales_cumplen_la_politica(self):
        for aleatoria in (False, True):
            password = generar_password_temporal(aleatoria=aleatoria)
            self.assertGreaterEqual(len(password), 24)
            validate_password(password)
