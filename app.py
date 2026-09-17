import tempfile
from pathlib import Path
import fiona
import streamlit as st
from pyproj import CRS
from converter import MAX_UPLOAD, extract, sidecar, convert, package

st.set_page_config(page_title='SHP 转 KML / KMZ', page_icon='🗺️', layout='wide')
st.title('🗺️ SHP 转 KML / KMZ')
st.caption('中文属性 · WGS84 经纬度 · 多图层转换 · 无需登录')
st.warning('ZIP 上传上限 1 GB（1024 MB）。云端内存有限，允许上传不代表能处理任意 1 GB 文件；大文件建议在本机运行。解压总量上限 4 GB。')
st.caption('文件会上传到运行本工具的服务器；转换不调用外部服务。临时工作文件在本次处理结束后删除。')
upload = st.file_uploader('上传包含 .shp / .shx / .dbf / .prj / .cpg 的 ZIP', type=['zip'])
if upload:
    if upload.size > MAX_UPLOAD:
        st.error('ZIP 超过 1 GB 上限')
        st.stop()
    with tempfile.TemporaryDirectory(prefix='shp2kml-') as directory:
        root = Path(directory)
        try:
            extract(upload, root)
        except Exception as exc:
            st.error(f'无法解压：{exc}')
            st.stop()
        layers = sorted(p for p in root.rglob('*') if p.suffix.lower() == '.shp')
        if not layers:
            st.error('未找到 .shp 文件')
            st.stop()
        configs = []
        for index, shp in enumerate(layers):
            relative = shp.relative_to(root).as_posix()
            with st.expander(relative, expanded=True):
                try:
                    for extension in ('.shx', '.dbf'):
                        if not sidecar(shp, extension):
                            raise ValueError(f'缺少配套文件 {extension}')
                    # Normalize sidecar case for Linux GDAL.
                    for extension in ('.shx', '.dbf', '.prj', '.cpg'):
                        path = sidecar(shp, extension)
                        expected = shp.with_suffix(extension)
                        if path and path != expected and not expected.exists():
                            path.rename(expected)
                    cpg = sidecar(shp, '.cpg')
                    declared = cpg.read_text(encoding='utf-8-sig', errors='replace').strip() if cpg else ''
                    aliases = {'UTF8':'UTF-8', 'UTF-8':'UTF-8', '65001':'UTF-8', 'GBK':'GBK', '936':'GBK', 'CP936':'GBK', 'GB2312':'GBK'}
                    detected = aliases.get(declared.upper())
                    if declared:
                        st.caption(f'CPG 编码：{declared}')
                    if declared and not detected:
                        st.warning('CPG 编码无法识别，请选择正确的 DBF 编码。')
                    encoding = st.selectbox('DBF 编码', ['UTF-8', 'GBK'], index=int(detected == 'GBK'), key=f'enc-{relative}')
                    with fiona.open(shp, encoding=encoding) as layer:
                        source_crs = layer.crs_wkt or layer.crs
                        st.write({'文件名': relative, '要素数': len(layer), '几何类型': layer.schema['geometry'], '坐标系': CRS(source_crs).to_string() if source_crs else '缺少 .prj'})
                    override = None
                    if not source_crs:
                        choice = st.selectbox('源坐标系（必须根据数据来源选择）', ['请选择', 'EPSG:4326', 'EPSG:4490', 'EPSG:3857', '其他 EPSG'], key=f'crs-{relative}')
                        if choice == '其他 EPSG':
                            number = st.text_input('EPSG 代码', key=f'epsg-{relative}')
                            override = 'EPSG:' + number if number else None
                        elif choice != '请选择':
                            override = choice
                        if override:
                            CRS.from_user_input(override)
                    configs.append((shp, encoding, override, bool(source_crs or override)))
                except Exception as exc:
                    st.error(f'图层读取失败：{exc}')
        fmt = st.radio('输出格式', ['KML', 'KMZ'], horizontal=True)
        if st.button('开始转换', type='primary'):
            st.session_state.pop('result', None)
            output_dir = root / '_converted'
            output_dir.mkdir(exist_ok=True)
            completed = []
            for index, (shp, encoding, override, ready) in enumerate(configs):
                try:
                    if not ready:
                        raise ValueError('缺少 PRJ，请选择源 EPSG 后重试')
                    output = output_dir / f'{index+1:03d}_{shp.stem}.kml'
                    with st.spinner(f'正在转换 {shp.name}'):
                        engine, warning = convert(shp, output, override, encoding)
                    if warning:
                        st.warning(f'{shp.name}：ogr2ogr 失败，已使用备用引擎。原因：{warning}')
                    st.success(f'{shp.name} 转换完成（{engine}）')
                    completed.append(output)
                except Exception as exc:
                    st.error(f'{shp.name} 转换失败：{exc}')
            if completed:
                st.session_state['result'] = (upload.file_id, fmt, package(completed, fmt))
        result = st.session_state.get('result')
        if result and result[:2] == (upload.file_id, fmt):
            name, content = result[2]
            mime = 'application/zip' if name.endswith('.zip') else ('application/vnd.google-earth.kmz' if name.endswith('.kmz') else 'application/vnd.google-earth.kml+xml')
            st.download_button('下载转换结果', content, name, mime, on_click='ignore')
