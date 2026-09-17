import io, tempfile, zipfile, unittest
from pathlib import Path
from xml.etree import ElementTree as ET
import fiona
from shapely.geometry import Point, LineString, Polygon, MultiPoint, MultiLineString, MultiPolygon, mapping
from pyproj import Transformer
from converter import extract, convert, package, geometry_xml
NS = {'k':'http://www.opengis.net/kml/2.2'}

class ConversionTests(unittest.TestCase):
    def test_geometries_and_encodings(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            polygon = Polygon([(116,39),(117,39),(117,40),(116,40),(116,39)], [[(116.2,39.2),(116.2,39.4),(116.4,39.4),(116.4,39.2),(116.2,39.2)]])
            cases = [Point(116.4,39.9), LineString([(116,39),(117,40)]), polygon, MultiPoint([(116,39),(117,40)]), MultiLineString([[(116,39),(117,40)]]), MultiPolygon([polygon])]
            for i, g in enumerate(cases):
                for encoding in ['UTF-8','GBK']:
                    shp = root / f'case{i}_{encoding}.shp'
                    schema = {'geometry': 'Polygon' if g.geom_type == 'MultiPolygon' else g.geom_type, 'properties': {'name':'str:80','count':'int'}}
                    with fiona.open(shp,'w',driver='ESRI Shapefile',crs='EPSG:4326',schema=schema,encoding=encoding) as dst:
                        dst.write({'geometry':mapping(g),'properties':{'name':'北京 & <测试>','count':42}})
                    output = shp.with_suffix('.kml')
                    convert(shp,output,None,encoding)
                    doc = ET.parse(output)
                    self.assertEqual(doc.find('.//k:Data[@name="name"]/k:value',NS).text,'北京 & <测试>')
                    self.assertEqual(doc.find('.//k:Data[@name="count"]/k:value',NS).text,'42')
                    self.assertTrue(doc.findall('.//k:coordinates',NS))
                    if g.geom_type in ['Polygon','MultiPolygon']:
                        self.assertEqual(len(doc.findall('.//k:innerBoundaryIs',NS)),1)
                    name, data = package([output], 'KMZ')
                    self.assertTrue(name.endswith('.kmz'))
                    with zipfile.ZipFile(io.BytesIO(data)) as z:
                        self.assertEqual(z.namelist(), ['doc.kml'])
                        ET.fromstring(z.read('doc.kml'))

    def test_projection(self):
        with tempfile.TemporaryDirectory() as d:
            shp = Path(d)/'projected.shp'
            x,y = Transformer.from_crs(4326,3857,always_xy=True).transform(116.4,39.9)
            with fiona.open(shp,'w',driver='ESRI Shapefile',crs='EPSG:3857',schema={'geometry':'Point','properties':{'name':'str'}},encoding='UTF-8') as dst:
                dst.write({'geometry':mapping(Point(x,y)),'properties':{'name':'北京'}})
            output = shp.with_suffix('.kml')
            convert(shp,output,None,'UTF-8')
            lon,lat,*_ = map(float,ET.parse(output).find('.//k:coordinates',NS).text.split(','))
            self.assertAlmostEqual(lon,116.4,places=7)
            self.assertAlmostEqual(lat,39.9,places=7)
            shp.with_suffix('.prj').unlink()
            convert(shp,output,'EPSG:3857','UTF-8')
            self.assertIn('116.4', output.read_text(encoding='utf-8'))

    def test_zip_traversal(self):
        for name in ['../evil.shp','/evil.shp','C:/evil.shp','..\\evil.shp']:
            with tempfile.TemporaryDirectory() as d:
                buffer = io.BytesIO()
                with zipfile.ZipFile(buffer,'w') as z: z.writestr(name,b'x')
                with self.assertRaises(ValueError): extract(buffer,Path(d))

if __name__ == '__main__': unittest.main()
