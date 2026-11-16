"""Janela simples para executar lote e revisar máscaras sem terminal."""
import json
import queue
import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Interface:
    def __init__(self, root):
        self.root = root
        self.files = []
        self.events = queue.Queue()
        self.output = tk.StringVar(value=str(PROJECT_ROOT / 'resultados' / 'lote'))
        self.sensitivity = tk.StringVar(value='1.5')
        root.title('Análise de fantomas DICOM')
        root.geometry('1100x670')
        controls = tk.Frame(root); controls.pack(fill='x', padx=12, pady=8)
        tk.Button(controls, text='Adicionar DICOMs', command=self.add_files).grid(row=0, column=0)
        tk.Button(controls, text='Adicionar pasta', command=self.add_folder).grid(row=0, column=1)
        tk.Button(controls, text='Limpar lista', command=self.clear).grid(row=0, column=2)
        tk.Label(controls, text='Sensibilidade').grid(row=1, column=0, sticky='w')
        tk.Entry(controls, textvariable=self.sensitivity, width=8).grid(row=1, column=1, sticky='w')
        tk.Label(controls, text='Saída').grid(row=2, column=0, sticky='w')
        tk.Entry(controls, textvariable=self.output, width=62).grid(row=2, column=1, columnspan=2)
        tk.Button(controls, text='Escolher', command=self.choose_output).grid(row=2, column=3)
        self.run_button = tk.Button(controls, text='Processar todos', command=self.run)
        self.run_button.grid(row=3, column=0, pady=8)
        tk.Button(controls, text='Revisar máscara e profundidade', command=self.review).grid(row=3, column=1)
        tk.Button(controls, text='Abrir relatório', command=self.open_report).grid(row=3, column=2)
        tk.Button(controls, text='Anotar referência', command=self.annotate_reference).grid(row=3, column=3)
        tk.Button(controls, text='Gerar curvas do lote', command=self.generate_depth_curves).grid(row=4, column=0, pady=4)
        tk.Button(controls, text='Abrir lote existente', command=self.open_existing_batch).grid(row=4, column=1, pady=4)
        tk.Label(root, text='Selecione um resultado e clique em Revisar máscara e profundidade.').pack()
        self.listbox = tk.Listbox(root, height=18, width=100)
        self.listbox.pack(fill='both', expand=True, padx=12, pady=8)
        self.status = tk.StringVar(value='Adicione arquivos ou uma pasta com DICOMs.')
        tk.Label(root, textvariable=self.status, anchor='w').pack(fill='x', padx=12)
        root.after(200, self.poll)

    def add_files(self):
        for filename in filedialog.askopenfilenames(title='Selecione DICOMs'):
            self.append(Path(filename))

    def add_folder(self):
        directory = filedialog.askdirectory(title='Pasta de DICOMs')
        if directory:
            for path in sorted(Path(directory).iterdir()):
                if path.is_file():
                    self.append(path)

    def append(self, path):
        path = path.resolve()
        if path not in self.files:
            self.files.append(path); self.listbox.insert('end', path.name)

    def clear(self):
        self.files.clear(); self.listbox.delete(0, 'end')

    def choose_output(self):
        directory = filedialog.askdirectory(title='Diretório de saída')
        if directory:
            self.output.set(directory)

    def run(self):
        if not self.files:
            messagebox.showerror('Sem arquivos', 'Selecione ao menos um DICOM.'); return
        try:
            sensitivity = float(self.sensitivity.get())
            if sensitivity <= 0:
                raise ValueError()
        except ValueError:
            messagebox.showerror('Sensibilidade', 'Informe um número positivo.'); return
        self.run_button.configure(state='disabled')
        output = Path(self.output.get()).resolve()
        if output.exists() and any(output.iterdir()):
            output = output.parent / f'{output.name}_{datetime.now():%Y%m%d_%H%M%S}'
        files = list(self.files)
        self.batch_output = output
        self.status.set(f'Processando {len(files)} arquivo(s)...')
        def worker():
            cmd = [sys.executable, '-m', 'radio2.processar_lote',
                   *map(str, files), '--output-dir', str(output),
                   '--sensibilidade', str(sensitivity)]
            proc = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True)
            self.events.put(('done', output, proc))
        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        try:
            while True:
                kind, output, proc = self.events.get_nowait()
                if kind == 'done':
                    self.run_button.configure(state='normal')
                    summary = output / 'resumo_lote.json'
                    if summary.exists():
                        rows = json.loads(summary.read_text(encoding='utf-8'))
                        self.display_batch(rows, summary)
                    else:
                        messagebox.showerror('Falha no lote', proc.stderr or proc.stdout)
                elif kind == 'curves':
                    page = output / 'index.html'
                    if proc.returncode == 0 and page.is_file():
                        self.status.set(f'Curvas por profundidade informada: {page}')
                        webbrowser.open(page.resolve().as_uri())
                    else:
                        messagebox.showerror('Falha nas curvas', proc.stderr or proc.stdout)
        except queue.Empty:
            pass
        self.root.after(200, self.poll)

    def display_batch(self, rows, summary):
        self.listbox.delete(0, 'end')
        for row in rows:
            quality = row.get('qualidade_analise', 'não avaliada')
            self.listbox.insert('end', f'{Path(row["arquivo"]).name}: '
                                       f'{row["status"]} — {row["regioes"]} regiões, '
                                       f'{row["regioes_com_alerta"]} alertas; '
                                       f'análise {quality}')
        self.rows = rows
        self.batch_output = summary.parent
        self.status.set(f'{sum(r["status"] == "concluido" for r in rows)}/{len(rows)} '
                        f'execuções concluídas. Resumo: {summary}')

    def open_existing_batch(self):
        folder = filedialog.askdirectory(title='Selecione uma pasta de lote com resumo_lote.json')
        if not folder:
            return
        summary = Path(folder) / 'resumo_lote.json'
        if not summary.is_file():
            messagebox.showerror('Lote', 'A pasta não contém resumo_lote.json.'); return
        try:
            rows = json.loads(summary.read_text(encoding='utf-8'))
            if not isinstance(rows, list):
                raise ValueError('Resumo do lote inválido.')
        except (OSError, ValueError) as exc:
            messagebox.showerror('Lote', str(exc)); return
        self.display_batch(rows, summary)

    def review(self):
        selection = self.listbox.curselection()
        if not selection or not hasattr(self, 'rows'):
            messagebox.showinfo('Seleção', 'Processe o lote e selecione um resultado.'); return
        row = self.rows[selection[0]]
        if row['status'] != 'concluido':
            messagebox.showerror('Falha', row['detalhe']); return
        folder = Path(row['diretorio'])
        subprocess.Popen([sys.executable, '-m', 'radio2.editor_mascaras',
                          row['arquivo'], str(folder), str(folder / 'revisoes')],
                         cwd=PROJECT_ROOT)

    def open_report(self):
        selection = self.listbox.curselection()
        if not selection or not hasattr(self, 'rows'):
            messagebox.showinfo('Seleção', 'Processe o lote e selecione um resultado.'); return
        row = self.rows[selection[0]]
        if row['status'] != 'concluido':
            messagebox.showerror('Falha', row['detalhe']); return
        report = Path(row['diretorio']) / f'relatorio_{Path(row["arquivo"]).stem}.html'
        if not report.is_file():
            messagebox.showinfo('Relatório ausente', 'Este lote foi criado antes da geração automática de relatórios.')
            return
        webbrowser.open(report.resolve().as_uri())

    def annotate_reference(self):
        selection = self.listbox.curselection()
        if not selection:
            messagebox.showinfo('Seleção', 'Selecione um DICOM na lista.'); return
        index = selection[0]
        if hasattr(self, 'rows') and index < len(self.rows):
            dicom = Path(self.rows[index]['arquivo'])
        elif index < len(self.files):
            dicom = self.files[index]
        else:
            messagebox.showerror('Seleção', 'Arquivo não encontrado na lista.'); return
        destination = PROJECT_ROOT / 'referencias' / dicom.stem
        subprocess.Popen([sys.executable, '-m', 'radio2.anotar_referencia',
                          str(dicom), str(destination)], cwd=PROJECT_ROOT)

    def generate_depth_curves(self):
        if not hasattr(self, 'batch_output') or not (self.batch_output / 'resumo_lote.json').is_file():
            messagebox.showinfo('Lote', 'Processe um lote nesta janela antes de gerar as curvas.'); return
        output = self.batch_output / 'curvas_fisicas'
        self.status.set('Gerando curvas com as profundidades já informadas...')
        def worker():
            cmd = [sys.executable, '-m', 'radio2.gerar_curvas_fisicas_lote',
                   '--lote', str(self.batch_output), '--saida', str(output)]
            proc = subprocess.run(cmd, cwd=PROJECT_ROOT, capture_output=True, text=True)
            self.events.put(('curves', output, proc))
        threading.Thread(target=worker, daemon=True).start()


def main():
    root = tk.Tk()
    Interface(root)
    root.mainloop()


if __name__ == '__main__':
    main()
