@echo off
rem Une los registros y recalcula adjudicatarios, picos, cierre, linea base y ordenes de cierre. Ejecutar con Power BI cerrado.
cd /d "%~dp0"
python scripts\03_unir_registros.py registros scripts\intermedios\codigos_codice.json . || goto error
move /Y resumen_registros.json scripts\intermedios\ >nul
move /Y catalogo_organos_defensa.csv scripts\intermedios\ >nul
python scripts\05_adjudicatarios_y_picos.py registros scripts\intermedios\codigos_codice.json sucesos_2017_2026.csv . || goto error
python scripts\06_cierre_competencia_calendario.py registros scripts\intermedios\codigos_codice.json . || goto error
echo Linea base del sector publico (tarda unos minutos)...
python scripts\07_linea_base_sector_publico.py registros scripts\intermedios\codigos_codice.json . >nul || goto error
echo Ordenes de cierre del ejercicio...
python scripts\08_ordenes_cierre.py registros scripts\intermedios\codigos_codice.json . >nul || goto error
echo.
echo Listo. Abre powerbi\gasto_fin_ejercicio_defensa.pbip y pulsa Actualizar.
pause
exit /b 0
:error
echo.
echo Ha fallado un paso: revisa el mensaje de arriba.
pause
exit /b 1
