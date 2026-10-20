import io
import json
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest


class Upload:
    name = 'sample.geojson'
    def getvalue(self):
        return json.dumps({'type': 'FeatureCollection', 'features': [{
            'type': 'Feature', 'properties': {'类别': '耕地'},
            'geometry': {'type': 'Point', 'coordinates': [116, 39]}}]}).encode()


class GeojsonUITests(unittest.TestCase):
    def test_actual_app_route_export_and_changed_upload(self):
        app = AppTest.from_file(str(Path(__file__).with_name('app.py'))).run()
        with patch('streamlit.file_uploader', return_value=Upload()):
            app.radio[0].set_value('GeoJSON 转 SHP').run()
            self.assertFalse(app.exception)
            self.assertEqual(app.subheader[0].value, 'GeoJSON 转 SHP')
            app.button[0].click().run()
            self.assertFalse(app.exception)
            with zipfile.ZipFile(io.BytesIO(app.session_state['geojson_shp_result'])) as z:
                self.assertTrue(any(n.endswith('.shp') for n in z.namelist()))
                self.assertIn('类别', json.loads(z.read('字段映射.json')))
        with patch('streamlit.file_uploader', return_value=None):
            app.run()
            self.assertNotIn('geojson_shp_result', app.session_state)


if __name__ == '__main__':
    unittest.main()
