============================================================================
 SynchMag — Sincronización espacio-temporal de magnetometría terrestre
============================================================================

CONTENIDO DEL ZIP
------------------
  SynchMag.py       -> script principal
  input\            -> carpeta donde poner los archivos de cada campaña
  build_exe.bat      -> genera SynchMag.exe (ver abajo, PASO OBLIGATORIO)
  LEEME.txt          -> este archivo


IMPORTANTE: SOBRE EL EJECUTABLE (.exe)
----------------------------------------
Este script fue generado en un entorno Linux, y un .exe de Windows solo se
puede compilar corriendo PyInstaller EN Windows (no existe compilación
cruzada confiable Linux -> Windows para este tipo de programas). Por eso el
.exe no viene ya armado dentro del zip: te dejo "build_exe.bat" para que lo
generes vos mismo, una sola vez, en tu PC. Tarda 1-2 minutos.

Pasos:
  1. Descomprimí este .zip en una carpeta, por ejemplo:
       C:\Users\Geopex\Desktop\SynchMag\

  2. Abrí Anaconda Prompt (o tu terminal con Conda) y activá el entorno
     donde ya tenés instalados pandas, gpxpy y geopandas:
       conda activate TU_ENTORNO

  3. Andá a la carpeta del proyecto:
       cd C:\Users\Geopex\Desktop\SynchMag

  4. Corré:
       build_exe.bat

  5. Cuando termine, el ejecutable va a estar en:
       C:\Users\Geopex\Desktop\SynchMag\dist\SynchMag.exe

     Copialo a donde quieras usarlo habitualmente (junto con una carpeta
     "input" al lado). Desde ese momento podés usar SynchMag.exe con doble
     click, sin necesitar Python/Conda activado ni volver a compilar.


CÓMO SE USA (tanto SynchMag.py como SynchMag.exe)
---------------------------------------------------
1. En la carpeta "input" (al lado del .py o del .exe), colocá los 3
   archivos de la campaña:

     - Tracklog GPS:              *.gpx           (ej: 20260907.gpx)
     - Magnetómetro BASE:         base_*          (ej: base_40ratv07.txt)
     - Magnetómetro MÓVIL:        mobile_*        (ej: mobile_al120.dat)

   La extensión NO importa (puede ser .txt, .dat, o cualquier otra forma de
   texto plano) — la detección se basa únicamente en el prefijo "base_" /
   "mobile_". Si no tenés preferencia, usá .txt.

   Tiene que haber EXACTAMENTE un archivo de cada tipo. Si falta o sobra
   alguno, el programa te lo indica con un mensaje claro y no continúa.

2. Ejecutá SynchMag.exe (doble click) o "python SynchMag.py" desde la
   terminal.

3. Se abre una ventana para elegir la carpeta DESTINO donde guardar los
   resultados (puede ser cualquier carpeta que quieras, en cualquier disco).

4. El programa crea automáticamente, dentro de esa carpeta destino, una
   subcarpeta con el formato "yymmdd" (fecha de campaña, tomada del propio
   GPX), conteniendo:

     - Copia del .gpx original
     - Copia del base_* original
     - Copia del mobile_* original
     - datos_sincronizados_yymmdd.csv   (incluye M, M_base, M_diurna)
     - datos_sincronizados_yymmdd.gpkg   (para abrir directo en QGIS)
     - graficos_yymmdd.png               (figura de 3 paneles de control)

   Ejemplo, si elegís como destino "D:\Campañas" y la fecha es 7/9/2026:

     D:\Campañas\260907\
         20260907.gpx
         base_40ratv07.txt
         mobile_al120.dat
         datos_sincronizados_260907.csv
         datos_sincronizados_260907.gpkg
         graficos_260907.png


CORRECCIÓN QUE INCLUYE EL CSV/GEOPACKAGE
--------------------------------------------
  Fecha_Hora_UTC -> timestamp completo (fecha + hora, UTC), en formato
                    datetime nativo dentro del GeoPackage (usable con el
                    Panel de Control Temporal de QGIS)
  hhmmss.s       -> mismo dato de tiempo en el formato compacto original
                    del archivo del móvil (hora del día, sin fecha)
  M [nT]         -> lectura cruda del móvil
  M_base [nT]    -> lectura de la base interpolada al tiempo del móvil
  M_diurna [nT]  -> corrección diurna: M(t) - M_base(t)
                    (resta directa, sin sumar ningún nivel de referencia)

  Si algún timestamp del móvil queda fuera del rango temporal cubierto por
  la base (por ejemplo, si la base se apagó antes de terminar el móvil),
  esos puntos NO se extrapolan — el programa lo va a advertir en pantalla.


CONTROL DE CALIDAD AUTOMÁTICO (QC)
--------------------------------------------
Antes de interpolar y aplicar correcciones, el programa descarta
automáticamente cualquier lectura de M (móvil) o M_base (base) que sea
EXACTAMENTE 0 nT. Un campo total de 0 nT no es físicamente posible en la
superficie terrestre (ronda entre ~25.000 y ~65.000 nT según la latitud):
es un dropout del instrumento, no un dato real. Si no se filtrara, ese
cero generaría un pico falso en la interpolación de los puntos vecinos.

El programa informa en pantalla cuántas lecturas se descartaron de cada
archivo (por ejemplo: "[QC] móvil: se descartaron 7 de 3469 lecturas...").


GRÁFICOS DE CONTROL (graficos_yymmdd.png)
--------------------------------------------
Figura de 3 paneles apilados, con eje X de tiempo (UTC) compartido para
poder comparar visualmente los mismos momentos entre los tres:
  (1) Base        -> deriva diurna pura (detecta tormentas magnéticas o
                      saltos del instrumento)
  (2) Móvil       -> señal bruta tal como la adquirió el operador
  (3) Móvil-Base  -> perfil con la variación temporal del campo ya
                      mitigada (M_diurna)


DEPENDENCIAS
-----------------------------------------------
Todas se instalan vía conda-forge, dentro de tu entorno Conda activo:

    conda activate TU_ENTORNO
    conda install -c conda-forge matplotlib

(pandas, gpxpy y geopandas ya los tenías instalados de antes; matplotlib
puede que ya venga como dependencia de geopandas, pero no está de más
asegurarlo)

"build_exe.bat" ya la instala automáticamente antes de compilar el .exe.


NOTAS
-----
- El GPX puede tener datos "de más" al principio o al final (por ejemplo
  si alguien se olvidó de apagar el track log); el programa recorta
  automáticamente el GPS a la ventana real de medición del móvil, con un
  margen de 30 segundos de cada lado.
- La fecha de campaña se toma automáticamente del primer punto del GPX,
  no hace falta indicarla a mano.
- El archivo BASE se usa para la corrección diurna (no solo se copia como
  antes): se interpola su lectura a los tiempos exactos del móvil.
- La detección de BASE y MÓVIL se hace solo por el prefijo del nombre
  ("base_" / "mobile_"); la extensión puede ser .txt, .dat, o cualquier
  otro formato de texto plano.
- Revisá siempre la columna "q" (factor de calidad) antes de interpretar
  el mapa final: lecturas con q muy bajo suelen ser poco confiables y
  podrían valer la pena filtrarse también (avisame si querés que agregue
  un umbral de q como parte del QC automático).
