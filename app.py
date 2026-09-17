import tempfile
import io
import zipfile
from pathlib import Path
import fiona
import streamlit as st
from pyproj import CRS
from converter import MAX_UPLOAD, extract, sidecar, convert, package

st.set_page_config(page_title='SHP 转 KML / KMZ', page_icon='🗺️', layout='wide')
st.title('🗺️ SHP 转 KML / KMZ')
st.caption('中文属性 · WGS84 经纬度 · 批量上传、转换、下载 · 无需登录')
st.warning('每个 ZIP 上传上限 1 GB（1024 MB），多个上传文件会累计占用内存。云端内存有限，允许上传不代表能处理任意 1 GB 文件；大文件建议在本机运行。解压总量上限 4 GB。')
st.caption('文件会上传到运行本工具的服务器；转换不调用外部服务。临时工作文件在本次处理结束后删除。')
uploads = st.file_uploader('批量上传 Shapefile ZIP（可多选）', type=['zip'], accept_multiple_files=True)
if uploads:
    st.info(f'已选择 {len(uploads)} 个压缩包，总计 {sum(u.size for u in uploads) / 1024**2:.1f} MB')
    with tempfile.TemporaryDirectory(prefix='shp2kml-') as directory:
        root = Path(directory)
        layers = []
        owners = {}
        for archive_index, upload in enumerate(uploads):
            archive_id = f'{archive_index+1:03d}'
            folder = root / archive_id
            folder.mkdir()
            try:
                if upload.size > MAX_UPLOAD:
                    raise ValueError('ZIP 超过 1 GB 上限')
                extract(upload, folder)
                found = sorted(p for p in folder.rglob('*') if p.suffix.lower() == '.shp')
                if not found:
                    raise ValueError('未找到 .shp 文件')
                layers.extend(found)
                owners[archive_id] = (upload.name, upload.file_id)
            except Exception as exc:
                st.error(f'{upload.name}：{exc}')
        configs = []
        for index, shp in enumerate(layers):
            relative = shp.relative_to(root).as_posix()
            archive_id = shp.relative_to(root).parts[0]
            archive_name, file_id = owners[archive_id]
            widget_id = f'{file_id}-{relative}'
            with st.expander(f'{archive_id} · {archive_name} / {shp.relative_to(root / archive_id)}', expanded=True):
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
                    encoding = st.selectbox('DBF 编码', ['UTF-8', 'GBK'], index=int(detected == 'GBK'), key=f'enc-{widget_id}')
                    with fiona.open(shp, encoding=encoding) as layer:
                        source_crs = layer.crs_wkt or layer.crs
                        st.write({'文件名': relative, '要素数': len(layer), '几何类型': layer.schema['geometry'], '坐标系': CRS(source_crs).to_string() if source_crs else '缺少 .prj'})
                    override = None
                    if not source_crs:
                        choice = st.selectbox('源坐标系（必须根据数据来源选择）', ['请选择', 'EPSG:4326', 'EPSG:4490', 'EPSG:3857', '其他 EPSG'], key=f'crs-{widget_id}')
                        if choice == '其他 EPSG':
                            number = st.text_input('EPSG 代码', key=f'epsg-{widget_id}')
                            override = 'EPSG:' + number if number else None
                        elif choice != '请选择':
                            override = choice
                        if override:
                            CRS.from_user_input(override)
                    configs.append((shp, encoding, override, bool(source_crs or override)))
                except Exception as exc:
                    st.error(f'图层读取失败：{exc}')
        fmt = st.radio('输出格式', ['KML', 'KMZ'], horizontal=True)
        signature = (tuple(u.file_id for u in uploads), fmt, tuple((str(p.relative_to(root)), e, c, r) for p, e, c, r in configs))
        if st.session_state.get('batch_signature') != signature:
            st.session_state.pop('batch_results', None)
        if st.button('批量开始转换', type='primary', disabled=not configs):
            st.session_state.pop('batch_results', None)
            output_dir = root / '_converted'
            output_dir.mkdir(exist_ok=True)
            completed = {}
            progress = st.progress(0.0)
            for index, (shp, encoding, override, ready) in enumerate(configs):
                try:
                    if not ready:
                        raise ValueError('缺少 PRJ，请选择源 EPSG 后重试')
                    archive_id = shp.relative_to(root).parts[0]
                    archive_dir = output_dir / archive_id
                    archive_dir.mkdir(exist_ok=True)
                    output = archive_dir / f'{index+1:03d}_{shp.stem}.kml'
                    with st.spinner(f'正在转换 {shp.name}'):
                        engine, warning = convert(shp, output, override, encoding)
                    if warning:
                        st.warning(f'{shp.name}：ogr2ogr 失败，已使用备用引擎。原因：{warning}')
                    st.success(f'{shp.name} 转换完成（{engine}）')
                    completed.setdefault(archive_id, []).append(output)
                except Exception as exc:
                    st.error(f'{shp.name} 转换失败：{exc}')
                finally:
                    progress.progress((index + 1) / len(configs))
            if completed:
                results = []
                combined = io.BytesIO()
                with zipfile.ZipFile(combined, 'w', zipfile.ZIP_DEFLATED) as bundle:
                    for archive_id, files in completed.items():
                        name, content = package(files, fmt)
                        source_name = owners[archive_id][0]
                        safe_name = Path(source_name.replace('\\', '/')).stem
                        download_name = f'{archive_id}_{safe_name}' + Path(name).suffix
                        results.append((source_name, download_name, content))
                        bundle.writestr(download_name, content)
                st.session_state['batch_results'] = (results, combined.getvalue())
                st.session_state['batch_signature'] = signature
        saved = st.session_state.get('batch_results')
        if saved:
            results, combined = saved
            st.download_button('一键下载全部结果 ZIP', combined, 'batch_shp2kml_results.zip', 'application/zip', on_click='ignore')
            for index, (source_name, name, content) in enumerate(results):
                mime = 'application/zip' if name.endswith('.zip') else ('application/vnd.google-earth.kmz' if name.endswith('.kmz') else 'application/vnd.google-earth.kml+xml')
                st.download_button(f'下载 {source_name} 的结果', content, name, mime, key=f'download-{index}', on_click='ignore')
else:
    st.session_state.pop('batch_results', None)
    st.session_state.pop('batch_signature', None)
