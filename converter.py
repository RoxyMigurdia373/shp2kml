import io
import math
import os
import shutil
import stat
import subprocess
import sys
import logging
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

MAX_UPLOAD = 1024**3

def extract(source, dest):
    dest = Path(dest).resolve()
    source.seek(0)
    with zipfile.ZipFile(source) as archive:
        entries = archive.infolist()
        if len(entries) > 10000:
            raise ValueError('ZIP 文件数量超过 10000')
        total = 0
        seen = set()
        for item in entries:
            name = item.filename.replace('\\', '/')
            target = (dest / name).resolve()
            if ':' in name or name.startswith('/') or '..' in Path(name).parts or dest not in target.parents:
                raise ValueError('ZIP 包含不安全路径')
            if stat.S_ISLNK(item.external_attr >> 16):
                raise ValueError('ZIP 不允许符号链接')
            key = str(target).casefold()
            if key in seen:
                raise ValueError('ZIP 包含重复路径')
            seen.add(key)
            total += item.file_size
            if total > 4 * MAX_UPLOAD or item.file_size > max(item.compress_size, 1) * 1000:
                raise ValueError('解压体积超过 4 GB 或压缩比超过 1000')
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(item) as src, target.open('wb') as dst:
                    shutil.copyfileobj(src, dst, 1024 * 1024)

def sidecar(shp, ext):
    return next((p for p in shp.parent.iterdir() if p.stem.casefold() == shp.stem.casefold() and p.suffix.casefold() == ext), None)

def clean(value):
    text = '' if value is None else str(value)
    return ''.join(c for c in text if c in '\t\n\r' or 0x20 <= ord(c) <= 0xD7FF or 0xE000 <= ord(c) <= 0xFFFD or 0x10000 <= ord(c) <= 0x10FFFF)

def geometry_xml(g):
    if g is None or g.is_empty:
        return ''
    def coords(seq):
        values = []
        for p in seq:
            if not all(math.isfinite(v) for v in p):
                raise ValueError('坐标转换产生非有限值，请检查源 CRS')
            if not -180.00001 <= p[0] <= 180.00001 or not -90.00001 <= p[1] <= 90.00001:
                raise ValueError('坐标不在经纬度范围，请检查源 CRS')
            values.append(','.join(format(v, '.15g') for v in p[:2]) + ',0')
        return '<coordinates>' + ' '.join(values) + '</coordinates>'
    kind = g.geom_type
    if kind == 'Point':
        return '<Point>' + coords(g.coords) + '</Point>'
    if kind in ('LineString', 'LinearRing'):
        return '<LineString>' + coords(g.coords) + '</LineString>'
    if kind == 'Polygon':
        from shapely.geometry.polygon import orient
        g = orient(g, sign=1.0)
        result = '<Polygon><outerBoundaryIs><LinearRing>' + coords(g.exterior.coords) + '</LinearRing></outerBoundaryIs>'
        for ring in g.interiors:
            result += '<innerBoundaryIs><LinearRing>' + coords(ring.coords) + '</LinearRing></innerBoundaryIs>'
        return result + '</Polygon>'
    if kind.startswith('Multi') or kind == 'GeometryCollection':
        return '<MultiGeometry>' + ''.join(geometry_xml(part) for part in g.geoms) + '</MultiGeometry>'
    raise ValueError('不支持的几何类型：' + kind)

def write_kml(source, output, encoding, crs=None):
    import fiona
    from pyproj import Transformer
    from shapely.geometry import shape
    from shapely.ops import transform
    with fiona.open(source, encoding=encoding) as layer:
        source_crs = crs or layer.crs_wkt or layer.crs
        if not source_crs:
            raise ValueError('缺少源 CRS')
        transformer = Transformer.from_crs(source_crs, 'EPSG:4326', always_xy=True)
        def project(x, y, z=None):
            return transformer.transform(x, y, errcheck=True)
        with open(output, 'w', encoding='utf-8') as out:
            out.write('<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document>')
            for feature in layer:
                out.write('<Placemark><ExtendedData>')
                for key, value in feature['properties'].items():
                    out.write('<Data name=' + quoteattr(clean(key)) + '><value>' + escape(clean(value)) + '</value></Data>')
                out.write('</ExtendedData>')
                if feature['geometry']:
                    out.write(geometry_xml(transform(project, shape(feature['geometry']))))
                out.write('</Placemark>')
            out.write('</Document></kml>')

def convert(shp, output, crs, encoding):
    ogr = shutil.which('ogr2ogr')
    bundled_root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[2])) / 'gdal'
    if not ogr and (bundled_root / 'ogr2ogr.exe').is_file():
        ogr = str(bundled_root / 'ogr2ogr.exe')
    warning = None
    if ogr:
        intermediate = output.with_suffix('.geojson')
        cmd = [ogr, '-f', 'GeoJSON', str(intermediate), str(shp), '-t_srs', 'EPSG:4326', '-oo', 'ENCODING=' + encoding]
        if crs:
            cmd += ['-s_srs', crs]
        try:
            env = os.environ.copy()
            # 独立 CLI 的 DLL/数据只传给该子进程，避免污染 Fiona/PyProj。
            if Path(ogr).resolve().parent == bundled_root.resolve():
                env['PATH'] = str(bundled_root) + os.pathsep + env.get('PATH', '')
                if (bundled_root / 'gdal-data').is_dir():
                    env['GDAL_DATA'] = str(bundled_root / 'gdal-data')
                if (bundled_root / 'proj-data').is_dir():
                    env['PROJ_LIB'] = str(bundled_root / 'proj-data')
                    env['PROJ_DATA'] = str(bundled_root / 'proj-data')
            # PyInstaller 修改的 DLL 查找目录不能传给外部 GDAL 程序。
            if os.name == 'nt' and getattr(sys, 'frozen', False):
                import ctypes
                ctypes.windll.kernel32.SetDllDirectoryW(None)
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8',
                    errors='replace', timeout=600, env=env,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            finally:
                if os.name == 'nt' and getattr(sys, 'frozen', False):
                    ctypes.windll.kernel32.SetDllDirectoryW(sys._MEIPASS)
            if proc.returncode:
                raise ValueError(proc.stderr[-2000:])
            write_kml(intermediate, output, 'UTF-8', 'EPSG:4326')
            return 'ogr2ogr', None
        except Exception as exc:
            warning = str(exc)
            logging.getLogger(__name__).warning('ogr2ogr 失败，改用 Fiona + PyProj：%s', exc)
        finally:
            intermediate.unlink(missing_ok=True)
    if not ogr:
        logging.getLogger(__name__).info('ogr2ogr 不可用，使用 Fiona + PyProj')
    write_kml(shp, output, encoding, crs)
    return 'Fiona + PyProj', warning

def package(files, fmt):
    outputs = []
    for p in files:
        if fmt == 'KMZ':
            target = p.with_suffix('.kmz')
            with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as z:
                z.write(p, 'doc.kml')
            outputs.append(target)
        else:
            outputs.append(p)
    if len(outputs) == 1:
        return outputs[0].name, outputs[0].read_bytes()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as z:
        for p in outputs:
            z.write(p, p.name)
    return 'shp2kml_results.zip', buffer.getvalue()
