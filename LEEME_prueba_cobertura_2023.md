# Prueba de cobertura 2023 — ficheros y procedencia

Generado el 22/10/2026 a partir de datos abiertos oficiales. Nada interno.

## Ficheros

| Fichero | Qué contiene |
| --- | --- |
| `placsp_defensa_adjudicaciones_2023.csv` | Adjudicaciones de órganos que cuelgan del Ministerio de Defensa en la PLACSP, con fecha de adjudicación en 2023, agregadas por mes × rama × tipo de contrato × procedimiento × tramitación × sistema de contratación. 916 filas. Separador `;`, decimales con coma, UTF-8. Sin nombres de adjudicatarios ni de personas. |
| `igae_defensa_2023.csv` | Créditos, obligaciones reconocidas netas y pagos de la sección 14 (Defensa), capítulos 2 y 6, 2023 y 2022, y obligaciones 2023 por programa. En euros. |

## Origen

- **PLACSP**: `licitacionesPerfilesContratanteCompleto3_2023.zip` (sindicación 643, licitaciones sin contratos menores), descargado de contrataciondelestado.es el 22/10/2026. 1.668.002.789 bytes; 1.250 ficheros Atom; 614.269 entradas; 28.604 de Defensa (9.656 licitaciones distintas).
- **IGAE**: Estadísticas mensuales de ejecución del Presupuesto del Estado hasta el 31/12/2023 (`MENSUAL 12-23.pdf`), páginas 97, 125 y 144.
- **Códigos**: listas CODICE oficiales publicadas en contrataciondelestado.es/codice/cl/.

## Reglas aplicadas

- Defensa = el órgano tiene «Ministerio de Defensa» en su jerarquía de la plataforma. `rama` = el nivel inmediatamente inferior (Ejército de Tierra, Armada, Ejército del Aire, EMAD, Secretaría de Estado, Subsecretaría, ISDEFE, SAES).
- `en_seccion_14 = No` para ISDEFE y SAES (empresas públicas, fuera del presupuesto de la sección 14).
- Por licitación se toma la última versión publicada en 2023; se descartan las anuladas y las retiradas del feed.
- Se cuentan los resultados «Adjudicado», «Adjudicado provisionalmente/definitivamente» y «Formalizado» con fecha de adjudicación e importe.
- `es_establecimiento_marco = Sí`: adjudicación de un acuerdo marco o sistema dinámico. Su importe es un techo, no un gasto; se excluye de la cobertura.

## Límites conocidos

- Adjudicar no es gastar: los importes de contratos plurianuales cuentan entero el año de adjudicación.
- Las adjudicaciones de finales de diciembre de 2023 publicadas en 2024 no están en este fichero: diciembre está infrarrepresentado.
- Cuatro adjudicaciones fechadas en el año «0023» (errores de carga, 0,5 M€) y 1.577 M€ de adjudicaciones con fecha anterior a 2023 actualizadas durante 2023 quedan fuera.

## Verificación

Agregado transferido del navegador con suma de control FNV-1a 32 bits `12788fbd` (39.396 caracteres, 916 filas, 7.551.674.511,26 € con IVA), comprobada tras la copia.
