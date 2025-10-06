from PIL import Image, ImageDraw, ImageOps
import os
import random
from collections import defaultdict
import math

def text_to_a4(
    text: str,
    output_path: str = "output_a4.png",
    font_folder: str = "letters",
    images_per_row: int = 15,
    horizontal_spacing: int = 0,
    vertical_spacing: int = 30,
    margin_left: int = 100,
    margin_top: int = 100,
    margin_right: int = 100,
    margin_bottom: int = 100,
    dpi: int = 300,
    background_color: str = "#FFFFFF",  # Белый по умолчанию (в HEX)
    text_color: str = "black",
    uppercase: bool = True,
    space_width: int = 100,
    random_offset: int = 5,
    max_rotation: int = 10,
    line_offset: int = 15,
):
    # Конвертируем цвета в RGB
    def hex_to_rgb(hex_color):
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

    bg_color = hex_to_rgb(background_color) if background_color.startswith('#') else {
        "white": (255, 255, 255),
        "black": (0, 0, 0),
        "red": (255, 0, 0),
        "green": (0, 255, 0),
        "blue": (0, 0, 255)
    }.get(background_color.lower(), (255, 255, 255))

    # Размер А4 в пикселях
    a4_width = int(8.27 * dpi)
    a4_height = int(11.69 * dpi)

    if uppercase:
        text = text.upper()

    # Загружаем варианты букв
    letter_variants = defaultdict(list)
    for filename in os.listdir(font_folder):
        if filename.upper().endswith(('.PNG', '.JPG', '.JPEG')):
            base_name = os.path.splitext(filename)[0]
            letter = base_name.rstrip('0123456789').upper()
            img_path = os.path.join(font_folder, filename)
            letter_img = Image.open(img_path).convert("RGBA")
            
            # Перекрашиваем текст
            if text_color.lower() != "black":
                data = letter_img.getdata()
                new_data = []
                for item in data:
                    if item[:3] == (0, 0, 0):  # Черный цвет
                        new_color = {
                            "red": (255, 0, 0),
                            "green": (0, 255, 0),
                            "blue": (0, 0, 255)
                        }.get(text_color.lower(), hex_to_rgb(text_color) if text_color.startswith('#') else (0, 0, 0))
                        new_data.append(new_color + (item[3],))
                    else:
                        new_data.append(item)
                letter_img.putdata(new_data)
            
            letter_variants[letter].append(letter_img)

    if not letter_variants:
        raise FileNotFoundError("В папке нет изображений букв!")

    # Создаем А4 с прозрачным фоном
    a4_image = Image.new('RGBA', (a4_width, a4_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(a4_image)

    x_offset = margin_left
    y_offset = margin_top
    line_height = 0

    for char in text:
        # Перенос строки
        if x_offset + space_width > a4_width - margin_right:
            x_offset = margin_left + random.randint(-line_offset, line_offset)
            y_offset += line_height + vertical_spacing
            line_height = 0

        # Пробел
        if char == " ":
            x_offset += space_width
            continue

        # Точка
        if char == ".":
            char = "POINT"

        if char not in letter_variants:
            print(f"Нет изображения для символа: '{char}'")
            continue

        letter_img = random.choice(letter_variants[char])
        
        # Поворачиваем букву
        if max_rotation > 0:
            angle = random.uniform(-max_rotation, max_rotation)
            letter_img = letter_img.rotate(angle, expand=True, resample=Image.BICUBIC)
        
        # Случайное смещение
        offset_x = random.randint(-random_offset, random_offset)
        offset_y = random.randint(-random_offset, random_offset)

        # Размещаем букву
        a4_image.alpha_composite(
            letter_img,
            (x_offset + offset_x, y_offset + offset_y)
        )

        x_offset += letter_img.width + horizontal_spacing
        if letter_img.height > line_height:
            line_height = letter_img.height

    # Создаем фон нужного цвета
    final_image = Image.new('RGB', (a4_width, a4_height), bg_color)
    
    # Заменяем все прозрачные/белые области на background_color
    data = a4_image.getdata()
    new_data = []
    for pixel in data:
        # Если пиксель прозрачный или белый (с учетом альфа-канала)
        if pixel[3] == 0 or (pixel[:3] == (255, 255, 255) and pixel[3] > 0):
            new_data.append(bg_color)
        else:
            new_data.append(pixel[:3])
    
    # Применяем изменения
    final_image.putdata(new_data)
    
    # Сохраняем
    final_image.save(output_path, dpi=(dpi, dpi))
    print(f"Результат сохранен в {output_path}")

# Пример использования
text_to_a4(
    text="тот самый рукописный  текст",
    output_path="custom_bg.png",
    font_folder="letters",
    background_color="#FFFFFF",  # Голубой фон
    text_color="black",
    random_offset=3,
    max_rotation=5
)
