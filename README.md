# SHP 转 KML / KMZ

中文 Streamlit 工具，上传 Shapefile ZIP 后逐图层转换为 EPSG:4326 KML 2.2 或 KMZ。应用无需登录，转换不调用外部服务；云端部署时文件会上传到云端服务器。

## 仓库结构
- `app.py`：中文界面、逐图层编码/CRS选择、下载
- `converter.py`：安全解压、ogr2ogr 主路径、Fiona/PyProj 备用路径、统一 XML 输出
- `requirements.txt`：Python 依赖
- `packages.txt`：系统 GDAL apt 依赖
- `.streamlit/config.toml`：上传上限 1024 MB
- `test_converter.py`：转换与安全回归测试
- `make_samples.py` / `samples.zip`：带中文属性的点线面合成测试数据

## 本机运行
建议 Python 3.11：
```sh
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```
Linux 可使用 `sudo apt-get install gdal-bin libgdal-dev`。Windows 未安装 ogr2ogr 时自动使用 Fiona/PyProj。GeoPandas 列为依赖，备用实现直接流式读取 Fiona，以减少整图层装入内存。

## Streamlit Community Cloud
1. 将本目录文件提交到 GitHub 仓库根目录，保留 `.streamlit/config.toml` 路径。
2. 登录 https://share.streamlit.io ，创建应用，选择仓库、`main` 分支及入口 `app.py`。
3. Advanced settings 中选择 Python **3.11**，随后 Deploy。
4. Cloud 构建时自动读取根目录 `requirements.txt`，安装 Python 包；读取 `packages.txt`，通过 apt 安装 `gdal-bin` 和 `libgdal-dev`。修改依赖后会重建环境，必要时 Reboot。
5. 查看构建日志确认 GDAL 安装成功。无需 pip 安装 `gdal`，避免系统库与 Python GDAL 版本不匹配。

## 行为与限制
- ZIP 最大 1 GiB（界面标注 1 GB / 1024 MB）。解压总量最多 4 GiB、10000 文件、压缩比不超过 1000，拒绝路径穿越和符号链接。
- Streamlit 上传与下载仍使用内存。云端约 1 GB 内存时不保证可以处理接近上限的数据；大文件请本地运行。未进行真实 1 GB 云端压力测试。
- 每个 SHP 必须有 SHX、DBF。CPG 优先识别 UTF-8/65001、GBK/936；无 CPG 或需覆盖时可选编码。中文字段名仍受 Shapefile 字段名长度限制。
- PRJ 自动识别；缺失时必须逐图层选择源 EPSG。不能把源投影坐标直接当经纬度。
- 支持 Point/LineString/Polygon/Multi*、多边形孔洞和空几何，所有属性写入 ExtendedData，XML 转义。输出为二维经纬度，高程置 0，不进行垂直基准转换。
- ogr2ogr 先输出 WGS84 GeoJSON，再统一流式输出 KML；失败则使用 Fiona/PyProj，并显示错误原因。
- 单文件直接下载 KML 或 KMZ（含 doc.kml）；多文件下载 ZIP，每图层独立结果。失败图层不影响其他图层。
- 临时文件在本次页面处理结束时删除；结果字节留在当前 Streamlit 会话中供下载，下一次转换会替换。

## 测试与人工验收
```sh
python -m unittest discover -v
python make_samples.py
```
自动测试涵盖六类几何、孔洞、UTF-8/GBK 中文与 XML 特殊字符、EPSG:3857 到 4326、缺失 PRJ 显式源 CRS、KMZ doc.kml 和 ZIP 路径穿越。

上传 `samples.zip`，预期 point/line/polygon 各 1 要素，EPSG:4326，属性 name 为 `中文测试 & <属性>`、value 为 42。点在 (116.4,39.9)，线到 (116.5,40.0)，面范围为 116.4–116.5 / 39.9–40.0。

在 QGIS 添加下载 KML/KMZ 并查看属性表；在 Google Earth Pro 文件→打开，展开三个图层查看位置及气泡属性。两者均应显示北京附近位置、完整属性及正常中文。尚未在 QGIS / Google Earth GUI 中实际验收；自动测试不等同于这项人工验收。
