"""Teste do contrato NPY/NPZ e da avaliação sem precisar do XRMC instalado."""
import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from segmentador_fantomas.avaliar_simulacao import run


class TesteIntegracaoSimulacao(unittest.TestCase):
    def test_fluxo_com_pixels_originais_e_vinculo_da_referencia(self):
        rng = np.random.default_rng(42)
        image = np.zeros((256, 256), dtype=np.float64)
        image[24:232, 24:232] = 46000 + rng.normal(0, 10, (208, 208))
        y, x = np.mgrid[:256, :256]
        reference = ((x - 127.5)**2 + (y - 127.5)**2 <= 25**2).astype(np.int32)
        image[reference > 0] = 85000 + rng.normal(0, 15, int(reference.sum()))

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image_path = root / 'image.npy'
            reference_path = root / 'verdade_simulada.npz'
            np.save(image_path, image)
            np.savez_compressed(reference_path, labels=reference)
            reference_path.with_suffix('.json').write_text(json.dumps({
                'image_sha256': hashlib.sha256(image_path.read_bytes()).hexdigest(),
                'reference_objects': [{'reference_id': 1, 'shape': 'circle',
                                       'depth_mm': 5}],
            }), encoding='utf-8')

            output = root / 'resultado'
            metrics = run(image_path, reference_path, output)
            self.assertEqual((metrics['true_positives'], metrics['false_positives'],
                              metrics['false_negatives']), (1, 0, 0))
            self.assertGreater(metrics['pixel_iou_foreground'], 0.85)
            self.assertTrue((output / 'relatorio_simulacao.html').is_file())
            self.assertTrue((output / 'comparacao.png').is_file())
            with (output / 'resultados.csv').open(encoding='utf-8') as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(len(rows), 1)
            self.assertGreater(float(rows[0]['sinal_bruto']), 84000)
            with (output / 'profundidades_referencia.csv').open(encoding='utf-8') as stream:
                depth_rows = list(csv.DictReader(stream))
            self.assertEqual(depth_rows[0]['automatic_id'], 'R001')
            self.assertEqual(depth_rows[0]['depth_mm'], '5')
            with np.load(output / 'mascaras.npz', allow_pickle=False) as data:
                self.assertEqual(data['labels'].ndim, 2)

            image[100, 100] += 1
            np.save(image_path, image)
            with self.assertRaisesRegex(ValueError, 'SHA-256'):
                run(image_path, reference_path, root / 'resultado_errado')


if __name__ == '__main__':
    unittest.main()
