"""
Улучшенный имитатор рукописного текста.
Правильная перекраска: берём инвертированную яркость + альфа-канал как маску,
чтобы антиалиасинг и полупрозрачные края тоже окрашивались корректно.
"""

from PIL import Image, ImageDraw, ImageFilter, ImageOps, ImageChops
import os
import random
from collections import defaultdict
import math

# ------------------------
# Утилиты
# ------------------------
def hex_to_rgb(hex_color):
    """Преобразует '#RRGGBB' или короткие формы и некоторые имена в (R,G,B)."""
    if not hex_color:
        return (0, 0, 0)
    if isinstance(hex_color, tuple) and len(hex_color) == 3:
        return hex_color
    s = str(hex_color).strip()
    names = {
        "white": (255,255,255),
        "black": (0,0,0),
        "red": (255,0,0),
        "green": (0,255,0),
        "blue": (0,0,255),
        "brown": (150,75,0),
        "paper": (250,245,240),
    }
    if s.lower() in names:
        return names[s.lower()]
    if s.startswith('#'):
        s = s[1:]
    if len(s) == 3:
        s = ''.join([c*2 for c in s])
    if len(s) != 6:
        # По умолчанию чёрный
        return (0,0,0)
    try:
        return tuple(int(s[i:i+2], 16) for i in (0, 2, 4))
    except:
        return (0,0,0)

def load_letter_images(font_folder, text_color_rgb=None, auto_trim=True):
    """
    Загружает изображения букв из папки.
    Перекрашивает каждый вариант через инвертированную яркость + альфа.
    Возвращает dict: key -> [ImageRGBA, ...]
    Ключ: имя файла без цифровых суффиксов, в верхнем регистре (например: 'A', 'POINT').
    """
    variants = defaultdict(list)
    if not os.path.isdir(font_folder):
        raise FileNotFoundError(f"Папка с буквами не найдена: {font_folder}")

    for fname in sorted(os.listdir(font_folder)):
        if not fname.lower().endswith(('.png', '.jpg', '.jpeg')):
            continue
        base = os.path.splitext(fname)[0]
        key = base.rstrip('0123456789').upper()
        path = os.path.join(font_folder, fname)
        try:
            img = Image.open(path).convert("RGBA")
        except Exception as e:
            print(f"Не удалось открыть {path}: {e}")
            continue

        # Обрезаем пустые поля (если нужно) для более точного кернинга
        if auto_trim:
            bbox = img.getbbox()
            if bbox:
                img = img.crop(bbox)

        # Перекрашиваем: используем инвертированную яркость * альфа как итоговую маску.
        # Это корректно работает, если исходный рисунок — чёрный (и полу-прозрачные края)
        if text_color_rgb is not None:
            # Градация серого изображения (яркость)
            gray = ImageOps.grayscale(img)  # 0..255, где 0 — чёрный (т.е. чернила)
            # Инвертируем яркость: теперь 255 где было чёрное
            inv = ImageOps.invert(gray)
            # Учитываем исходный альфа-канал (если фон в PNG прозрачный)
            alpha = img.split()[-1]
            # Маска = (инверсия яркости) * (альфа / 255)
            # Для этого умножим и нормализуем:
            mask = ImageChops.multiply(inv.convert("L"), alpha)
            # Создаём цветной слой и ставим как альфу нашу маску
            colored = Image.new("RGBA", img.size, text_color_rgb + (0,))
            colored.putalpha(mask)
            img = colored

        variants[key].append(img)

    return variants

