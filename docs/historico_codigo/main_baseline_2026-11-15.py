"""Segmentacao automatica de insertos com correção de fundo local.

Adaptacao da Eq. (1) do TCC de William da Veiga:
S_corrigido = (S_ROI / S_fundo_local) * S_referencia.
Como nao ha grade ou ROI 12 conhecida, S_referencia e a mediana
dos fundos locais de todas as regioes detectadas.
Os valores brutos do DICOM permanecem intactos.

Uso:
    python3 main.py Cranio81_1
    python3 main.py imagem.dcm --sensibilidade 1.3
"""
import argparse
import os
import sys
from pathlib import Path

# Reduz o numero de threads de BLAS antes de importar NumPy/SciPy.
# Em computadores com pouca memoria evita picos de RAM.
os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['OMP_NUM_THREADS'] = '1'
os.environ['MKL_NUM_THREADS'] = '1'

import cv2
import numpy as np
import pydicom
from scipy import ndimage as ndi

cv2.setNumThreads(1)


class DicomReader:
    @staticmethod
    def resolve(filename):
        request = Path(filename).expanduser()
        candidates = [request, Path('dicom') / request]
        if not request.suffix:
            candidates.extend([Path(str(p) + '.dcm') for p in candidates])
        for path in candidates:
            if path.is_file():
                return path
        raise FileNotFoundError(f"Arquivo '{filename}' nao encontrado (nem na pasta dicom/).")

    @staticmethod
    def read(path):
        ds = pydicom.dcmread(str(path))
        raw = ds.pixel_array
        if raw.ndim != 2:
            raise ValueError(f'Esperada imagem DICOM 2D; encontrada {raw.shape}.')
        print(f'\nArquivo: {path.name} | Dimensoes: {raw.shape} | Tipo: {raw.dtype}')
        print(f'Pixel minimo: {raw.min()} | Pixel maximo: {raw.max()}')
        return ds, raw


class PhantomSegmenter:
    """Preserva o algoritmo previamente validado para recortar o fantoma."""
    def detect(self, pixels):
        H, W = pixels.shape
        image = pixels.astype(np.float32)
        low, high = np.percentile(image, [1, 99])
        if high <= low:
            raise RuntimeError('Imagem sem variacao de intensidade.')
        norm = np.uint8(np.clip((image - low) * 255 / (high - low), 0, 255))
        blur = cv2.GaussianBlur(norm, (5, 5), 0)
        close_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15))
        open_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        options = []
        for p in (20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 85):
            value = int(np.percentile(blur, p))
            for polarity in (cv2.THRESH_BINARY, cv2.THRESH_BINARY_INV):
                _, binary = cv2.threshold(blur, value, 255, polarity)
                binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, close_kernel, iterations=2)
                binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, open_kernel)
                contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                for contour in contours:
                    area = cv2.contourArea(contour)
                    if area < 0.03 * H * W:
                        continue
                    x, y, w, h = cv2.boundingRect(contour)
                    if x <= 2 or y <= 2 or x + w >= W - 2 or y + h >= H - 2:
                        continue
                    portion = w * h / (H * W)
                    if not 0.04 <= portion <= 0.90 or not 0.45 <= w / h <= 2.20:
                        continue
                    rectangle = area / (w * h)
                    if rectangle < 0.12:
                        continue
                    options.append((portion**0.5 * rectangle, (x, y, w, h)))
        if not options:
            raise RuntimeError('Nao foi possivel localizar a regiao externa do fantoma.')
        x, y, w, h = max(options, key=lambda item: item[0])[1]
        mx, my = max(2, int(0.012 * w)), max(2, int(0.012 * h))
        mask = np.zeros((h, w), dtype=bool)
        mask[my:h-my, mx:w-mx] = True
        print(f'Fantoma: x={x}, y={y}, largura={w}, altura={h}')
        return pixels[y:y+h, x:x+w], mask


