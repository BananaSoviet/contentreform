# -*- coding: utf-8 -*-
"""`pkp estado`: el bloque generado de `docs/ESTADO-AHORA.md` (TSV + git).

La pagina de estado se mantenia a mano, y una pagina a mano se convierte en
otro briefing en dos semanas. Este modulo genera lo que si es maquina: la
version del paquete, el ultimo commit, la tabla de unidades leida del TSV y
la marca de frescura (la fecha estampada en la cabecera de la pagina y si ha
caducado). Lee `docs/ESTADO-VEHICULOS.tsv` y git; **no** lee el tablero: las
tarjetas cambian en minutos y no son producto.

El bloque vive en la pagina entre dos marcadores HTML:

    <!-- ESTADO:GENERADO:INICIO -->
    ... bloque generado ...
    <!-- ESTADO:GENERADO:FIN -->

y `--write` reescribe **solo** ese hueco: todo lo demas del fichero se
conserva byte a byte (es texto de Edu y de las actas). `--check` devuelve
codigo 1 si la pagina esta caducada (mas de `CADUCIDAD_DIAS` dias), si el
bloque real no coincide con lo generable, o si un commit citado (cabecera
o sello del bloque) no es ancestro de HEAD: el sello es de cuando se
genero y cualquier commit posterior -- incluido el de la propia pagina --
es legitimo (t_b4961d90). `--write` no reescribe nada si lo unico que
cambiaria es ese sello: no hay nada nuevo.

Solo stdlib (`tomllib`, 3.11+; el proyecto se declara para >=3.11,<3.12).
Sin rutas de maquina: la raiz se deriva de `__file__` y las rutas por
defecto son relativas a ella.
"""

from __future__ import annotations

import datetime as dt
import os
import re
import subprocess
import tomllib

#: delimitan el bloque generado dentro de la pagina.
MARCA_INI = "<!-- ESTADO:GENERADO:INICIO -->"
MARCA_FIN = "<!-- ESTADO:GENERADO:FIN -->"

#: dias que la pagina sigue valiendo; despues se remide, no se cita
#: (CANON regla 15).
CADUCIDAD_DIAS = 3

TSV_POR_DEFECTO = os.path.join("docs", "ESTADO-VEHICULOS.tsv")
PAGINA_POR_DEFECTO = os.path.join("docs", "ESTADO-AHORA.md")

#: linea fija del documento que entra en el bloque generado (constante: el
#: TSV es la fuente, la pagina solo la declara).
LINEA_FUENTE = ("Fuente: `docs/ESTADO-VEHICULOS.tsv`. Cada fila tiene su "
                "orden de banco; no se copia la salida aquí.")

#: la cabecera de la pagina son las primeras lineas; el bloque generado esta
#: mas abajo y no debe leerse como cabecera.
LINEAS_CABECERA = 10

