"""Editor local de rótulos; salva cópia revisada e recalcula as medidas."""
import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

import cv2
import numpy as np
import pydicom
from PIL import Image, ImageTk
from scipy import ndimage as ndi

from .mapear_profundidades import (CLASSES, generate_single_curves, load_current_map,
                                    normalize_assignment, save_mapping)
from .quantificar_mascaras import quantificar
from .transferir_profundidades import transfer_group


def salvar_referencia_manual(labels, bbox, dicom, saida):
    """Versiona uma anotação iniciada em branco; nunca usa máscara automática."""
    labels = np.asarray(labels)
    bbox = np.asarray(bbox)
    if labels.ndim != 2 or not np.issubdtype(labels.dtype, np.integer) or np.any(labels < 0):
        raise ValueError('A referência deve ser uma matriz 2D de rótulos não negativos.')
    if bbox.shape != (4,) or tuple(map(int, bbox[2:])) != labels.shape:
        raise ValueError('Dimensões da referência e da imagem não coincidem.')
    if not np.any(labels > 0):
        raise ValueError('Pinte ao menos uma região antes de salvar a referência.')
    dicom = Path(dicom)
    saida = Path(saida)
    saida.mkdir(parents=True, exist_ok=True)
    version = 1
    while (saida / f'referencia_manual_{version:03d}.npz').exists():
        version += 1
    target = saida / f'referencia_manual_{version:03d}.npz'
    np.savez_compressed(target, labels=labels.astype(np.int32),
                        crop_bbox_yxwh=bbox.astype(np.int32))
    sha = hashlib.sha256()
    with dicom.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            sha.update(chunk)
    metadata = {
        'origem': 'anotacao_manual_iniciada_em_branco',
        'status': 'pendente_de_conferencia_independente',
        'dicom': str(dicom.resolve()), 'dicom_sha256': sha.hexdigest(),
        'data_local': datetime.now().isoformat(timespec='seconds'),
        'rotulos': int(np.count_nonzero(np.unique(labels))),
        'pixels_anotados': int(np.count_nonzero(labels)),
        'nota': 'A anotação não prova por si só que os contornos ou profundidades estão corretos.',
    }
    target.with_suffix('.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2),
                                          encoding='utf-8')
    return target


def carregar_associacoes(automatico, saida):
    """Recupera profundidades pela etiqueta original, mesmo após renumeração."""
    automatico, saida = Path(automatico), Path(saida)
    revisions = sorted((p for p in saida.glob('revisao_*')
                        if p.is_dir() and (p / 'resultados.csv').is_file()),
                       reverse=True)
    folder = revisions[0] if revisions else automatico
    mapping = load_current_map(folder)
    if mapping is not None:
        if folder == automatico:
            origins = {entry['region_id']: int(entry['region_id'][1:])
                       for entry in mapping['entries']}
        else:
            changes = json.loads((folder / 'alteracoes.json').read_text(encoding='utf-8'))
            origins = {key: int(value) for key, value in changes['rotulos_origem'].items()}
        assignments = {origins[entry['region_id']]:
                       {'classe': entry['classe'],
                        'profundidade_mm': '' if entry['profundidade_mm'] is None else
                        str(entry['profundidade_mm'])}
                       for entry in mapping['entries'] if entry['region_id'] in origins}
        return assignments, mapping.get('observacoes', ''), folder
    return {}, '', None


def associacoes_para_revisao(rotulos_origem, assignments):
    """Relaciona cada ID recalculado ao rótulo editado selecionado na tela."""
    return {region_id: assignments.get(int(source_label),
            {'classe': CLASSES[0], 'profundidade_mm': ''})
            for region_id, source_label in rotulos_origem.items()}


