import io, zipfile
from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
class Upload(io.BytesIO):
    def __init__(self,data,name,identity):
        super().__init__(data)
        self.name,self.file_id,self.size=name,identity,len(data)
data=Path('samples.zip').read_bytes()
uploads=[Upload(data,'same.zip','a'),Upload(data,'same.zip','b'),Upload(b'invalid','broken.zip','c')]
with patch('streamlit.file_uploader',return_value=uploads):
    app=AppTest.from_file('app.py').run()
    assert not app.exception
    app.button[0].click().run()
    assert not app.exception
    results,bundle=app.session_state['batch_results']
    assert len(results)==2
    assert any('broken.zip' in e.value for e in app.error)
    with zipfile.ZipFile(io.BytesIO(bundle)) as outer:
        assert len(set(outer.namelist()))==2
        for name in outer.namelist():
            with zipfile.ZipFile(io.BytesIO(outer.read(name))) as inner:
                assert len(inner.namelist())==3
                assert all(n.endswith('.kml') for n in inner.namelist())
    app.radio[0].set_value('KMZ').run()
    assert 'batch_results' not in app.session_state
    app.button[0].click().run()
    assert not app.exception
    results,bundle=app.session_state['batch_results']
    with zipfile.ZipFile(io.BytesIO(results[0][2])) as inner:
        assert all(n.endswith('.kmz') for n in inner.namelist())
print('Batch test passed: duplicate names, corrupt archive isolation, combined KML/KMZ downloads, stale-result invalidation')