# ------------------------
# Главная функция
# ------------------------
def text_to_a4(
    text: str,
    output_path: str = "output_a4.png",
    font_folder: str = "letters",
    dpi: int = 300,
    background_color: str = "#FFFFFF",
    text_color: str = "black",
    uppercase: bool = False,
    margin_left: int = 100,
    margin_top: int = 100,
    margin_right: int = 100,
    margin_bottom: int = 100,
    line_spacing: int = 18,
    space_width: int = None,
    max_rotation: float = 6.0,
    max_scale_jitter: float = 0.06,
    random_offset: int = 3,
    baseline_jitter: int = 6,
    kerning_jitter: int = 2,
    bleed_amount: int = 2,
    blur_after_bleed: float = 0.8,
    paper_texture: str = None,
    paper_opacity: float = 1.0,
    add_noise: bool = True,
    noise_level: float = 0.02,
    preserve_transparent_background: bool = False,
):
    """
    Рендерит заданный текст на листе A4 (в пикселях, вычисляемых через DPI).
    """

    # Подготовка
    bg_rgb = hex_to_rgb(background_color)
    text_rgb = hex_to_rgb(text_color)

    a4_w = int(8.27 * dpi)
    a4_h = int(11.69 * dpi)

    if uppercase:
        text = text.upper()

    # Загружаем буквы (и перекрашиваем их на этапе загрузки)
    letter_variants = load_letter_images(font_folder, text_color_rgb=text_rgb)

    if not letter_variants:
        raise FileNotFoundError("В папке нет изображений букв (png/jpg). Проверьте папку font_folder.")

    # Буфер RGBA
    canvas = Image.new("RGBA", (a4_w, a4_h), (0,0,0,0))

    # Вычисление ширины пробела, если не задана
    if space_width is None:
        widths = []
        for lst in letter_variants.values():
            for im in lst[:3]:
                widths.append(im.width)
        space_width = int(sum(widths)/len(widths)) if widths else int(0.25 * dpi)

    x = margin_left
    y = margin_top
    max_line_height = 0

    def paste_letter(letter_img, pos_x, pos_y):
        """Вставляет letter_img в canvas с учётом bleed и blur."""
        # масштаб
        jitter_scale = 1.0 + random.uniform(-max_scale_jitter, max_scale_jitter)
        if abs(jitter_scale - 1.0) > 1e-6:
            nw = max(1, int(letter_img.width * jitter_scale))
            nh = max(1, int(letter_img.height * jitter_scale))
            letter_img = letter_img.resize((nw, nh), resample=Image.BICUBIC)

        # поворот
        angle = random.uniform(-max_rotation, max_rotation)
        if abs(angle) > 1e-6:
            letter_img = letter_img.rotate(angle, expand=True, resample=Image.BICUBIC)

        # Bleed (растекание): используем альфа исходного символа (или его яркость)
        if bleed_amount and bleed_amount > 0:
            # Получаем маску альфа (или градацию яркости если есть)
            mask = letter_img.split()[-1]
            # Увеличиваем размеры маски и размываем
            mask = mask.filter(ImageFilter.MaxFilter(bleed_amount*2+1))
            mask = mask.filter(ImageFilter.GaussianBlur(radius=bleed_amount))
            bleed_layer = Image.new("RGBA", letter_img.size, text_rgb + (96,))  # полупрозрачный тон
            bleed_layer.putalpha(mask)
            # рисуем растекание под основной буквой
            canvas.paste(bleed_layer, (pos_x, pos_y), bleed_layer)

        # Лёгкое размытие для реализма краёв
        if blur_after_bleed and blur_after_bleed > 0:
            try:
                letter_img = letter_img.filter(ImageFilter.GaussianBlur(radius=0.12 * blur_after_bleed))
            except Exception:
                pass

        canvas.paste(letter_img, (pos_x, pos_y), letter_img)
        return letter_img.width, letter_img.height

    i = 0
    n = len(text)
    while i < n:
        ch = text[i]

        # Новая строка
        if ch == '\n':
            x = margin_left + random.randint(-5,5)
            y += max_line_height + line_spacing
            max_line_height = 0
            i += 1
            continue

        # Пробел
        if ch == ' ':
            x += space_width + random.randint(-kerning_jitter, kerning_jitter)
            i += 1
            continue

        # Пунктуация: используем отдельные файлы POINT, COMMA, QUESTION и т.д., если они есть
        if ch == '.':
            key = "POINT"
        elif ch == ',':
            key = "COMMA"
        elif ch == '?':
            key = "QUESTION"
        elif ch == '!':
            key = "EXCLAMATION"
        else:
            key = ch.upper()

        if key not in letter_variants:
            # Просто выводим предупреждение и пропускаем символ
            print(f"[warn] Нет варианта для символа '{ch}' (ключ '{key}'), пропускаем.")
            i += 1
            continue

        letter_img = random.choice(letter_variants[key]).copy()
        # Обрезка пустого поля
        bbox = letter_img.getbbox()
        if bbox:
            letter_img = letter_img.crop(bbox)

        # Проверка переноса по ширине (примерная ширина с учётом масштаба)
        approx_w = int(letter_img.width * (1 + max_scale_jitter))
        if x + approx_w > a4_w - margin_right:
            x = margin_left + random.randint(-6,6)
            y += max_line_height + line_spacing
            max_line_height = 0

        # Случайные оффсеты
        ox = random.randint(-random_offset, random_offset)
        oy = random.randint(-baseline_jitter, baseline_jitter)

        # Небольшой shear для имитации рукописного наклона
        shear = random.uniform(-0.06, 0.06)
        if abs(shear) > 1e-4:
            w0, h0 = letter_img.size
            new_w = w0 + abs(int(h0 * shear))
            try:
                letter_img = letter_img.transform(
                    (new_w, h0),
                    Image.AFFINE,
                    (1, shear, 0, 0, 1, 0),
                    resample=Image.BICUBIC)
            except Exception:
                pass

        w, h = paste_letter(letter_img, x + ox, y + oy)

        x += w + random.randint(-kerning_jitter, kerning_jitter)
        if h > max_line_height:
            max_line_height = h

        i += 1

    # Подготовка финального изображения (RGB) или RGBA если preserve_transparent_background
    if preserve_transparent_background:
        out = canvas
    else:
        out = Image.new("RGB", (a4_w, a4_h), bg_rgb)
        out.paste(canvas, (0,0), canvas)

    # Текстура бумаги (если указана)
    if paper_texture and os.path.exists(paper_texture):
        paper = Image.open(paper_texture).convert("RGB").resize((a4_w, a4_h), resample=Image.BICUBIC)
        if preserve_transparent_background and out.mode == "RGBA":
            base = Image.new("RGB", (a4_w, a4_h), bg_rgb)
            blended = ImageChops.multiply(base, paper)
            blended = Image.blend(base, blended, paper_opacity)
            # сохраняем альфу из canvas
            alpha = canvas.split()[-1]
            out = blended.convert("RGBA")
            out.putalpha(alpha)
        else:
            base = Image.new("RGB", (a4_w, a4_h), bg_rgb)
            base = ImageChops.multiply(base, paper)
            out = Image.blend(base, out.convert("RGB"), paper_opacity) if paper_opacity < 1 else ImageChops.multiply(base, out.convert("RGB"))

    # Шум
    if add_noise and noise_level > 0:
        try:
            import numpy as np
            arr = np.array(out).astype('float32') / 255.0
            noise = (np.random.randn(*arr.shape) * noise_level).astype('float32')
            arr = arr + noise
            arr = (255.0 * (arr.clip(0.0, 1.0))).astype('uint8')
            out = Image.fromarray(arr)
        except Exception as e:
            # Ничего страшного, если numpy нет — пропускаем шум
            pass

    # Сохраняем
    save_kwargs = {"dpi": (dpi, dpi)}
    out_to_save = out if (preserve_transparent_background and out.mode == "RGBA") else out.convert("RGB")
    out_to_save.save(output_path, **save_kwargs)
    print(f"Готово. Файл сохранён: {output_path}")

# ------------------------
# Пример использования
# ------------------------
if __name__ == "__main__":
    # Пример: папка letters должна содержать файлы типа A1.png, A2.png, POINT.png и т.д.
    text_to_a4(
        text="тот самый рукописный текст, который должен выглядеть натурально.\nПроверь соединения и оттенки.",
        output_path="output.png",
        font_folder="letters",          # <- сюда поместите ваши изображение букв
        dpi=300,
        background_color="#FBF7EF",
        text_color="#1B1B1B",           # Можно указать '#RRGGBB' или имя цвета
        uppercase=False,
        margin_left=100,
        margin_top=100,
        margin_right=100,
        margin_bottom=100,
        line_spacing=18,
        space_width=None,
        max_rotation=5.0,
        max_scale_jitter=0.05,
        random_offset=3,
        baseline_jitter=5,
        kerning_jitter=0,
        bleed_amount=2,
        blur_after_bleed=0.9,
        paper_texture=None,            # например "paper.jpg", если есть
        paper_opacity=0.9,
        add_noise=True,
        noise_level=0.012,
        preserve_transparent_background=False
    )
