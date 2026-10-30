# Predicción del cierre de 2026

**Fijada el 29 de octubre de 2026, antes de noviembre, con datos a 23/10/2026. No se modifica:** en enero de 2027 se contrasta tal cual con lo que haya pasado. Las mismas cifras están en `prediccion_cierre_2026.csv`, que genera `scripts/09_prediccion_cierre_2026.py`. Las predicciones van escritas en el script y no se recalculan.

## Qué se predice y por qué

Cada predicción repite lo que ha pasado en la mayoría de los años de 2017 a 2025, con las mismas reglas del informe. El alcance es el importe ordinario: licitaciones de la sección 14 sin contratos menores, sin el establecimiento de acuerdos marco y sin programas especiales. La comparación es siempre con el resto de la Administración General del Estado (AGE).

| | Qué se mide | Predicción para 2026 | Años que lo cumplieron (2017-2025) | Mediana 2017-2025 |
| --- | --- | --- | --- | --- |
| P1 | Peso de noviembre-diciembre en el importe ordinario de Defensa | Entre el 22 % y el 33 % (valor central, 26 %) | 9 de 9 | 25,9 % |
| P2 | Ese peso: Defensa frente al resto de la AGE | Defensa, por encima | 8 de 9 | +4,6 puntos |
| P3 | Peso de noviembre-diciembre en número de adjudicaciones: Defensa frente al resto de la AGE | Sin diferencia clara (entre −3 y +3 puntos) | 6 de 9 | +0,7 puntos |
| P4 | Peso de noviembre-diciembre en el importe de **servicios**: Defensa frente al resto de la AGE | Defensa, por encima | 7 de 9 | +8,5 puntos |
| P5 | Oferta única en Defensa: noviembre-diciembre frente a enero-octubre | Sube en el cierre | 8 de 9 | +3,8 puntos |
| P6 | Ese salto de la oferta única: Defensa frente al resto de la AGE | Mayor en Defensa | 8 de 9 | +5,5 puntos |
| P7 | Negociado sin publicidad en Defensa: noviembre-diciembre frente a enero-octubre | Sube en el cierre | 8 de 9 | +2,0 puntos |
| P8 | Quincena con más adjudicaciones de Defensa | Del 16 al 30 de noviembre | 8 de 9 | — |
| P9 | Adjudicaciones de Defensa después del plazo para enviar el compromiso a fiscalización, entre las de antes (5 días hábiles a cada lado) | Caen (cociente menor que 1) | 9 de 9 | 0,72 |
| P10 | Ese cociente: Defensa frente al resto de la AGE | Defensa cae más | 9 de 9 | −0,34 |
| P11 | Programas especiales (expedientes de 100 M€ o más) adjudicados en noviembre-diciembre | Al menos uno, sin predecir el importe | 7 de 9 | 2 |

Si se cumple lo habitual, acertarán casi todas. Lo interesante será cuáles fallan.

## Qué hace distinto a 2026

- **Presupuesto prorrogado, otra vez.** Es el tercer año seguido, tras 2024 y 2025. Con presupuesto prorrogado, el peso del cierre ha ido del 22,2 % (2024) al 32,3 % (2025): la prórroga sola no lo decide.
- **Mucho más importe antes del cierre.** De enero a octubre de 2026, el importe ordinario de Defensa ya suma 2.531,6 M€, frente a los 2.886 M€ de todo 2025. Si el peso del cierre fuera del 26 %, noviembre-diciembre sumaría unos 890 M€. Con los extremos de P1, serían entre 714 y 1.247 M€. Es una cifra orientativa, no una predicción que se puntúe: octubre está incompleto y parte de lo adjudicado se publica tarde.
- **La orden de cierre de 2026 aún no se ha publicado.** Suele salir a mediados de noviembre. P9 y P10 se medirán con el plazo que fije, sea cual sea.
- **Accidente ferroviario de Urda (Toledo), 28 de octubre.** La UME se ha desplegado con unos 200 efectivos el primer día (suceso E08). Puede añadir gasto de emergencia en noviembre-diciembre, sobre todo negociado sin publicidad y tramitación urgente, lo que reforzaría P7. Por importe debería ser pequeño frente al cierre; el despliegue de referencia es el de la DANA de 2024, con miles de militares durante semanas (E05). Al contrastar la predicción en enero, se revisará si este suceso explica alguna desviación.
- **2025 fue excepcional en programas especiales:** 22 expedientes en noviembre-diciembre. P11 solo pide uno, sin cifra, porque el importe de estos programas no se puede predecir con los datos públicos.

## Cómo se comprueba

1. En enero de 2027, al hacer los pasos de «Enero de 2027» del README, `placsp_anios.csv` marcará 2026 como completo.
2. `python scripts/09_prediccion_cierre_2026.py .` rellena `valor_2026` y `resultado_2026` de cada predicción.
3. En junio de 2027 se repite, porque las adjudicaciones publicadas tarde pueden mover algún resultado. Si cambia, se cuentan los dos.

Una predicción fallida no es un error del informe: indica que 2026 se comportó distinto y que conviene mirar por qué.