_MESES = {"ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
          "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12}
_MES_REV = {num: mes for mes, num in _MESES.items()}

#: `**18-nov-2026 14:51**` — como la cabecera de la pagina.
_FECHA_RE = re.compile(r"\*\*(\d{2})-([A-Za-z]{3})-(\d{4})"
                       r"(?:\s+(\d{2}:\d{2}))?\*\*")
_COMMIT_RE = re.compile(r"commit\s+`([0-9a-fA-F]{4,40})`")

#: marca de firma estructurada: la celda `listo` EMPIEZA con `sí · FIRMADA`.
#: una mención de «firmada» en prosa dentro de la nota (p. ej. el
#: «prueba 3 firmada» de B1) NO es una firma (t_f36395f3).
_FIRMADA_RE = re.compile(r"^\s*sí\s*·\s*FIRMADA\b", re.IGNORECASE)


class EstadoError(Exception):
    """No se puede generar ni comprobar el bloque (mensaje para quien manda)."""

    def __init__(self, mensaje: str, exit_code: int = 1):
        super().__init__(mensaje)
        self.exit_code = exit_code


def raiz_por_defecto() -> str:
    """El directorio que contiene el paquete (la raiz del repo)."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def leer_version(raiz: str) -> str | None:
    """Version del paquete: `[project] version` de `pyproject.toml`.

    Si el proyecto la declara dinamica (fuente unica `pokopia.__version__`,
    tarjeta `t_2d71193b`), se lee esa; es la misma que imprime `pkp
    --version`. None solo si no hay ninguna de las dos.
    """
    try:
        with open(os.path.join(raiz, "pyproject.toml"), "rb") as fh:
            cfg = tomllib.load(fh)
        version = cfg["project"]["version"]
        if isinstance(version, str) and version:
            return version
    except (OSError, tomllib.TOMLDecodeError, KeyError, TypeError):
        pass
    from . import __version__
    return __version__ or None


def ultimo_commit(raiz: str) -> str | None:
    """`git rev-parse --short HEAD`; None si no hay git o git falla."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=raiz, capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if res.returncode != 0:
        return None
    return res.stdout.strip() or None


def es_ancestro(raiz: str, citado: str) -> bool | None:
    """`git merge-base --is-ancestor <citado> HEAD` dentro de `raiz`.

    True si HEAD desciende de `citado` (o es el mismo commit), False si no
    desciende (rebase, rama distinta) y None si git no puede decidirlo
    (el commit no existe aqui, git ausente). Acepta el prefijo corto: git
    lo resuelve el.
    """
    try:
        res = subprocess.run(
            ["git", "merge-base", "--is-ancestor", citado, "HEAD"],
            cwd=raiz, capture_output=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if res.returncode == 0:
        return True
    if res.returncode == 1:
        return False
    return None


def enmascara_commit(texto: str) -> str:
    """El texto con el hash de `commit ...` sustituido por un marcador.

    El commit que estampa `generar` es un sello de cuando se escribio el
    bloque, no estado: el commit de la propia pagina (y cualquier otro
    posterior) lo deja obsoleto sin que el contenido haya cambiado. Se
    compara todo salvo ese hash; la ascendencia se comprueba aparte, con
    `es_ancestro`.
    """
    return _COMMIT_RE.sub("commit `<sello>`", texto)


def solo_cambia_el_sello(texto: str, nuevo: str, raiz: str) -> bool:
    """True si `nuevo` difiere de `texto` solo en el sello de commit, y ese
    sello sigue siendo ancestro de HEAD: no hay nada nuevo que escribir.

    Es la misma regla que `--check`: el sello es de cuando se genero, un
    commit posterior al de la pagina no es «algo nuevo». Si el sello no es
    ancestro (rebase) o no se puede resolver, se devuelve False para que
    `--write` reestampe.
    """
    if enmascara_commit(texto) != enmascara_commit(nuevo):
        return False
    partes = dividir(texto)
    if partes is None:
        return False
    sello = _COMMIT_RE.search(partes[1])
    if sello is None:
        return False
    if ultimo_commit(raiz) is None:
        return True  # sin git no hay sello que validar
    return es_ancestro(raiz, sello.group(1)) is True


def leer_unidades(ruta: str) -> list[dict]:
    """Filas del TSV: `id`, `vehiculo`, `listo` y si esta firmada.

    Firmada = la celda `listo` empieza con la marca de firma estructurada
    `sí · FIRMADA ...` (re `_FIRMADA_RE`). Una mención de «firmada» en prosa
    dentro de la nota (p. ej. el «prueba 3 firmada» de B1) NO cuenta.
    La cabecera tiene que tener las tres columnas; una fila mas corta que
    la cabecera es error, no se rellena.
    """
    try:
        with open(ruta, encoding="utf-8", newline="") as fh:
            crudo = fh.read()
    except UnicodeDecodeError as exc:
        raise EstadoError("%s: no es UTF-8 (%s)" % (ruta, exc)) from None
    lineas = [l for l in crudo.splitlines() if l.strip()]
    if not lineas:
        raise EstadoError("%s: vacio" % ruta)
    cab = lineas[0].split("\t")
    try:
        i_id = cab.index("id")
        i_veh = cab.index("vehículo")
        i_listo = cab.index("listo")
    except ValueError:
        raise EstadoError(
            "%s: la cabecera no tiene id/vehiculo/listo" % ruta) from None
    ultimo = max(i_id, i_veh, i_listo)
    filas: list[dict] = []
    for num, linea in enumerate(lineas[1:], start=2):
        c = linea.split("\t")
        if len(c) <= ultimo:
            raise EstadoError(
                "%s: fila %d con menos columnas que la cabecera"
                % (ruta, num))
        listo = c[i_listo]
        filas.append({"id": c[i_id], "vehiculo": c[i_veh], "listo": listo,
                      "firmada": _FIRMADA_RE.match(listo) is not None})
    if not filas:
        raise EstadoError("%s: sin filas de datos" % ruta)
    return filas


def cabecera(texto: str) -> tuple[dt.date | None, str | None, str | None]:
    """`(fecha, commit, fecha_en_texto)` de la cabecera de la pagina.

    Solo mira las primeras `LINEAS_CABECERA` lineas: el bloque generado
    tambien cita fecha y commit y no manda sobre la cabecera.
    """
    primeras = "\n".join(texto.splitlines()[:LINEAS_CABECERA])
    fecha: dt.date | None = None
    fecha_txt: str | None = None
    mfecha = _FECHA_RE.search(primeras)
    if mfecha:
        dia, mes = int(mfecha.group(1)), mfecha.group(2).lower()
        anyo = int(mfecha.group(3))
        if mes in _MESES:
            try:
                fecha = dt.date(anyo, _MESES[mes], dia)
                fecha_txt = mfecha.group(0).strip("*")
            except ValueError:
                fecha = None
    mcommit = _COMMIT_RE.search(primeras)
    return fecha, (mcommit.group(1) if mcommit else None), fecha_txt


def fecha_texto(fecha: dt.date) -> str:
    """18-nov-2026: dia con dos cifras, mes en espanol, como la cabecera."""
    return "%02d-%s-%04d" % (fecha.day, _MES_REV[fecha.month], fecha.year)


def frescura(fecha: dt.date, hoy: dt.date) -> tuple[bool, int]:
    """`(caducada, dias)` — caduca a los `CADUCIDAD_DIAS` dias."""
    dias = (hoy - fecha).days
    return dias > CADUCIDAD_DIAS, dias


def _bloque_fresco(fecha: dt.date, hoy: dt.date) -> str:
    caducada, dias = frescura(fecha, hoy)
    caduca = fecha_texto(fecha + dt.timedelta(days=CADUCIDAD_DIAS))
    if caducada:
        return ("CADUCADA (%d días, caducaba el %s): se remide, no se cita"
                % (dias, caduca))
    return "fresca (caduca el %s)" % caduca


def generar(raiz: str, pagina_ruta: str, tsv_ruta: str,
            hoy: dt.date | None = None) -> str:
    """El bloque generado (sin los marcadores), texto determinista."""
    hoy = hoy or dt.date.today()
    try:
        with open(pagina_ruta, encoding="utf-8", newline="") as fh:
            pagina = fh.read()
    except UnicodeDecodeError as exc:
        raise EstadoError("%s: no es UTF-8 (%s)" % (pagina_ruta, exc)) from None
    fecha, _, fecha_txt = cabecera(pagina)
    filas = leer_unidades(tsv_ruta)
    firmadas = [f for f in filas if f["firmada"]]
    version = leer_version(raiz)
    commit = ultimo_commit(raiz)

    if fecha is None:
        fecha_en_linea = "sin fecha legible"
        frescura_txt = "sin fecha en la cabecera: se remide"
    else:
        fecha_en_linea = fecha_txt or fecha_texto(fecha)
        frescura_txt = _bloque_fresco(fecha, hoy)

    lineas = [
        "## Firmado por Edu — %d de %d unidades" % (len(firmadas), len(filas)),
        "",
        ("Generado por `pkp estado` · versión `%s` · commit `%s` · "
         "página `%s` — %s."
         % (version or "no leída", commit or "sin git",
            fecha_en_linea, frescura_txt)),
        "",
        LINEA_FUENTE,
        "",
        "| id | vehículo | listo |",
        "|---|---|---|",
    ]
    for f in firmadas:
        lineas.append("| %s | %s | %s |"
                      % (f["id"],
                         f["vehiculo"].replace("|", "\\|"),
                         f["listo"].replace("|", "\\|")))
    return "\n".join(lineas)


def dividir(texto: str) -> tuple[str, str, str] | None:
    """`(antes, bloque, despues)` con los marcadores; None si faltan."""
    i = texto.find(MARCA_INI)
    j = texto.find(MARCA_FIN)
    if i < 0 or j < 0 or j < i + len(MARCA_INI):
        return None
    fin_ini = i + len(MARCA_INI)
    return texto[:fin_ini], texto[fin_ini:j], texto[j:]


def normaliza_bloque(bloque: str) -> str:
    """El bloque como texto comparable: mismos finales de linea, sin
    newline sobrante al principio ni al final."""
    return bloque.replace("\r\n", "\n").strip("\r\n")


def reemplazar(texto: str, bloque: str) -> str:
    """El texto con **solo** el bloque sustituido por `bloque`.

    Todo lo demas sale byte a byte igual (se opera sobre el texto tal cual,
    con su fin de linea original). Si faltan los marcadores, no se reescribe
    nada: se avisa y se sale sin tocar el fichero.
    """
    partes = dividir(texto)
    if partes is None:
        raise EstadoError(
            "faltan los marcadores %s / %s en la pagina: no se reescribe nada"
            % (MARCA_INI, MARCA_FIN), exit_code=2)
    antes, _, despues = partes
    tras_ini = texto[len(antes):len(antes) + 2]
    nl = "\r\n" if tras_ini.startswith("\r\n") else "\n"
    if nl != "\n":
        # el bloque sale con el mismo fin de linea que la pagina: si no, el
        # fichero quedaria mezclado y la proxima lectura no seria estable.
        bloque = bloque.replace("\n", nl)
    return antes + nl + bloque + nl + despues


def comprobar(raiz: str, pagina_ruta: str, tsv_ruta: str,
              hoy: dt.date | None = None) -> tuple[int, list[str]]:
    """`(codigo, problemas)`: 0 si la pagina cuadra con lo generable.

    Falla (1) con la pagina caducada, con el bloque manipulado a mano y con
    un commit citado (cabecera o sello del bloque) del que HEAD no
    desciende: el sello es de cuando se genero, no exige igualdad con
    HEAD (t_b4961d90).
    """
    hoy = hoy or dt.date.today()
    try:
        with open(pagina_ruta, encoding="utf-8", newline="") as fh:
            pagina = fh.read()
    except UnicodeDecodeError as exc:
        raise EstadoError("%s: no es UTF-8 (%s)" % (pagina_ruta, exc)) from None
    problemas: list[str] = []
    head = ultimo_commit(raiz)

    fecha, commit_pag, _ = cabecera(pagina)
    if fecha is None:
        problemas.append("la cabecera no cita una fecha legible")
    else:
        caducada, dias = frescura(fecha, hoy)
        if caducada:
            problemas.append(
                "la cabecera dice %s: lleva %d dias (> %d): se remide, "
                "no se cita" % (fecha_texto(fecha), dias, CADUCIDAD_DIAS))

    partes = dividir(pagina)
    if partes is None:
        problemas.append("faltan los marcadores ESTADO:GENERADO")
    else:
        actual = normaliza_bloque(partes[1])
        esperado = normaliza_bloque(
            generar(raiz, pagina_ruta, tsv_ruta, hoy=hoy))
        if enmascara_commit(actual) != enmascara_commit(esperado):
            problemas.append(
                "el bloque no coincide con lo generable (edicion a mano sin "
                "regenerar: vuelve a lanzar --write)")
        elif head is not None:
            sello = _COMMIT_RE.search(actual)
            if sello is not None:
                # el sello del bloque es de cuando se escribio: solo es
                # fallo si HEAD no desciende de el (t_b4961d90).
                anc = es_ancestro(raiz, sello.group(1))
                if anc is False:
                    problemas.append(
                        "el bloque cita commit %s, que no es ancestro de "
                        "HEAD %s: rebase o rama distinta"
                        % (sello.group(1), head))
                elif anc is None:
                    problemas.append(
                        "el bloque cita commit %s, que no se encuentra en "
                        "este repo (HEAD es %s)" % (sello.group(1), head))

    if commit_pag is None:
        problemas.append("la cabecera no cita ningun commit")
    elif head is None:
        pass  # sin git no se puede comparar; lo dice el propio bloque
    else:
        anc = es_ancestro(raiz, commit_pag)
        if anc is False:
            problemas.append(
                "la cabecera cita commit %s, que no es ancestro de HEAD %s: "
                "rebase o rama distinta" % (commit_pag, head))
        elif anc is None:
            problemas.append(
                "la cabecera cita commit %s, que no se encuentra en este "
                "repo (HEAD es %s)" % (commit_pag, head))

    return (0 if not problemas else 1), problemas