class InsertoDetector:
    """Segmenta insertos usando contraste local e crescimento de regioes.

    Nao usa numero esperado, grade, circularidade ou raio predefinido.
    """
    def __init__(self, sensitivity=1.5, min_area=0):
        if not np.isfinite(sensitivity) or sensitivity <= 0:
            raise ValueError('Sensibilidade deve ser positiva e finita.')
        if min_area < 0:
            raise ValueError('A area minima nao pode ser negativa.')
        self.sensitivity = float(sensitivity)
        self.min_area = int(min_area)

    @staticmethod
    def refine(crop, valid_mask, objects):
        """Completa mascaras parciais ajustando um fundo LOCAL por componente.

        Um polinomio suave e ajustado somente a pixels externos a semente.
        O crescimento ocorre no contraste corrigido, sem supor a forma.
        """
        H, W = crop.shape
        smoothed = ndi.gaussian_filter(crop.astype(np.float32), sigma=2.0)
        all_seeds = np.zeros((H, W), dtype=bool)
        for obj in objects:
            all_seeds[obj['slice']] |= obj['mask']
        refined = []

        for obj in objects:
            sl = obj['slice']
            y0, y1 = sl[0].start, sl[0].stop
            x0, x1 = sl[1].start, sl[1].stop
            size = max(y1 - y0, x1 - x0)
            pad = int(np.clip(size * 0.95, 32, 110))
            ya, yb = max(0, y0 - pad), min(H, y1 + pad)
            xa, xb = max(0, x0 - pad), min(W, x1 + pad)
            window = np.s_[ya:yb, xa:xb]
            sub = smoothed[window]
            valid = valid_mask[window]
            seed = np.zeros(valid.shape, dtype=bool)
            seed[y0-ya:y1-ya, x0-xa:x1-xa] = obj['mask']
            other = all_seeds[window] & ~seed

            # Ajusta o fundo do componente fora da regiao identificada.
            distance = ndi.distance_transform_edt(~seed)
            buffer = int(np.clip(size * 0.27, 10, 25))
            exterior = valid & (distance > buffer)
            if other.any():
                exterior &= ~ndi.binary_dilation(other, iterations=8)
            if np.count_nonzero(exterior) < 250:
                refined.append(obj)
                continue

            yc, xc = (y0 + y1) / 2, (x0 + x1) / 2
            yy, xx = np.mgrid[ya:yb, xa:xb]
            u = (xx - xc) / (size + 1)
            v = (yy - yc) / (size + 1)
            # Ajuste de fundo por AMOSTRAGEM: limita a matriz de regressao.
            # Antes, todos os pixels da janela entravam numa matriz float64,
            # provocando picos de RAM e possiveis encerramentos pelo Linux.
            yy_bg, xx_bg = np.nonzero(exterior)
            step = max(1, int(np.ceil(yy_bg.size / 4000)))
            yy_bg = yy_bg[::step]
            xx_bg = xx_bg[::step]
            uu = u[yy_bg, xx_bg]
            vv = v[yy_bg, xx_bg]
            X = np.column_stack((np.ones(uu.size), uu, vv, uu * vv, uu**2, vv**2))
            observed = sub[yy_bg, xx_bg]
            good = np.ones(observed.size, dtype=bool)
            coef = None
            noise = 1.0

            # Refaz o ajuste rejeitando pixels discrepantes (outliers).
            for _ in range(3):
                if np.count_nonzero(good) < 250:
                    break
                coef = np.linalg.lstsq(X[good], observed[good], rcond=None)[0]
                error = observed - X @ coef
                median = float(np.median(error[good]))
                noise = float(1.4826 * np.median(np.abs(error[good] - median)))
                good = np.abs(error - median) < max(3 * noise, 3.0)
            if coef is None:
                refined.append(obj)
                continue

            local_background = (coef[0] + coef[1]*u + coef[2]*v +
                                coef[3]*u*v + coef[4]*u*u + coef[5]*v*v)
            sign = -1 if obj['polarity'] == 'escuro' else 1
            contrast = sign * (sub - local_background)
            signal = float(np.median(contrast[seed]))
            threshold = max(2.3 * max(noise, 1.0), 0.24 * signal)
            if signal <= threshold:
                refined.append(obj)
                continue

            permitted = (contrast > threshold) & valid & ~other
            grown = ndi.binary_propagation(seed & permitted, mask=permitted)
            grown = ndi.binary_closing(grown, iterations=2)
            grown = ndi.binary_fill_holes(grown) & valid & ~other

            count = int(grown.sum())
            initial_count = int(seed.sum())
            if count < 0.5 * initial_count or count > 2.8 * initial_count:
                refined.append(obj)
                continue

            ys, xs = np.where(grown)
            if len(xs) == 0:
                refined.append(obj)
                continue

            y_min, y_max = ys.min(), ys.max() + 1
            x_min, x_max = xs.min(), xs.max() + 1
            new_slice = np.s_[ya+y_min:ya+y_max, xa+x_min:xa+x_max]
            new_mask = grown[y_min:y_max, x_min:x_max]
            cy, cx = ndi.center_of_mass(grown)
            new_obj = obj.copy()
            new_obj.update({
                'slice': new_slice,
                'mask': new_mask,
                'cx': float(cx + xa),
                'cy': float(cy + ya),
                'area_px': count,
                'local_contrast': float(np.mean(contrast[grown])),
            })
            refined.append(new_obj)
        return refined

    @staticmethod
    def local_background(crop, inside, occupied, obj):
        """Estima S_fundo num anel local EXTERNO ao objeto, sem forma imposta.

        O anel e gerado por distancia euclidiana ao contorno segmentado:
        funciona com formas irregulares e nao presume circulos.
        """
        sl, region = obj['slice'], obj['mask']
        h, w = region.shape
        size = max(1, min(h, w))
        inner = max(5, int(round(0.10 * size)))
        band = max(14, int(round(0.35 * size)))

        H, W = crop.shape
        # Janela ao redor do objeto para economizar memoria.
        margin = inner + 2 * band + 2
        ya = max(0, sl[0].start - margin)
        yb = min(H, sl[0].stop + margin)
        xa = max(0, sl[1].start - margin)
        xb = min(W, sl[1].stop + margin)
        win = np.s_[ya:yb, xa:xb]

        local_obj = np.zeros((yb - ya, xb - xa), dtype=bool)
        local_obj[
            sl[0].start-ya:sl[0].stop-ya,
            sl[1].start-xa:sl[1].stop-xa
        ] = region

        distance = ndi.distance_transform_edt(~local_obj)
        allowed = inside[win] & ~occupied[win]
        annulus = allowed & (distance >= inner) & (distance <= inner + band)
        min_samples = max(30, int(region.sum() * 0.1))
        if annulus.sum() < min_samples:
            annulus = allowed & (distance >= inner) & (distance <= inner + 2*band)
        values = crop[win][annulus].astype(np.float64)
        if values.size < 30:
            return float('nan'), float('nan'), int(values.size)

        # Mediana mais robusta que media contra pequenas contaminacoes.
        return float(np.median(values)), float(np.std(values)), int(values.size)

    def detect(self, crop, phantom_mask):
        H, W = crop.shape
        img = crop.astype(np.float32)
        margin = max(8, int(min(H, W) * 0.035))
        inside = ndi.binary_erosion(phantom_mask, iterations=margin)
        if np.count_nonzero(inside) < 200:
            raise RuntimeError('Area interna insuficiente para analise.')

        # Contraste local inicial: permite identificar sementes sem forma imposta.
        smooth = ndi.gaussian_filter(img, sigma=2.5)
        sigma = max(25, min(H, W) * 0.065)
        weight = ndi.gaussian_filter(inside.astype(np.float32), sigma=sigma)
        avg = ndi.gaussian_filter(smooth * inside, sigma=sigma)
        background = np.divide(avg, weight, out=np.zeros_like(avg), where=weight > 1e-5)
        residual = smooth - background
        samples = residual[inside]
        median = np.median(samples)
        noise = float(1.4826 * np.median(np.abs(samples - median)))
        if not np.isfinite(noise) or noise < 1e-5:
            raise RuntimeError('Imagem sem contraste suficiente para detectar insertos.')

        min_pixels = self.min_area or max(25, int(inside.sum() * 0.00018))
        max_pixels = int(inside.sum() * 0.15)
        objects = []
        for polarity, sign in [('escuro', -1), ('claro', 1)]:
            contrast = sign * residual
            seed = (contrast > self.sensitivity * noise) & inside
            permissive = (contrast > self.sensitivity * 0.5 * noise) & inside
            regions = ndi.binary_propagation(seed, mask=permissive)
            regions = ndi.binary_opening(regions, structure=np.ones((3, 3), dtype=bool))
            regions = ndi.binary_fill_holes(regions) & inside
            labels, count = ndi.label(regions)
            sizes = np.bincount(labels.ravel())
            slices = ndi.find_objects(labels)
            for n in range(1, count + 1):
                area = int(sizes[n])
                if not min_pixels <= area <= max_pixels:
                    continue
                sl = slices[n-1]
                if sl is None:
                    continue
                reg = labels[sl] == n
                cy, cx = ndi.center_of_mass(reg)
                objects.append({
                    'polarity': polarity,
                    'cx': float(cx + sl[1].start),
                    'cy': float(cy + sl[0].start),
                    'area_px': area,
                    'slice': sl,
                    'mask': reg,
                })

        objects = self.refine(crop, inside, objects)

        # Mede os insertos no DICOM ORIGINAL, antes de qualquer correcao.
        for obj in objects:
            sl, region = obj['slice'], obj['mask']
            core = ndi.binary_erosion(region, iterations=2)
            if core.sum() < max(9, region.sum() * 0.2):
                core = region
            values = crop[sl][core].astype(np.float64)
            obj.update({
                'mean': float(values.mean()),
                'std': float(values.std()),
                'pixel_count': int(values.size),
            })

        # Mede o fundo ao redor de CADA inserto, excluindo os proprios insertos.
        # Adapta o S_fundo da Equacao (1) do TCC de William da Veiga.
        occupied = np.zeros((H, W), dtype=bool)
        for obj in objects:
            occupied[obj['slice']] |= obj['mask']

        for obj in objects:
            obj['background'], obj['background_std'], obj['background_pixels'] = (
                self.local_background(crop, inside, occupied, obj)
            )

        # O TCC utiliza o fundo da ROI 12 como referencia. Como aqui NAO
        # supomos numeracao, quantidade ou disposicao, substituimos essa
        # referencia especifica pela mediana dos fundos locais detectados.
        valid_backgrounds = [
            obj['background'] for obj in objects
            if np.isfinite(obj['background']) and obj['background'] > 0
        ]
        if not valid_backgrounds and objects:
            raise RuntimeError('Nao foi possivel estimar o fundo das regioes.')
        reference = float(np.median(valid_backgrounds)) if valid_backgrounds else float('nan')

        for obj in objects:
            bg = obj['background']
            if not np.isfinite(bg) or bg <= 0:
                # Preserva o valor bruto na tabela e marca que a comparacao
                # corrigida nao e confiavel, em vez de fabricar resultado.
                obj['corrected'] = float('nan')
                obj['relative_contrast'] = float('nan')
            else:
                # S_corrigido = (S_ROI / S_fundo_local) * S_ref
                obj['corrected'] = obj['mean'] / bg * reference
                obj['relative_contrast'] = 100.0 * (obj['mean'] / bg - 1.0)
            obj['reference_background'] = reference

        # Comparacao explicita: posicao antiga (bruta) e posicao corrigida.
        for raw_rank, obj in enumerate(
            sorted(objects, key=lambda o: (-o['mean'], o['cy'], o['cx'])),
            start=1
        ):
            obj['raw_rank'] = raw_rank

        # 1 = maior sinal CORRIGIDO; ausencias/falhas ficam no fim.
        objects.sort(key=lambda o: (
            not np.isfinite(o['corrected']),
            -o['corrected'] if np.isfinite(o['corrected']) else 0,
            o['cy'], o['cx']
        ))

        full_labels = np.zeros((H, W), dtype=np.int32)
        for index, obj in enumerate(objects, start=1):
            obj['id'] = index
            sl, reg = obj['slice'], obj['mask']
            full_labels[sl][reg] = index

        print(f'Fundo de referencia (mediana): {reference:.2f}')
        print(f'\nRuido global estimado: {noise:.2f}')
        print(f'Area minima: {min_pixels} pixels')
        print(f'Regioes identificadas: {len(objects)}')
        return objects, full_labels


