"""生成供 QGIS / Google Earth 人工验收的合成数据。"""
from pathlib import Path
import tempfile, zipfile
import fiona
from shapely.geometry import Point, LineString, Polygon, mapping

out = Path(__file__).parent / 'samples.zip'
with tempfile.TemporaryDirectory() as directory:
    root = Path(directory)
    for name, geometry in [('point',Point(116.4,39.9)),('line',LineString([(116.4,39.9),(116.5,40.0)])),('polygon',Polygon([(116.4,39.9),(116.5,39.9),(116.5,40.0),(116.4,40.0),(116.4,39.9)]))]:
        shp = root / (name+'.shp')
        with fiona.open(shp,'w',driver='ESRI Shapefile',crs='EPSG:4326',schema={'geometry':geometry.geom_type,'properties':{'name':'str:80','value':'int'}},encoding='UTF-8') as dst:
            dst.write({'geometry':mapping(geometry),'properties':{'name':'中文测试 & <属性>','value':42}})
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as archive:
        for p in root.iterdir(): archive.write(p,p.name)
print(out)
