"""Synthetic docker-save TAR fixtures; do not use any real operator secrets."""
import io
import tarfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'deploy/vela'))
import image_layer_audit as audit


def tar_bytes(entries):
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode='w') as archive:
        for name, content in entries.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
    return out.getvalue()


def image_bytes(layers, configs=None):
    entries = {f'{idx}/layer.tar': tar_bytes(items) for idx, items in enumerate(layers)}
    entries.update(configs or {})
    return io.BytesIO(tar_bytes(entries))


class ImageLayerTests(unittest.TestCase):
    def test_clean_image_all_layers(self):
        x = image_bytes([{'app/x-ui': b'compiled program', 'etc/ssl/certs/root.pem': b'public certificate'},
                         {'app/translation/en-US.json':b'{}'}], {'config.json':b'{"Env":["XUI_DB_TYPE=sqlite"]}'})
        layers, files, risks = audit.audit_image_save(x)
        self.assertEqual((layers, files, risks),(2,4,0))

    def test_deleted_in_later_layer_is_still_detected(self):
        x = image_bytes([{'app/.env':b'PRIVATE PLACEHOLDER'}, {'app/.wh..env':b''}])
        self.assertGreater(audit.audit_image_save(x)[2],0)

    def test_embedded_private_key_header(self):
        x = image_bytes([{'app/not-a-key.txt':(b'header\n-----BEGIN ' + b'OPENSSH ' + b'PRIVATE KEY-----\nPLACEHOLDER')}])
        self.assertGreater(audit.audit_image_save(x)[2],0)

    def test_token_split_across_stream_chunks(self):
        mock = b'99999999:' + b'A' * 39
        content = b'!' * (audit.CHUNK - 9) + mock
        x = image_bytes([{'app/note.txt':content}])
        self.assertGreater(audit.audit_image_save(x)[2],0)

    def test_metadata_leak(self):
        token=b'12345678:' + b'A'*35
        x=image_bytes([{'app/readme.txt':b'ok'}], {'config.json':b'{"Env":["TOKEN='+token+b'"]}'})
        self.assertGreater(audit.audit_image_save(x)[2],0)

    def test_oci_layout_gzip_layers_and_metadata(self):
        import gzip
        import hashlib
        import json

        def as_oci(layers, config):
            blobs = {}
            refs = []
            for contents in layers:
                data = gzip.compress(tar_bytes(contents))
                digest = hashlib.sha256(data).hexdigest()
                blobs[f'blobs/sha256/{digest}'] = data
                refs.append({'mediaType': 'application/vnd.oci.image.layer.v1.tar+gzip', 'digest': f'sha256:{digest}', 'size': len(data)})
            config_digest = hashlib.sha256(config).hexdigest()
            blobs[f'blobs/sha256/{config_digest}'] = config
            manifest = json.dumps({'schemaVersion': 2, 'config': {'digest': f'sha256:{config_digest}'}, 'layers': refs}).encode()
            manifest_digest = hashlib.sha256(manifest).hexdigest()
            blobs[f'blobs/sha256/{manifest_digest}'] = manifest
            blobs['index.json'] = json.dumps({'schemaVersion': 2, 'manifests': [{'digest': f'sha256:{manifest_digest}'}]}).encode()
            blobs['oci-layout'] = b'{"imageLayoutVersion":"1.0.0"}'
            return io.BytesIO(tar_bytes(blobs))

        with self.subTest('normal OCI tar'):
            stream = as_oci([{'app/x-ui': b'public test application'}, {'etc/ssl/certs/ca.pem': b'public cert'}], b'{"Env":["XUI_DB_TYPE=sqlite"]}')
            count, files, risks = audit.audit_image_save(stream)
            self.assertEqual(count, 2)
            self.assertGreaterEqual(files, 5)
            self.assertEqual(risks, 0)
        with self.subTest('deleted file in OCI layer'):
            stream = as_oci([{'app/.env': b'PRIVATE FAKE DATA'}, {'app/.wh..env': b''}], b'{}')
            self.assertGreater(audit.audit_image_save(stream)[2], 0)
        with self.subTest('credential in OCI config'):
            token = b'12345678:' + b'A' * 35
            stream = as_oci([{'app/x-ui': b'ok'}], b'{"Env":["TG='+token+b'"]}')
            self.assertGreater(audit.audit_image_save(stream)[2], 0)
        with self.subTest('corrupt OCI blob fails closed'):
            stream = io.BytesIO(tar_bytes({'blobs/sha256/' + 'f'*64: b'not a compressed or uncompressed tar'}))
            with self.assertRaises(ValueError):
                audit.audit_image_save(stream)

    def test_empty_or_corrupt_tar_refused(self):
        for content in (b'',b'not tar',tar_bytes({'manifest.json':b'[]'})):
            with self.subTest(size=len(content)),self.assertRaises(ValueError):
                audit.audit_image_save(io.BytesIO(content))


if __name__=='__main__':
    unittest.main()