def pixel_area_mm2(ds):
    spacing = getattr(ds, 'PixelSpacing', None)
    if spacing is None or len(spacing) < 2:
        return None
    try:
        dy, dx = float(spacing[0]), float(spacing[1])
        return dy * dx if dy > 0 and dx > 0 else None
    except (TypeError, ValueError):
        return None


def show_results(crop, objects, labels, output_path, show_window=True,
                 use_matplotlib=False):
    """Mostra a imagem com OpenCV (menos RAM); opcionalmente Matplotlib."""
    if use_matplotlib:
        import matplotlib.pyplot as plt
        fig, axes = plt.subplots(1, 2, figsize=(16, 7))
        lo, hi = np.percentile(crop, [1, 99])
        for ax in axes:
            ax.imshow(crop, cmap='gray', vmin=lo, vmax=hi)
            ax.axis('off')
        axes[0].set_title('Contornos e numeros por sinal corrigido')
        axes[1].set_title(f'Segmentacao automatica ({len(objects)} regioes)')
        colored = np.ma.masked_where(labels == 0, labels)
        axes[1].imshow(colored, cmap='nipy_spectral',
                       interpolation='nearest', alpha=0.65)
        for obj in objects:
            sl = obj['slice']
            contours, _ = cv2.findContours(obj['mask'].astype(np.uint8),
                                           cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            color = 'red' if obj['polarity'] == 'escuro' else 'cyan'
            for c in contours:
                p = c[:, 0, :]
                axes[0].plot(p[:, 0] + sl[1].start,
                             p[:, 1] + sl[0].start,
                             color=color, linewidth=1.1)
            for ax, text_color in [(axes[0], 'yellow'), (axes[1], 'white')]:
                ax.text(obj['cx'], obj['cy'], str(obj['id']),
                        color=text_color, fontsize=9, fontweight='bold',
                        ha='center', va='center')
        plt.tight_layout()
        fig.savefig(output_path, dpi=110)
        if show_window:
            plt.show()
        plt.close(fig)
        print(f'Imagem salva em: {output_path}', flush=True)
        return

    # A visualizacao padrao evita carregar a biblioteca Matplotlib.
    lo, hi = np.percentile(crop, [1, 99])
    if hi <= lo:
        hi = lo + 1
    gray = np.clip(
        (crop.astype(np.float32) - lo) * (255.0 / (hi - lo)),
        0, 255
    ).astype(np.uint8)
    base = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    left = base.copy()
    right = base.copy()

    H, W = crop.shape
    # Mistura a imagem com a segmentacao sem alterar os dados DICOM.
    for obj in objects:
        sl = obj['slice']
        reg = obj['mask']
        y0, x0 = sl[0].start, sl[1].start
        num = obj['id']
        hue = int((num * 37) % 180)
        hsv = np.uint8([[[hue, 220, 220]]])
        color = tuple(int(x) for x in cv2.cvtColor(
            hsv, cv2.COLOR_HSV2BGR)[0, 0])
        patch = right[sl]
        patch[reg] = (0.35 * patch[reg] + 0.65 * np.array(color)).astype(np.uint8)
        contours, _ = cv2.findContours(
            reg.astype(np.uint8), cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE
        )
        for contour in contours:
            contour = contour + np.array([[[x0, y0]]], dtype=np.int32)
            cv2.drawContours(
                left, [contour], -1,
                (0, 0, 255) if obj['polarity'] == 'escuro' else (255, 255, 0),
                thickness=2
            )
        cx, cy = int(round(obj['cx'])), int(round(obj['cy']))
        label = str(num)
        font = cv2.FONT_HERSHEY_SIMPLEX
        scale = 0.60
        thickness = 2
        (tw, th), _ = cv2.getTextSize(label, font, scale, thickness)
        pos = (cx - tw // 2, cy + th // 2)
        cv2.putText(left, label, pos, font, scale, (0, 0, 0), 4, cv2.LINE_AA)
        cv2.putText(left, label, pos, font, scale, (0, 255, 255), 2, cv2.LINE_AA)
        cv2.putText(right, label, pos, font, scale, (0, 0, 0), 4, cv2.LINE_AA)
        cv2.putText(right, label, pos, font, scale, (255, 255, 255), 2, cv2.LINE_AA)

    # Redimensiona somente a visualizacao, nunca os pixels medidos.
    view_width = 690
    view_height = max(1, int(round(H * view_width / W)))
    left = cv2.resize(left, (view_width, view_height), interpolation=cv2.INTER_AREA)
    right = cv2.resize(right, (view_width, view_height), interpolation=cv2.INTER_AREA)
    header = 60
    canvas = np.full((view_height + header, view_width * 2 + 24, 3), 245, dtype=np.uint8)
    canvas[header:, :view_width] = left
    canvas[header:, view_width + 24:] = right
    cv2.putText(canvas, 'Contornos / sinal corrigido',
                (18, 38), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (40, 40, 40), 2)
    cv2.putText(canvas, f'Segmentacao ({len(objects)} regioes)',
                (view_width + 40, 38), cv2.FONT_HERSHEY_SIMPLEX,
                0.75, (40, 40, 40), 2)

    if not cv2.imwrite(str(output_path), canvas):
        raise RuntimeError(f'Nao foi possivel salvar: {output_path}')
    print(f'Imagem salva em: {output_path}', flush=True)

    if show_window:
        if not (os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')):
            print('Sem ambiente grafico; abra a imagem PNG salva no projeto.',
                  flush=True)
            return
        try:
            cv2.imshow('Analise DICOM - pressione uma tecla para fechar', canvas)
            cv2.waitKey(0)
            cv2.destroyAllWindows()
        except cv2.error as exc:
            print('Nao foi possivel abrir a janela OpenCV:', exc)
            print('O resultado PNG foi salvo.', flush=True)

def main(argv=None):
    parser = argparse.ArgumentParser(description='Detecta insertos sem geometria predefinida e corrige gradientes de sinal.')
    parser.add_argument('arquivo', help='Nome em dicom/ ou caminho completo para DICOM.')
    parser.add_argument('--sensibilidade', type=float, default=1.5,
                        help='Maior detecta apenas contrastes mais fortes (padrao: 1.5).')
    parser.add_argument('--min-area', type=int, default=0,
                        help='Area minima de um inserto, em pixels (0 = automatico).')
    parser.add_argument('--sem-grafico', action='store_true',
                        help='Imprime somente os resultados numericos.')
    parser.add_argument('--sem-janela', action='store_true',
                        help='Salva a visualizacao em PNG sem abrir janela.')
    parser.add_argument('--matplotlib', action='store_true',
                        help='Usa Matplotlib (consome mais memoria).')
    args = parser.parse_args(argv)
    try:
        print('Abrindo arquivo DICOM...', flush=True)
        path = DicomReader.resolve(args.arquivo)
        ds, raw = DicomReader.read(path)
        print('DICOM carregado.', flush=True)
        crop, mask = PhantomSegmenter().detect(raw)
        print('Recorte concluido. Detectando e refinando os insertos...', flush=True)
        objects, labels = InsertoDetector(args.sensibilidade, args.min_area).detect(crop, mask)
        print('\n=== RESULTADOS ===')
        area_scale = pixel_area_mm2(ds)
        if not objects:
            print('Nenhum inserto identificado com os parametros utilizados.')
        for obj in objects:
            area = (f" | Area: {obj['area_px'] * area_scale:.2f} mm2" if
                    area_scale is not None else '')
            print(f"{obj['id']:02d} | Bruto: {obj['mean']:8.2f} "
                  f"(posicao bruta: {obj['raw_rank']:02d}) | "
                  f"Fundo local: {obj['background']:8.2f} | "
                  f"Corrigido: {obj['corrected']:8.2f} | "
                  f"Contraste relativo: {obj['relative_contrast']:+7.2f}% | "
                  f"Area: {obj['area_px']} px{area} | "
                  f"Centro: ({obj['cx']:.1f}, {obj['cy']:.1f}) | "
                  f"DP: {obj['std']:.2f}")
        if not args.sem_grafico:
            output_path = Path.cwd() / f'resultado_{path.stem}.png'
            print('Gerando visualizacao...', flush=True)
            show_results(crop, objects, labels, output_path,
                         show_window=not args.sem_janela,
                         use_matplotlib=args.matplotlib)
        return 0
    except Exception as e:
        print(f'Erro: {e}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
