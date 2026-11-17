import unittest
import tempfile
import json
from pathlib import Path

import numpy as np
from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, SecondaryCaptureImageStorage, generate_uid

from radio2.avaliacao import evaluate_instances, image_quality
from radio2.editor_mascaras import (associacoes_para_revisao, carregar_associacoes,
                                    salvar_referencia_manual)
from radio2.gerar_curvas_fisicas_lote import latest_measurements, read_dataset
from radio2.mapear_profundidades import load_current_map, read_rows, save_mapping
from radio2.segmentacao import InsertoDetector
from radio2.transferir_profundidades import match_positions, transfer_group


class TesteAvaliacaoSintetica(unittest.TestCase):
    def test_mescla_fragmento_sobreposto_sem_impor_forma(self):
        large = np.ones((20, 40), dtype=bool)
        small = np.ones((8, 10), dtype=bool)
        objects = [
            {'slice': np.s_[10:30, 10:50], 'mask': large, 'area_px': 800,
             'cx': 29.5, 'cy': 19.5, 'polarity': 'escuro'},
            {'slice': np.s_[15:23, 18:28], 'mask': small, 'area_px': 80,
             'cx': 22.5, 'cy': 18.5, 'polarity': 'escuro'},
            {'slice': np.s_[10:30, 52:92], 'mask': large, 'area_px': 800,
             'cx': 71.5, 'cy': 19.5, 'polarity': 'escuro'},
        ]
        merged, count = InsertoDetector.merge_overlapping_fragments(objects)
        self.assertEqual((count, len(merged)), (1, 2))
        self.assertEqual(merged[0]['area_px'], 800)

    def test_detector_em_formas_nao_circulares(self):
        yy, xx = np.mgrid[:220, :260]
        image = (2200 + 0.4 * xx + 0.2 * yy).astype(np.float32)
        reference = np.zeros(image.shape, dtype=np.int32)
        reference[25:65, 20:82] = 1              # retângulo
        reference[105:172, 25:42] = 2            # barra
        reference[145:185, 135:205] = 3          # L: duas barras
        reference[110:185, 135:155] = 3
        image[reference > 0] -= 500
        objects, labels = InsertoDetector(sensitivity=2.0).detect(image.astype(np.uint16), np.ones_like(reference, dtype=bool))
        metricas = evaluate_instances(labels, reference, iou_threshold=0.5)
        self.assertGreaterEqual(metricas['true_positives'], 3)

    def test_formas_nao_circulares_e_associacao(self):
        referencia = np.zeros((80, 100), dtype=np.int32)
        referencia[5:20, 7:36] = 1              # retângulo
        referencia[35:62, 10:17] = 2            # barra estreita
        referencia[40:65, 55:82] = 3            # forma em L
        referencia[40:52, 55:64] = 0
        previsto = referencia.copy()
        previsto[70:76, 80:90] = 4              # falso positivo
        metricas = evaluate_instances(previsto, referencia, iou_threshold=0.5)
        self.assertEqual(metricas['true_positives'], 3)
        self.assertEqual(metricas['false_positives'], 1)
        self.assertEqual(metricas['false_negatives'], 0)
        self.assertAlmostEqual(metricas['recall'], 1.0)

    def test_falha_de_deteccao_e_iou(self):
        referencia = np.zeros((30, 30), dtype=np.int32)
        referencia[2:12, 2:12] = 1
        referencia[16:26, 16:26] = 2
        previsto = np.zeros_like(referencia)
        previsto[2:12, 2:12] = 7
        metricas = evaluate_instances(previsto, referencia, iou_threshold=0.5)
        self.assertEqual((metricas['true_positives'], metricas['false_positives'], metricas['false_negatives']), (1, 0, 1))
        self.assertAlmostEqual(metricas['mean_iou_matches'], 1.0)
        self.assertAlmostEqual(metricas['erro_centroide_medio_px'], 0.0)

    def test_erro_de_centroide_e_estado_inconclusivo(self):
        reference = np.zeros((20, 20), dtype=np.int32)
        predicted = np.zeros_like(reference)
        reference[2:8, 2:8] = 1
        predicted[5:11, 6:12] = 1
        metrics = evaluate_instances(predicted, reference, iou_threshold=0.05)
        self.assertEqual(metrics['true_positives'], 1)
        self.assertAlmostEqual(metrics['erro_centroide_medio_px'], 5.0)
        self.assertAlmostEqual(metrics['matches'][0]['erro_centroide_px'], 5.0)
        self.assertEqual(image_quality([])['estado'], 'inconclusiva')
        self.assertEqual(image_quality([{'quality_flags': ['contraste_local_baixo']}])['estado'],
                         'inconclusiva')
        self.assertEqual(image_quality([{'quality_flags': []}])['estado'], 'provisoria')
        mostly_flagged = [{'quality_flags': ['contraste_local_baixo']}] * 9 + [
            {'quality_flags': []}]
        self.assertEqual(image_quality(mostly_flagged)['estado'], 'inconclusiva')

    def test_referencia_manual_em_branco_versionada(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            dicom = root / 'imagem.dcm'
            dicom.write_bytes(b'arquivo de teste')
            labels = np.zeros((12, 15), dtype=np.int32)
            labels[2:5, 3:7] = 1
            bbox = np.array([0, 0, 12, 15])
            first = salvar_referencia_manual(labels, bbox, dicom, root / 'referencias')
            second = salvar_referencia_manual(labels, bbox, dicom, root / 'referencias')
            self.assertNotEqual(first, second)
            with np.load(first, allow_pickle=False) as data:
                self.assertTrue(np.array_equal(data['labels'], labels))
                self.assertTrue(np.array_equal(data['crop_bbox_yxwh'], bbox))
            self.assertIn('anotacao_manual_iniciada_em_branco', first.with_suffix('.json').read_text())
            with self.assertRaises(ValueError):
                salvar_referencia_manual(np.zeros_like(labels), bbox, dicom,
                                         root / 'referencias')

    def test_mapa_fisico_separado_e_vinculado_ao_csv(self):
        with tempfile.TemporaryDirectory() as folder:
            run = Path(folder)
            source = ('region_id,centro_x_imagem_px,centro_y_imagem_px,area_px,'
                      'sinal_bruto,sinal_corrigido,rsr,rcr,alertas\n'
                      'R001,10,20,50,100,110,10,2,\n'
                      'R002,30,40,60,90,95,9,1,contraste_local_baixo\n')
            (run / 'resultados.csv').write_text(source, encoding='utf-8')
            (run / 'resultados.json').write_text('{"dicom":"imagem.dcm"}', encoding='utf-8')
            assignments = {'R001': {'classe': 'inserto', 'profundidade_mm': '7,5'},
                           'R002': {'classe': 'artefato', 'profundidade_mm': ''}}
            first, data = save_mapping(run, assignments, 'conferir')
            second, _ = save_mapping(run, assignments, 'conferir')
            self.assertNotEqual(first, second)
            self.assertEqual(data['entries'][0]['profundidade_mm'], 7.5)
            self.assertEqual(data['entries'][1]['classe'], 'artefato')
            self.assertEqual(load_current_map(run)['contagem']['inserto'], 1)
            with self.assertRaises(ValueError):
                save_mapping(run, {'R001': assignments['R001']})
            (run / 'resultados.csv').write_text(source.replace(',100,110,', ',101,110,'), encoding='utf-8')
            with self.assertRaises(ValueError):
                load_current_map(run)

    def test_profundidades_acompanham_rotulos_na_revisao(self):
        with tempfile.TemporaryDirectory() as folder:
            run = Path(folder) / '001_Mão46_1'
            revision = run / 'revisoes' / 'revisao_001'
            revision.mkdir(parents=True)
            (revision / 'resultados.csv').write_text(
                'region_id,centro_x_imagem_px,centro_y_imagem_px,area_px,'
                'sinal_bruto,sinal_corrigido,rsr,rcr,alertas\n'
                'R001,10,20,50,100,110,10,2,\n'
                'R002,30,40,60,90,95,9,1,\n', encoding='utf-8')
            (revision / 'resultados.json').write_text(
                json.dumps({'dicom': 'Mão46_1',
                            'qualidade_analise': {'estado': 'provisoria'}}),
                encoding='utf-8')
            origins = {'R001': 7, 'R002': 3}
            (revision / 'alteracoes.json').write_text(
                json.dumps({'rotulos_origem': origins}), encoding='utf-8')
            by_source = {7: {'classe': 'inserto', 'profundidade_mm': '1,5'},
                         3: {'classe': 'inserto', 'profundidade_mm': '8'}}
            mapped = associacoes_para_revisao(origins, by_source)
            self.assertEqual(mapped['R001']['profundidade_mm'], '1,5')
            self.assertEqual(mapped['R002']['profundidade_mm'], '8')
            save_mapping(revision, mapped, 'orientação conferida pelo usuário')
            loaded, notes, source = carregar_associacoes(run, run / 'revisoes')
            self.assertEqual(source, revision)
            self.assertEqual(notes, 'orientação conferida pelo usuário')
            self.assertEqual(loaded[7]['profundidade_mm'], '1.5')
            self.assertEqual(loaded[3]['profundidade_mm'], '8.0')
            self.assertEqual(latest_measurements(run), revision)
            (Path(folder) / 'resumo_lote.json').write_text(json.dumps([
                {'arquivo': 'Mão46_1', 'diretorio': str(run), 'status': 'concluido'}
            ]), encoding='utf-8')
            datasets, omitted = read_dataset(Path(folder))
            self.assertEqual(omitted, [])
            self.assertEqual(datasets['Mão46_1']['run_dir'], revision)
            self.assertEqual([row['depth'] for row in datasets['Mão46_1']['rows']],
                             [1.5, 8.0])
            later = run / 'revisoes' / 'revisao_002'
            later.mkdir()
            (later / 'resultados.csv').write_bytes((revision / 'resultados.csv').read_bytes())
            self.assertEqual(latest_measurements(run), later)
            datasets, omitted = read_dataset(Path(folder))
            self.assertEqual(datasets, {})
            self.assertIn('nessa versão', omitted[0][1])
            loaded, _, source = carregar_associacoes(run, run / 'revisoes')
            self.assertEqual(loaded, {})
            self.assertIsNone(source)

    def test_transferencia_espacial_protege_mapa_manual_e_imagem_inconclusiva(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            summary = []
            rows_by_exposure = {
                1: [('R001', 10, 10), ('R002', 43, 12), ('R003', 70, 55)],
                2: [('R001', 11, 11), ('R002', 44, 12)],
                4: [('R001', 10, 11), ('R002', 43, 13)],
            }
            runs = {}
            for exposure, points in rows_by_exposure.items():
                dicom = root / f'Fantoma_{exposure}'
                meta = FileMetaDataset()
                meta.MediaStorageSOPClassUID = SecondaryCaptureImageStorage
                meta.MediaStorageSOPInstanceUID = generate_uid()
                meta.TransferSyntaxUID = ExplicitVRLittleEndian
                image = FileDataset(str(dicom), {}, file_meta=meta,
                                    preamble=b'\0' * 128)
                image.Rows = 100; image.Columns = 100
                image.save_as(dicom)
                run = root / f'{exposure:03d}_Fantoma_{exposure}'
                run.mkdir(); runs[exposure] = run
                header = ('region_id,centro_x_imagem_px,centro_y_imagem_px,area_px,'
                          'sinal_bruto,sinal_corrigido,rsr,rcr,alertas\n')
                alert = 'contraste_local_baixo' if exposure == 4 else ''
                lines = [f'{id_},{x},{y},50,100,110,10,2,{alert}\n'
                         for id_, x, y in points]
                (run / 'resultados.csv').write_text(header + ''.join(lines), encoding='utf-8')
                (run / 'resultados.json').write_text(
                    json.dumps({'dicom': str(dicom),
                                'qualidade_analise': {'estado': 'provisoria'}}),
                    encoding='utf-8')
                summary.append({'arquivo': str(dicom), 'diretorio': str(run),
                                'status': 'concluido'})
            (root / 'resumo_lote.json').write_text(json.dumps(summary), encoding='utf-8')
            assignments = {'R001': {'classe': 'inserto', 'profundidade_mm': '1'},
                           'R002': {'classe': 'inserto', 'profundidade_mm': '2'},
                           'R003': {'classe': 'artefato', 'profundidade_mm': ''}}
            save_mapping(runs[1], assignments)
            matches, limit = match_positions(read_rows(runs[1]), read_rows(runs[2]))
            self.assertEqual(len(matches), 2)
            self.assertLessEqual(max(distance for _, _, distance in matches), limit)
            report = transfer_group(runs[1], runs[1])
            self.assertEqual(report['alvos'][0]['estado'], 'preenchido')
            self.assertEqual(report['alvos'][1]['motivo'], 'análise inconclusiva')
            transferred = load_current_map(runs[2])
            self.assertEqual(transferred['contagem']['inserto'], 2)
            self.assertTrue(transferred['proveniencia_transferencia']
                            ['conferencia_visual_pendente'])
            manual = {entry['region_id']:
                      {'classe': entry['classe'], 'profundidade_mm': entry['profundidade_mm']}
                      for entry in transferred['entries']}
            save_mapping(runs[2], manual, 'conferido manualmente')
            again = transfer_group(runs[1], runs[1])
            self.assertEqual(again['alvos'][0]['motivo'], 'mapa já editado pelo usuário')


if __name__ == '__main__':
    unittest.main()
