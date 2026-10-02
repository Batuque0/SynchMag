"""
============================================================================
 SynchMag — Sincronización espacio-temporal de datos de magnetometría
============================================================================

MODO DE USO
-----------
1. Colocar en la carpeta "input" (ubicada junto a SynchMag.py / SynchMag.exe)
   los tres archivos de la campaña:

     - Tracklog del navegador GPS:  *.gpx           (ej: 20260907.gpx)
     - Magnetómetro BASE:           base_*      (ej: base_40ratv07.txt, base_40ratv07.dat)
     - Magnetómetro MÓVIL:          mobile_*    (ej: mobile_al120.txt, mobile_al120.dat)

   La extensión NO importa (puede ser .txt, .dat, o cualquier otro texto
   plano); la detección se basa únicamente en el prefijo "base_" / "mobile_".
   Si no tenés preferencia, usá .txt.

   Debe haber EXACTAMENTE un archivo de cada tipo. Si sobra o falta alguno,
   el programa avisa con un mensaje claro y no continúa.

2. Ejecutar SynchMag.py (o SynchMag.exe).

3. Se abre un cuadro de diálogo para elegir la carpeta DESTINO donde
   guardar los resultados. Ahí se crea automáticamente una subcarpeta con
   el formato "yymmdd" (fecha de campaña, detectada del propio GPX) que
   contiene:

     - Copia del .gpx original
     - Copia del base_* original
     - Copia del mobile_* original
     - datos_sincronizados_yymmdd.csv   (incluye M, M_base, M_diurna)
     - datos_sincronizados_yymmdd.gpkg   (listo para abrir en QGIS)
     - graficos_yymmdd.png              (figura de 3 paneles: base, móvil, móvil-base)

CORRECCIONES APLICADAS
-----------------------
  M_diurna = M(t) - M_base(t)

  Se resta directamente la lectura de la base (interpolada al tiempo del
  móvil), sin sumar ningún nivel de referencia adicional.

Dependencias (todas vía conda-forge): pandas, gpxpy, geopandas, matplotlib
    conda install -c conda-forge matplotlib
"""

import sys
import shutil
from pathlib import Path
from datetime import date

import pandas as pd
import gpxpy
import geopandas as gpd
from shapely.geometry import Point

import matplotlib
matplotlib.use("Agg")  # sin pantalla: solo genera y guarda archivos de imagen
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox
except ImportError:
    tk = None


