"""Confere que máscaras independentes estão alinhadas ao DICOM de origem."""
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, SecondaryCaptureImageStorage, generate_uid

from segmentador_fantomas.validar_referencia import sha256, validate


class TesteValidarReferencia(unittest.TestCase):
    def test_dimensoes_e_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dicom = root / 'imagem.dcm'
            meta = FileMetaDataset()
            meta.MediaStorageSOPClassUID = SecondaryCaptureImageStorage
            meta.MediaStorageSOPInstanceUID = generate_uid()
            meta.TransferSyntaxUID = ExplicitVRLittleEndian
            dataset = FileDataset(str(dicom), {}, file_meta=meta, preamble=b'\0' * 128)
            dataset.Rows = 20
            dataset.Columns = 30
            dataset.save_as(dicom, enforce_file_format=True)
            labels = np.zeros((20, 30), dtype=np.int32)
            labels[3:8, 4:10] = 1
            reference = root / 'referencia.npz'
            np.savez_compressed(reference, labels=labels)
            reference.with_suffix('.json').write_text(json.dumps({
                'origem': 'anotacao_manual_iniciada_em_branco',
                'dicom_sha256': sha256(dicom),
            }), encoding='utf-8')
            result = validate(dicom, reference)
            self.assertEqual(result['regioes'], 1)
            self.assertEqual(result['objetos'][0]['area_px'], 30)
            labels = labels[:19]
            np.savez_compressed(reference, labels=labels)
            with self.assertRaisesRegex(ValueError, 'não coincide'):
                validate(dicom, reference)


if __name__ == '__main__':
    unittest.main()
