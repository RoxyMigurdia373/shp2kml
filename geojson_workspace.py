"""GeoJSON 转 SHP；复用现有矢量读写实现，避免两个转换器行为分歧。"""
import hashlib

import pandas as pd
import streamlit as st


from vector_io import read_vector, export_shapefile


def render_geojson_workspace():
    st.subheader('GeoJSON 转 SHP')
    st.caption('输出 WGS84（EPSG:4326）。点、线、面分别保存；ZIP 包含配套文件和字段映射。Shapefile 不保存显示样式。')
    upload = st.file_uploader('上传 GeoJSON 文件', type=['geojson', 'json'], key='geojson_shp_upload')
    if upload is None:
        for key in ('geojson_shp_identity', 'geojson_shp_frame', 'geojson_shp_result'):
            st.session_state.pop(key, None)
        return
    data = upload.getvalue()
    identity = hashlib.sha256(data + upload.name.encode()).hexdigest()
    try:
        if st.session_state.get('geojson_shp_identity') != identity:
            st.session_state.pop('geojson_shp_result', None)
            st.session_state.pop('geojson_shp_frame', None)
            frame = read_vector(data, upload.name)
            st.session_state.geojson_shp_frame = frame
            st.session_state.geojson_shp_identity = identity
        frame = st.session_state.geojson_shp_frame
        if frame.empty:
            st.warning('文件没有要素，请选择包含数据的文件。')
            return
        fields = [c for c in frame.columns if c != frame.geometry.name]
        st.caption(f'{len(frame):,} 个要素 / {len(fields)} 个属性字段 / 源坐标系：{frame.crs}')
        st.dataframe(pd.DataFrame(frame[fields].head(100)), hide_index=True, use_container_width=True)
        if st.button('生成 Shapefile ZIP', type='primary'):
            with st.spinner('正在转换…'):
                st.session_state.geojson_shp_result = export_shapefile(frame)
        if st.session_state.get('geojson_shp_result'):
            st.download_button('下载 Shapefile ZIP', st.session_state.geojson_shp_result,
                               'converted_shapefile.zip', 'application/zip')
    except Exception as exc:
        st.session_state.pop('geojson_shp_result', None)
        st.error(f'转换失败：{exc}')
