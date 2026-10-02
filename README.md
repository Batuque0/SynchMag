# SynchMag

Sincronización espacio-temporal de datos de magnetometría terrestre: combina el tracklog GPS, el magnetómetro móvil y la estación base de una campaña de campo en un único dataset georreferenciado, listo para QGIS.

## Qué hace

1. **Detecta automáticamente** los archivos de entrada en una carpeta `input/`, por prefijo de nombre (`base_*`, `mobile_*`) y por extensión (`*.gpx`) — sin importar si el texto plano viene como `.txt`, `.dat` u otro formato.
2. **Recorta el tracklog GPS** a la ventana real de medición (con margen de seguridad), para descartar el trayecto de acceso o el olvido de apagar el GPS.
3. **Interpola linealmente** las coordenadas (Lat/Lon/Alt) del GPS a los timestamps exactos del magnetómetro móvil, usando `pandas.interpolate(method="time")`.
4. **Control de calidad automático (QC):** descarta lecturas con intensidad magnética exactamente en 0 nT (dropouts del instrumento), tanto del móvil como de la base, antes de cualquier interpolación o corrección.
5. **Corrección diurna:** interpola la lectura de la base a los tiempos del móvil y resta directamente, `M_diurna(t) = M(t) - M_base(t)`.
6. **Genera gráficos de control** (figura de 3 paneles apilados, eje de tiempo compartido): Base, Móvil, Móvil−Base.
7. **Exporta los resultados** a CSV y a GeoPackage (`EPSG:4326`), con el tiempo conservado en dos formatos (`Fecha_Hora_UTC` como datetime nativo, usable con el control temporal de QGIS, y `hhmmss.s` en el formato compacto original).
8. **Organiza la salida** en una carpeta `yymmdd` (fecha de campaña, detectada del propio GPX), junto con copias de los tres archivos originales.

## Estructura de carpetas

```
SynchMag/
├── SynchMag.py
├── input/
│   ├── 20260907.gpx          # tracklog GPS (nombre libre, extensión .gpx)
│   ├── base_40ratv07.txt     # magnetómetro BASE  (prefijo "base_", cualquier extensión de texto plano)
│   └── mobile_al120.dat      # magnetómetro MÓVIL (prefijo "mobile_", cualquier extensión de texto plano)
├── build_exe.bat             # compila SynchMag.exe con PyInstaller (correr en Windows)
└── LEEME.txt
```

Debe haber **exactamente un archivo de cada tipo** en `input/`; si falta o sobra alguno, el programa avisa y no continúa.

## Formato de los archivos de entrada

- **GPX**: tracklog estándar, con latitud, longitud y tiempo UTC por punto.
- **Móvil / Base**: texto plano sin encabezado, columnas separadas por espacios:
  ```
  hhmmss.s   M(nT)   q
  135856.0   22940.30   99
  ```
  (la columna `q` es opcional en la base).

## Salida generada

Dentro de la carpeta destino elegida, en una subcarpeta `yymmdd`:

| Archivo | Contenido |
|---|---|
| `datos_sincronizados_yymmdd.csv` | `ID, Fecha_Hora_UTC, hhmmss.s, Lat, Lon, Alt, M [nT], M_base [nT], M_diurna [nT], q` |
| `datos_sincronizados_yymmdd.gpkg` | Mismos datos como GeoDataFrame (`EPSG:4326`), para abrir directo en QGIS |
| `graficos_yymmdd.png` | Figura de control: Base / Móvil / Móvil−Base |
| copias de `*.gpx`, `base_*`, `mobile_*` | Archivos originales de la campaña, archivados junto a los resultados |

## Requisitos

Python 3 + Conda, con las siguientes dependencias (todas vía `conda-forge`):

```bash
conda install -c conda-forge pandas gpxpy geopandas matplotlib
```

## Uso

```bash
python SynchMag.py
```

1. Colocá los archivos de la campaña en `input/`.
2. Corré el script (o el `.exe` compilado — ver más abajo).
3. Elegí la carpeta de destino en la ventana que se abre.
4. Los resultados quedan organizados automáticamente en `<destino>/yymmdd/`.

### Generar el ejecutable (Windows)

```bat
conda activate TU_ENTORNO
build_exe.bat
```

Esto instala `PyInstaller` si hace falta y genera `dist\SynchMag.exe`, que podés usar sin depender de Python/Conda activado.

> El `.exe` no viene incluido en el repo: `PyInstaller` compila para el sistema operativo en el que se ejecuta, así que debe generarse en una máquina Windows.

## Notas de implementación

- La fecha de campaña se detecta automáticamente del primer punto del GPX (no hay que indicarla a mano).
- La detección de `base_*` / `mobile_*` es independiente de la extensión del archivo.
- Las correcciones NO extrapolan: si un timestamp del móvil cae fuera del rango temporal cubierto por el GPS o por la base, el programa lo avisa en pantalla en vez de inventar un valor.