class Editor:
    def __init__(self, root, dicom, automatico, saida):
        self.root, self.dicom, self.automatico, self.saida = root, dicom, automatico, saida
        self.reference_mode = automatico is None
        raw = pydicom.dcmread(dicom).pixel_array
        if raw.ndim != 2:
            raise ValueError('A anotação requer um DICOM 2D.')
        if self.reference_mode:
            self.labels = np.zeros(raw.shape, dtype=np.int32)
            self.bbox = np.array([0, 0, *raw.shape], dtype=np.int32)
        else:
            with np.load(automatico / 'mascaras.npz', allow_pickle=False) as archive:
                self.labels = archive['labels'].copy()
                self.bbox = archive['crop_bbox_yxwh'].copy()
        y, x, h, w = map(int, self.bbox)
        self.crop = raw[y:y+h, x:x+w]
        lo, hi = np.percentile(self.crop, (1, 99))
        self.gray = np.uint8(np.clip((self.crop.astype(np.float32)-lo) * 255 / max(hi-lo, 1), 0, 255))
        available = np.unique(self.labels[self.labels > 0])
        self.selected = int(available[0]) if available.size else 1
        self.brush = 5
        self.zoom = 0.8
        self.mode = 'paint'
        self.undo = []
        self.last = None
        self.dirty = False
        self.metadata_dirty = False
        self.assignments = {}
        self.map_source = None
        self.loaded_map = None
        self.notes_initial = ''
        if not self.reference_mode:
            try:
                self.assignments, self.notes_initial, self.map_source = carregar_associacoes(
                    automatico, saida)
                if self.map_source is not None:
                    self.loaded_map = load_current_map(self.map_source)
            except (ValueError, KeyError, OSError) as exc:
                messagebox.showwarning('Mapa anterior incompatível', str(exc))
        root.title(f'{"Referência manual em branco" if self.reference_mode else "Revisão de máscaras"} — {dicom.name}')
        root.geometry('1200x740' if not self.reference_mode else '1100x740')
        bar = tk.Frame(root); bar.pack(fill='x')
        self.info = tk.StringVar()
        tk.Label(bar, textvariable=self.info).pack(side='left', padx=8)
        for title, action in [('Novo objeto (N)', self.new_label), ('Desfazer (Z)', self.undo_last),
                              ('Zoom +', lambda: self.set_zoom(1.25)),
                              ('Zoom -', lambda: self.set_zoom(0.8)),
                              (('Salvar referência (S)' if self.reference_mode else 'Salvar e recalcular (S)'), self.save)]:
            tk.Button(bar, text=title, command=action).pack(side='left')
        tk.Label(root, text='Clique direito: selecionar objeto | Clique e arraste esquerdo: pintar | '
                            'Clique e arraste com Shift: apagar | [ e ]: pincel | Esc: sair').pack()
        frame = tk.Frame(root); frame.pack(fill='both', expand=True)
        self.canvas = tk.Canvas(frame, width=1050 if self.reference_mode else 850,
                                height=650, bg='#202020')
        sx = tk.Scrollbar(frame, orient='horizontal', command=self.canvas.xview)
        sy = tk.Scrollbar(frame, orient='vertical', command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=sx.set, yscrollcommand=sy.set)
        self.canvas.grid(row=0, column=0, sticky='nsew'); sy.grid(row=0, column=1, sticky='ns')
        sx.grid(row=1, column=0, sticky='ew')
        frame.rowconfigure(0, weight=1); frame.columnconfigure(0, weight=1)
        if not self.reference_mode:
            panel = tk.Frame(frame, padx=12, pady=8)
            panel.grid(row=0, column=2, sticky='nsew')
            tk.Label(panel, text='Profundidade do objeto selecionado',
                     font=('TkDefaultFont', 11, 'bold')).pack(anchor='w')
            tk.Label(panel, text='Clique com o botão direito no objeto ou selecione na lista. '
                                 'A profundidade informada não participa da detecção.',
                     wraplength=290, justify='left').pack(anchor='w', pady=5)
            if self.loaded_map and self.loaded_map.get('origem', '').startswith('transferencia_'):
                tk.Label(panel, text='Sugestões transferidas de outra exposição. '
                                     'Confira as posições antes de interpretar as curvas.',
                         fg='#9b4d00', wraplength=290, justify='left').pack(anchor='w')
            self.selected_text = tk.StringVar()
            tk.Label(panel, textvariable=self.selected_text,
                     font=('TkDefaultFont', 13, 'bold')).pack(anchor='w', pady=8)
            tk.Label(panel, text='Classe').pack(anchor='w')
            self.class_var = tk.StringVar()
            ttk.Combobox(panel, textvariable=self.class_var, values=CLASSES,
                         state='readonly', width=22).pack(anchor='w', fill='x')
            tk.Label(panel, text='Profundidade física (mm)').pack(anchor='w', pady=(8, 0))
            self.depth_var = tk.StringVar()
            tk.Entry(panel, textvariable=self.depth_var).pack(anchor='w', fill='x')
            tk.Label(panel, text='Objetos nesta máscara').pack(anchor='w', pady=(10, 0))
            self.object_list = tk.Listbox(panel, height=18, width=36)
            self.object_list.pack(fill='both', expand=True)
            self.object_list.bind('<<ListboxSelect>>', self.select_from_list)
            tk.Label(panel, text='Observações / orientação').pack(anchor='w', pady=(8, 0))
            self.notes = tk.Text(panel, height=3, width=34)
            self.notes.pack(fill='x')
            self.notes.insert('1.0', self.notes_initial)
            self.class_var.trace_add('write', self.assignment_changed)
            self.depth_var.trace_add('write', self.depth_changed)
            self.loading_fields = False
        self.canvas.bind('<ButtonPress-1>', self.start_paint)
        self.canvas.bind('<B1-Motion>', self.paint)
        self.canvas.bind('<ButtonRelease-1>', self.end_paint)
        self.canvas.bind('<Button-3>', self.pick)
        root.bind('n', lambda event: self.shortcut(event, self.new_label))
        root.bind('z', lambda event: self.shortcut(event, self.undo_last))
        root.bind('s', lambda event: self.shortcut(event, self.save))
        root.bind('bracketleft', lambda event: self.shortcut(event, lambda: self.set_brush(-2)))
        root.bind('bracketright', lambda event: self.shortcut(event, lambda: self.set_brush(2)))
        root.bind('<Escape>', lambda _: self.close())
        root.protocol('WM_DELETE_WINDOW', self.close)
        self.centers = {}
        self.update_centers()
        if not self.reference_mode:
            self.load_selected_fields()
            self.update_object_list()
        self.refresh()

    @staticmethod
    def shortcut(event, action):
        if not isinstance(event.widget, (tk.Entry, tk.Text, ttk.Combobox)):
            action()

    def coords(self, event):
        x = int(self.canvas.canvasx(event.x) / self.zoom)
        y = int(self.canvas.canvasy(event.y) / self.zoom)
        return max(0, min(self.labels.shape[1]-1, x)), max(0, min(self.labels.shape[0]-1, y))

    def update_centers(self):
        ids = [int(value) for value in np.unique(self.labels) if value > 0]
        if not ids:
            self.centers = {}
            return
        points = ndi.center_of_mass(np.ones(self.labels.shape, dtype=np.uint8),
                                    self.labels, ids)
        self.centers = {id_: (int(round(x)), int(round(y)))
                        for id_, (y, x) in zip(ids, points)}

    def load_selected_fields(self):
        if self.reference_mode:
            return
        item = self.assignments.get(self.selected, {})
        self.loading_fields = True
        self.class_var.set(item.get('classe', CLASSES[0]))
        self.depth_var.set(item.get('profundidade_mm', ''))
        self.loading_fields = False
        self.selected_text.set(f'Rótulo {self.selected}')

    def assignment_changed(self, *_):
        if getattr(self, 'loading_fields', True):
            return
        self.assignments[self.selected] = {'classe': self.class_var.get(),
                                           'profundidade_mm': self.depth_var.get()}
        self.metadata_dirty = True
        self.update_object_list()

    def depth_changed(self, *_):
        if getattr(self, 'loading_fields', True):
            return
        if self.depth_var.get().strip() and self.class_var.get() == CLASSES[0]:
            self.class_var.set('inserto')
        else:
            self.assignment_changed()

    def update_object_list(self):
        if self.reference_mode:
            return
        self.list_updating = True
        self.list_ids = sorted(set(self.centers) | {self.selected})
        self.object_list.delete(0, 'end')
        for id_ in self.list_ids:
            item = self.assignments.get(id_, {})
            kind = item.get('classe', CLASSES[0])
            depth = item.get('profundidade_mm', '').strip()
            detail = f'{depth} mm' if kind == 'inserto' and depth else kind
            self.object_list.insert('end', f'Rótulo {id_:>3}  —  {detail}')
        self.object_list.selection_set(self.list_ids.index(self.selected))
        self.object_list.see(self.list_ids.index(self.selected))
        self.list_updating = False

    def select_label(self, id_, center=False):
        self.selected = int(id_)
        self.load_selected_fields()
        self.update_object_list()
        self.refresh()
        if center and id_ in self.centers:
            x, y = self.centers[id_]
            width = max(1, self.labels.shape[1] * self.zoom)
            height = max(1, self.labels.shape[0] * self.zoom)
            self.canvas.xview_moveto(max(0, min(1, (x * self.zoom - self.canvas.winfo_width()/2) / width)))
            self.canvas.yview_moveto(max(0, min(1, (y * self.zoom - self.canvas.winfo_height()/2) / height)))

    def select_from_list(self, _event):
        if getattr(self, 'list_updating', False):
            return
        selection = self.object_list.curselection()
        if selection:
            id_ = self.list_ids[selection[0]]
            if id_ != self.selected:
                self.select_label(id_, center=True)

    def refresh(self):
        rgb = cv2.cvtColor(self.gray, cv2.COLOR_GRAY2RGB)
        selected = self.labels == self.selected
        rgb[selected] = (0.45 * rgb[selected] + 0.55 * np.array([255, 215, 0])).astype(np.uint8)
        edges = cv2.morphologyEx(np.uint8(self.labels > 0), cv2.MORPH_GRADIENT,
                                 np.ones((3, 3), np.uint8)) > 0
        rgb[edges] = (255, 45, 45)
        for id_, (x, y) in self.centers.items():
            title = str(id_)
            cv2.putText(rgb, title, (x-9, y+6), cv2.FONT_HERSHEY_SIMPLEX, .62,
                        (0, 0, 0), 4, cv2.LINE_AA)
            cv2.putText(rgb, title, (x-9, y+6), cv2.FONT_HERSHEY_SIMPLEX, .62,
                        (255, 230, 70) if id_ == self.selected else (255, 255, 255),
                        2, cv2.LINE_AA)
        image = Image.fromarray(rgb)
        size = (max(1, int(image.width * self.zoom)), max(1, int(image.height * self.zoom)))
        self.photo = ImageTk.PhotoImage(image.resize(size, Image.Resampling.NEAREST))
        self.canvas.delete('all'); self.canvas.create_image(0, 0, image=self.photo, anchor='nw')
        self.canvas.configure(scrollregion=(0, 0, *size))
        self.info.set(f'Rótulo {self.selected} | Pincel {self.brush}px | Zoom {self.zoom:.2f}x | '
                      f'{"máscara alterada" if self.dirty else "máscara sem alterações"}')

    def start_paint(self, event):
        self.undo.append(self.labels.copy())
        if len(self.undo) > 8:
            self.undo.pop(0)
        self.mode = 'erase' if event.state & 0x0001 else 'paint'
        self.last = self.coords(event)
        cv2.circle(self.labels, self.last, self.brush, 0 if self.mode == 'erase' else self.selected, -1)
        self.dirty = True
        self.refresh()

    def paint(self, event):
        current = self.coords(event)
        cv2.line(self.labels, self.last, current,
                 0 if self.mode == 'erase' else self.selected, thickness=2*self.brush+1)
        self.last = current
        self.refresh()

    def end_paint(self, event):
        self.last = None
        self.update_centers()
        self.update_object_list()
        self.refresh()

    def pick(self, event):
        x, y = self.coords(event)
        if self.labels[y, x] > 0:
            self.select_label(int(self.labels[y, x]))

    def new_label(self):
        self.select_label(int(self.labels.max()) + 1)

    def undo_last(self):
        if self.undo:
            self.labels = self.undo.pop(); self.dirty = True
            self.update_centers(); self.update_object_list(); self.refresh()

    def set_zoom(self, factor):
        self.zoom = float(np.clip(self.zoom * factor, 0.25, 4.0)); self.refresh()

    def set_brush(self, increment):
        self.brush = max(1, min(100, self.brush + increment)); self.refresh()

    def save(self):
        if self.reference_mode:
            try:
                target = salvar_referencia_manual(self.labels, self.bbox,
                                                  self.dicom, self.saida)
            except Exception as exc:
                messagebox.showerror('Falha ao salvar referência', str(exc)); return
            self.dirty = False; self.refresh()
            messagebox.showinfo('Referência salva', f'Anotação salva em:\n{target}\n'
                                'Confirme todos os contornos antes de usá-la na avaliação.')
            return
        present = {int(id_) for id_ in np.unique(self.labels) if id_ > 0}
        notes = self.notes.get('1.0', 'end').strip()
        try:
            for id_ in present:
                item = self.assignments.get(id_, {})
                normalize_assignment(item.get('classe', CLASSES[0]),
                                     item.get('profundidade_mm', ''), f'rótulo {id_}')
        except ValueError as exc:
            messagebox.showerror('Profundidade inválida', str(exc)); return
        self.saida.mkdir(parents=True, exist_ok=True)
        version = 1
        while (self.saida / f'mascara_editada_{version:03d}.npz').exists():
            version += 1
        target = self.saida / f'mascara_editada_{version:03d}.npz'
        result = self.saida / f'revisao_{version:03d}'
        np.savez_compressed(target, labels=self.labels.astype(np.int32), crop_bbox_yxwh=self.bbox)
        try:
            changes = quantificar(self.dicom, self.automatico, target, result)
        except Exception as exc:
            target.unlink(missing_ok=True)
            messagebox.showerror('Falha ao recalcular', str(exc)); return
        map_message = 'Sem profundidades informadas.'
        mapped = bool(present) and (self.map_source is not None or bool(notes) or
                  any(self.assignments.get(id_, {}).get('classe', CLASSES[0]) != CLASSES[0]
                      for id_ in present))
        if mapped:
            assignments = associacoes_para_revisao(changes['rotulos_origem'],
                                                   self.assignments)
            try:
                origin = 'associacao_fisica_informada_pelo_usuario'
                provenance = None
                if self.loaded_map and self.loaded_map.get('origem', '').startswith('transferencia_'):
                    origin = (self.loaded_map['origem'] if not self.metadata_dirty and
                              notes == self.notes_initial else
                              'transferencia_espacial_editada_pelo_usuario')
                    provenance = self.loaded_map.get('proveniencia_transferencia')
                path, mapping = save_mapping(result, assignments, notes,
                                             origin=origin, provenance=provenance)
                curves = generate_single_curves(result) if mapping['contagem']['inserto'] else None
                self.map_source = result
                self.loaded_map = mapping
                self.notes_initial = notes
                map_message = f'Mapa: {path}\nCurvas: {curves or "sem insertos mapeados"}'
            except Exception as exc:
                messagebox.showerror('Medições salvas, mapa não salvo',
                                     f'Revisão: {result}\n{exc}')
                return
        group_message = ''
        if mapped and self.loaded_map['origem'] == 'associacao_fisica_informada_pelo_usuario':
            try:
                report = transfer_group(self.automatico, result)
                if report:
                    lines = [f"{item['imagem']}: {item.get('classes_copiadas', 0)} regiões preenchidas"
                             if item['estado'] == 'preenchido' else
                             f"{item['imagem']}: omitido ({item.get('motivo', 'sem motivo')})"
                             for item in report['alvos']]
                    if lines:
                        group_message = '\nGrupo: ' + '; '.join(lines)
            except Exception as exc:
                group_message = f'\nTransferência do grupo falhou: {exc}'
        self.dirty = False; self.refresh()
        self.metadata_dirty = False
        messagebox.showinfo('Salvo', f'Máscara e medições salvas em:\n{result}\n'
                                     f'Pixels alterados: {changes["pixels_alterados"]}\n'
                                     f'{map_message}{group_message}')

    def close(self):
        notes_changed = (not self.reference_mode and
                         self.notes.get('1.0', 'end').strip() != self.notes_initial)
        if (self.dirty or self.metadata_dirty or notes_changed) and not messagebox.askyesno(
                'Alterações não salvas', 'Descartar alterações?'):
            return
        self.root.destroy()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dicom', type=Path)
    parser.add_argument('automatico', type=Path)
    parser.add_argument('saida', type=Path)
    args = parser.parse_args()
    root = tk.Tk()
    Editor(root, args.dicom.resolve(), args.automatico.resolve(), args.saida.resolve())
    root.mainloop()


if __name__ == '__main__':
    main()