# ---------------------------------------------------------------------------
# CONFIGURACIÓN
# ---------------------------------------------------------------------------
def directorio_base() -> Path:
    """
    Devuelve la carpeta donde vive el script (o el .exe congelado con
    PyInstaller), para que "input/" se busque siempre al lado, sin
    importar desde dónde se lo ejecute.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


INPUT_DIR = directorio_base() / "input"
MARGEN_RECORTE_SEGUNDOS = 30.0  # margen de seguridad al recortar el GPX


# ---------------------------------------------------------------------------
# 1. DETECCIÓN AUTOMÁTICA DE ARCHIVOS EN "input/"
# ---------------------------------------------------------------------------
def _buscar_archivo_unico(carpeta: Path, condicion, descripcion: str) -> Path:
    """Busca EXACTAMENTE un archivo que cumpla 'condicion' dentro de 'carpeta'."""
    candidatos = sorted(f for f in carpeta.iterdir() if f.is_file() and condicion(f.name))

    if len(candidatos) == 0:
        raise FileNotFoundError(
            f"No se encontró ningún archivo de tipo '{descripcion}' en '{carpeta}'."
        )
    if len(candidatos) > 1:
        nombres = ", ".join(c.name for c in candidatos)
        raise FileExistsError(
            f"Se encontró más de un archivo de tipo '{descripcion}' en "
            f"'{carpeta}': {nombres}. Debe haber exactamente uno."
        )
    return candidatos[0]


def detectar_archivos_entrada(carpeta: Path) -> dict:
    """Detecta el GPX, el archivo BASE y el archivo MÓVIL dentro de 'input/'."""
    if not carpeta.exists():
        raise FileNotFoundError(
            f"No existe la carpeta de entrada '{carpeta}'.\n"
            "Creala junto a SynchMag y colocá ahí el .gpx, el base_* "
            "y el mobile_* de la campaña (cualquier extensión de texto plano)."
        )

    gpx_path = _buscar_archivo_unico(
        carpeta, lambda n: n.lower().endswith(".gpx"), "tracklog GPX (*.gpx)"
    )
    base_path = _buscar_archivo_unico(
        carpeta,
        lambda n: n.lower().startswith("base_"),
        "magnetómetro BASE (base_*, cualquier extensión de texto plano)",
    )
    mobile_path = _buscar_archivo_unico(
        carpeta,
        lambda n: n.lower().startswith("mobile_"),
        "magnetómetro MÓVIL (mobile_*, cualquier extensión de texto plano)",
    )

    print(f"  GPX detectado:   {gpx_path.name}")
    print(f"  Base detectada:  {base_path.name}")
    print(f"  Móvil detectado: {mobile_path.name}")

    return {"gpx": gpx_path, "base": base_path, "mobile": mobile_path}


# ---------------------------------------------------------------------------
# 2. LECTURA DEL GPX (NAVEGADOR)
# ---------------------------------------------------------------------------
def leer_gpx(gpx_path: Path) -> pd.DataFrame:
    """Parsea un tracklog GPX y devuelve un DataFrame con 'time' (UTC), Lat, Lon, Alt."""
    with open(gpx_path, "r", encoding="utf-8") as f:
        gpx = gpxpy.parse(f)

    registros = []
    for track in gpx.tracks:
        for segment in track.segments:
            for point in segment.points:
                registros.append(
                    {
                        "time": point.time,
                        "Lat": point.latitude,
                        "Lon": point.longitude,
                        # Elevación en metros sobre el elipsoide/geoide (según el
                        # GPS). Si el punto no trae elevación, queda como NaN y
                        # se interpola igual que Lat/Lon.
                        "Alt": point.elevation,
                    }
                )

    if not registros:
        raise ValueError(f"El GPX '{gpx_path.name}' no contiene puntos de tracklog.")

    df = pd.DataFrame(registros)
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.drop_duplicates(subset="time").sort_values("time").reset_index(drop=True)

    if df["Alt"].isna().all():
        print(
            "  [AVISO] El GPX no trae datos de elevación (Alt). Se usará 0 m "
            "como valor por defecto en la columna Alt de salida."
        )
        df["Alt"] = 0.0
    elif df["Alt"].isna().any():
        df["Alt"] = df["Alt"].interpolate().ffill().bfill()

    return df


# ---------------------------------------------------------------------------
# 3. LECTURA DEL ARCHIVO DEL MAGNETÓMETRO MÓVIL
# ---------------------------------------------------------------------------
def leer_csv_movil(dat_path: Path, fecha_referencia: date) -> pd.DataFrame:
    """
    Lee el archivo mobile_* (cualquier extensión de texto plano): sin
    encabezado, columnas
    separadas por uno o más espacios, en el orden hhmmss.s / M(nT) / q.
    Ejemplo de línea real:  135856.0  22940.30 99
    """
    df = pd.read_csv(
        dat_path,
        sep=r"\s+",
        header=None,
        names=["hhmmss.s", "M", "q"],
        engine="python",
    )

    def hhmmss_a_datetime(valor: float) -> pd.Timestamp:
        valor_str = f"{valor:012.6f}"
        hh = int(valor_str[0:2])
        mm = int(valor_str[2:4])
        ss_float = float(valor_str[4:])
        ss = int(ss_float)
        microsegundos = int(round((ss_float - ss) * 1e6))
        return pd.Timestamp(
            year=fecha_referencia.year, month=fecha_referencia.month, day=fecha_referencia.day,
            hour=hh, minute=mm, second=ss, microsecond=microsegundos, tz="UTC",
        )

    df["time"] = df["hhmmss.s"].apply(hhmmss_a_datetime)
    df = df.drop_duplicates(subset="time").sort_values("time").reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# 3.b LECTURA DEL ARCHIVO DEL MAGNETÓMETRO BASE
# ---------------------------------------------------------------------------
def leer_base(dat_path: Path, fecha_referencia: date) -> pd.DataFrame:
    """
    Lee el archivo base_* (cualquier extensión de texto plano). Acepta dos
    o tres columnas separadas por espacios:
        hhmmss.s   M_base            (2 columnas), o
        hhmmss.s   M_base   q        (3 columnas, se ignora q)
    Devuelve un DataFrame con 'time' (UTC) y 'M_base' (nT).
    """
    df_crudo = pd.read_csv(dat_path, sep=r"\s+", header=None, engine="python")

    if df_crudo.shape[1] == 2:
        df_crudo.columns = ["hhmmss.s", "M_base"]
    elif df_crudo.shape[1] >= 3:
        df_crudo = df_crudo.iloc[:, :3]
        df_crudo.columns = ["hhmmss.s", "M_base", "q_base"]
    else:
        raise ValueError(
            f"El archivo base '{dat_path.name}' no tiene el formato esperado "
            "(se esperan al menos 2 columnas: hhmmss.s y M_base)."
        )

    def hhmmss_a_datetime(valor: float) -> pd.Timestamp:
        valor_str = f"{valor:012.6f}"
        hh = int(valor_str[0:2])
        mm = int(valor_str[2:4])
        ss_float = float(valor_str[4:])
        ss = int(ss_float)
        microsegundos = int(round((ss_float - ss) * 1e6))
        return pd.Timestamp(
            year=fecha_referencia.year, month=fecha_referencia.month, day=fecha_referencia.day,
            hour=hh, minute=mm, second=ss, microsecond=microsegundos, tz="UTC",
        )

    df_crudo["time"] = df_crudo["hhmmss.s"].apply(hhmmss_a_datetime)
    df_crudo = df_crudo.drop_duplicates(subset="time").sort_values("time").reset_index(drop=True)
    return df_crudo[["time", "M_base"]]


# ---------------------------------------------------------------------------
# 3.c CONTROL DE CALIDAD AUTOMÁTICO (QC): DESCARTAR LECTURAS EN CERO
# ---------------------------------------------------------------------------
def filtrar_lecturas_en_cero(df: pd.DataFrame, columna_valor: str, nombre_fuente: str) -> pd.DataFrame:
    """
    Descarta filas donde la lectura magnética es exactamente 0, ya que un
    campo total de 0 nT no es un valor físicamente válido en superficie
    terrestre (el campo geomagnético ronda entre ~25.000 y ~65.000 nT según
    la latitud) — es un dropout del instrumento, no una medición real.

    Se aplica ANTES de interpolar/corregir para que ese cero no contamine
    la interpolación temporal de los puntos vecinos (una lectura en 0
    seguida de una interpolación lineal genera un "pico" falso hacia abajo
    justo alrededor del dropout, como se ve en el gráfico de control).
    """
    n_antes = len(df)
    mascara_cero = df[columna_valor] == 0
    n_ceros = int(mascara_cero.sum())

    if n_ceros > 0:
        porcentaje = 100 * n_ceros / n_antes
        print(
            f"  [QC] {nombre_fuente}: se descartaron {n_ceros} de {n_antes} "
            f"lecturas con {columna_valor} = 0 nT ({porcentaje:.2f}%), "
            "consideradas dropouts del instrumento."
        )

    return df.loc[~mascara_cero].reset_index(drop=True)


# ---------------------------------------------------------------------------
# 4. RECORTE DEL TRACKLOG GPS AL PERÍODO REAL DE MEDICIÓN
# ---------------------------------------------------------------------------
def recortar_gps_a_periodo_medicion(
    df_gps: pd.DataFrame, df_mov: pd.DataFrame, margen_segundos: float = 30.0
) -> pd.DataFrame:
    """
    Recorta el GPS al tramo real de medición (más un margen), para
    descartar el trayecto de acceso/salida cuando el GPS quedó grabando
    antes de empezar o después de terminar. No depende de una cadencia fija.
    """
    t_inicio = df_mov["time"].min() - pd.Timedelta(seconds=margen_segundos)
    t_fin = df_mov["time"].max() + pd.Timedelta(seconds=margen_segundos)

    df_gps_recortado = df_gps[(df_gps["time"] >= t_inicio) & (df_gps["time"] <= t_fin)].reset_index(drop=True)

    if df_gps_recortado.empty:
        raise ValueError(
            "El recorte del GPS al período de medición quedó vacío. "
            "Verificá que el GPX corresponda a la misma campaña que el "
            "archivo del móvil."
        )

    print(
        f"  GPS recortado: {len(df_gps)} -> {len(df_gps_recortado)} puntos "
        f"(período: {t_inicio} a {t_fin})"
    )
    return df_gps_recortado


# ---------------------------------------------------------------------------
# 5. INTERPOLACIÓN TEMPORAL LINEAL (GPS -> TIEMPOS DEL MAGNETÓMETRO)
# ---------------------------------------------------------------------------
def interpolar_coordenadas(df_gps: pd.DataFrame, df_mov: pd.DataFrame) -> pd.DataFrame:
    """Interpola linealmente Lat/Lon/Alt del GPS a los timestamps del móvil."""
    gps = df_gps.set_index("time")[["Lat", "Lon", "Alt"]]
    tiempos_mov = pd.DatetimeIndex(df_mov["time"])  # conserva tz-awareness (UTC)

    fuera_de_rango = tiempos_mov[(tiempos_mov < gps.index.min()) | (tiempos_mov > gps.index.max())]
    if len(fuera_de_rango) > 0:
        print(
            f"  [AVISO] {len(fuera_de_rango)} timestamps del móvil quedan "
            "fuera del rango temporal del GPX y no podrán interpolarse."
        )

    indice_union = gps.index.union(tiempos_mov).sort_values()
    gps_reindexado = gps.reindex(indice_union)
    gps_interpolado = gps_reindexado.interpolate(method="time", limit_area="inside")

    coords_sync = gps_interpolado.loc[tiempos_mov].reset_index().rename(columns={"index": "time"})
    return coords_sync


# ---------------------------------------------------------------------------
# 6. CORRECCIÓN DIURNA (MÓVIL − BASE)
# ---------------------------------------------------------------------------
def aplicar_correcciones(
    df_mov: pd.DataFrame, df_base: pd.DataFrame, coords_sync: pd.DataFrame
) -> pd.DataFrame:
    """
    Integra coordenadas y aplica la corrección diurna: resta la lectura de
    la base (interpolada al tiempo del móvil) a la lectura del móvil, sin
    sumar ningún nivel de referencia adicional.

        M_diurna = M(t) - M_base(t)

    Notas de diseño:

    * La interpolación de la base al tiempo del móvil usa limit_area="inside"
      para NO extrapolar el campo de la base fuera de su rango de registro
      real (evita corregir con valores inventados si la base se apagó antes
      o se prendió después que el móvil).
    """
    # 1. Integrar coordenadas (Lat, Lon, Alt) ya interpoladas a los tiempos del móvil
    df = df_mov.copy().reset_index(drop=True)
    df["Lat"] = coords_sync["Lat"].values
    df["Lon"] = coords_sync["Lon"].values
    df["Alt"] = coords_sync["Alt"].values

    # 2. Asegurar tz-aware UTC en ambas series de tiempo (por si vinieran naive)
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df_base = df_base.copy()
    df_base["time"] = pd.to_datetime(df_base["time"], utc=True)
    df_base = df_base.drop_duplicates(subset="time").sort_values("time").reset_index(drop=True)

    # 3. Corrección diurna: interpolar la base a los tiempos del móvil y restar
    base_indexed = df_base.set_index("time")[["M_base"]]
    tiempos_mov = pd.DatetimeIndex(df["time"])

    fuera_de_rango = tiempos_mov[
        (tiempos_mov < base_indexed.index.min()) | (tiempos_mov > base_indexed.index.max())
    ]
    if len(fuera_de_rango) > 0:
        print(
            f"  [AVISO] {len(fuera_de_rango)} timestamps del móvil quedan "
            "fuera del rango temporal de la BASE; su corrección diurna "
            "quedará como NaN (no se extrapola)."
        )

    indice_union = base_indexed.index.union(tiempos_mov).sort_values()
    base_reindexada = base_indexed.reindex(indice_union)
    base_interpolada = base_reindexada.interpolate(method="time", limit_area="inside")

    m_base_en_movil = base_interpolada.loc[tiempos_mov, "M_base"].values

    df_corr = df.copy()
    df_corr["M_base"] = m_base_en_movil
    df_corr["M_diurna"] = df_corr["M"] - df_corr["M_base"]

    # 4. Formato final
    #    Se conserva el tiempo completo de dos formas, para que sea fácil
    #    usar la que más te convenga:
    #      - "Fecha_Hora_UTC": timestamp legible completo (fecha + hora),
    #        ideal para ordenar/filtrar en QGIS o Excel, o para usar el
    #        control temporal de QGIS si la campaña abarca más de un día.
    #      - "hhmmss.s": el mismo formato compacto del archivo crudo del
    #        móvil (hora del día, sin fecha), para quien ya está
    #        acostumbrado a ese formato.
    #    Se quita el tz-info (ya en UTC) porque GeoPackage/QGIS interpretan
    #    mejor un datetime "naive" que uno con offset explícito.
    df_corr["Fecha_Hora_UTC"] = df_corr["time"].dt.tz_convert(None)
    df_corr["ID"] = range(1, len(df_corr) + 1)

    columnas_finales = [
        "time", "ID", "Fecha_Hora_UTC", "hhmmss.s", "Lat", "Lon", "Alt",
        "M", "M_base", "M_diurna", "q",
    ]

    # OJO: se conserva la columna 'time' (tz-aware, para los gráficos) además
    # de 'Fecha_Hora_UTC' (tz-naive, para exportar). 'time' se descarta en
    # main() justo antes de llamar a exportar_resultados.
    return df_corr[columnas_finales].rename(
        columns={
            "M": "M [nT]",
            "M_base": "M_base [nT]",
            "M_diurna": "M_diurna [nT]",
        }
    )


# ---------------------------------------------------------------------------
# 7. GRÁFICOS DE CONTROL DE CALIDAD (figura de 3 paneles)
# ---------------------------------------------------------------------------
def generar_graficos(
    df_base: pd.DataFrame, df_mov: pd.DataFrame, df_final: pd.DataFrame, out_png: Path
) -> None:
    """
    Genera una figura de 3 paneles apilados (eje X de tiempo compartido,
    para poder comparar visualmente los mismos momentos entre los tres):

      (1) Base:          M_base vs tiempo -> deriva diurna pura, sirve
                          para detectar tormentas magnéticas o saltos
                          instrumentales de la base.
      (2) Móvil (crudo): M vs tiempo -> señal bruta adquirida.
      (3) Móvil - Base:  M_diurna vs tiempo -> perfil con la variación
                          temporal del campo ya mitigada (sin sumar ningún
                          nivel de referencia adicional).

    Se guarda como PNG; no requiere pantalla (backend "Agg").
    """
    fig, (ax_base, ax_mov, ax_diurna) = plt.subplots(
        3, 1, figsize=(12, 10), sharex=True
    )

    ax_base.plot(df_base["time"], df_base["M_base"], color="tab:blue", linewidth=0.8)
    ax_base.set_title("Base")
    ax_base.set_ylabel("M_base [nT]")

    ax_mov.plot(df_mov["time"], df_mov["M"], color="tab:orange", linewidth=0.6)
    ax_mov.set_title("Móvil")
    ax_mov.set_ylabel("M [nT]")

    ax_diurna.plot(df_final["time"], df_final["M_diurna [nT]"], color="tab:green", linewidth=0.6)
    ax_diurna.set_title("Móvil − Base")
    ax_diurna.set_ylabel("M_diurna [nT]")
    ax_diurna.set_xlabel("Tiempo (UTC)")

    formato_hora = mdates.DateFormatter("%H:%M")
    for ax in (ax_base, ax_mov, ax_diurna):
        ax.xaxis.set_major_formatter(formato_hora)
        ax.grid(True, alpha=0.3)
        ax.tick_params(axis="x", rotation=30)

    fecha_campana = df_final["time"].iloc[0].date()
    fig.suptitle(f"SynchMag — Control de calidad del procesamiento ({fecha_campana})", fontsize=13)
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(out_png, dpi=150)
    plt.close(fig)

    print(f"  Gráficos exportados:  {out_png}")


# ---------------------------------------------------------------------------
# 8. EXPORTACIÓN (CSV + GEOPACKAGE)
# ---------------------------------------------------------------------------
def exportar_resultados(df_final: pd.DataFrame, out_csv: Path, out_gpkg: Path) -> None:
    df_final.to_csv(out_csv, index=False, encoding="utf-8")
    print(f"  CSV exportado:        {out_csv}")

    geometria = [Point(xy) for xy in zip(df_final["Lon"], df_final["Lat"])]
    gdf = gpd.GeoDataFrame(df_final, geometry=geometria, crs="EPSG:4326")
    gdf.to_file(out_gpkg, driver="GPKG")
    print(f"  GeoPackage exportado: {out_gpkg}")


# ---------------------------------------------------------------------------
# 9. SELECCIÓN DE CARPETA DE DESTINO (DIÁLOGO GRÁFICO)
# ---------------------------------------------------------------------------
def elegir_carpeta_destino() -> Path:
    """Abre un cuadro de diálogo nativo de Windows para elegir la carpeta destino."""
    if tk is None:
        raise RuntimeError(
            "No se pudo cargar tkinter (incluido normalmente con Python en "
            "Windows). No es posible abrir el selector de carpeta."
        )
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    carpeta = filedialog.askdirectory(
        title="SynchMag — Elegí la carpeta donde guardar los resultados"
    )
    root.destroy()

    if not carpeta:
        raise SystemExit("No se seleccionó ninguna carpeta de destino. Proceso cancelado.")
    return Path(carpeta)


def _mostrar_mensaje(titulo: str, texto: str, es_error: bool = False) -> None:
    """Muestra un mensaje emergente si tkinter está disponible (no interrumpe si falla)."""
    if tk is None:
        return
    try:
        root = tk.Tk()
        root.withdraw()
        if es_error:
            messagebox.showerror(titulo, texto)
        else:
            messagebox.showinfo(titulo, texto)
        root.destroy()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# FLUJO PRINCIPAL
# ---------------------------------------------------------------------------
def main():
    print("=" * 72)
    print(" SynchMag — Sincronización espacio-temporal de magnetometría")
    print("=" * 72)

    print("\n[1/9] Detectando archivos en 'input/'...")
    archivos = detectar_archivos_entrada(INPUT_DIR)

    print("\n[2/9] Leyendo tracklog GPX...")
    df_gps = leer_gpx(archivos["gpx"])
    fecha_campana = df_gps["time"].iloc[0].date()
    print(f"  Fecha de campaña detectada: {fecha_campana}")

    print("\n[3/9] Leyendo archivos del magnetómetro móvil y de la base...")
    df_mov = leer_csv_movil(archivos["mobile"], fecha_referencia=fecha_campana)
    df_base = leer_base(archivos["base"], fecha_referencia=fecha_campana)

    print("\n[4/9] Control de calidad: descartando lecturas en cero...")
    df_mov = filtrar_lecturas_en_cero(df_mov, "M", "móvil")
    df_base = filtrar_lecturas_en_cero(df_base, "M_base", "base")

    print("\n[5/9] Recortando GPS al período real de medición...")
    df_gps = recortar_gps_a_periodo_medicion(df_gps, df_mov, MARGEN_RECORTE_SEGUNDOS)

    print("\n[6/9] Interpolando coordenadas...")
    coords_sync = interpolar_coordenadas(df_gps, df_mov)

    print("\n[7/9] Aplicando corrección diurna (Móvil − Base)...")
    df_final = aplicar_correcciones(df_mov, df_base, coords_sync)

    print("\n[8/9] Seleccioná la carpeta de destino en la ventana que se abrió...")
    carpeta_base_destino = elegir_carpeta_destino()

    etiqueta_fecha = fecha_campana.strftime("%y%m%d")  # formato yymmdd
    carpeta_salida = carpeta_base_destino / etiqueta_fecha
    carpeta_salida.mkdir(parents=True, exist_ok=True)

    print(f"\nCopiando archivos originales a: {carpeta_salida}")
    shutil.copy2(archivos["gpx"], carpeta_salida / archivos["gpx"].name)
    shutil.copy2(archivos["base"], carpeta_salida / archivos["base"].name)
    shutil.copy2(archivos["mobile"], carpeta_salida / archivos["mobile"].name)

    print("\n[9/9] Exportando CSV, GeoPackage y gráficos de control...")
    out_csv = carpeta_salida / f"datos_sincronizados_{etiqueta_fecha}.csv"
    out_gpkg = carpeta_salida / f"datos_sincronizados_{etiqueta_fecha}.gpkg"
    out_png = carpeta_salida / f"graficos_{etiqueta_fecha}.png"

    # 'time' (datetime completo) se usa solo para los gráficos; no forma
    # parte del CSV/GPKG exportado, para no alterar el formato ya acordado.
    df_export = df_final.drop(columns=["time"])
    exportar_resultados(df_export, out_csv, out_gpkg)
    generar_graficos(df_base, df_mov, df_final, out_png)

    resumen = (
        f"{len(df_final)} puntos sincronizados.\n\n"
        f"Carpeta de resultados:\n{carpeta_salida}"
    )
    print(f"\nProceso finalizado. {resumen}")
    _mostrar_mensaje("SynchMag — Proceso finalizado", resumen)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n[ERROR] {e}")
        _mostrar_mensaje("SynchMag — Error", str(e), es_error=True)
        input("\nPresioná Enter para salir...")
        sys.exit(1)
