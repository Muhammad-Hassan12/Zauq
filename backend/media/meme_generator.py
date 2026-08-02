import os
import tempfile
from PIL import Image, ImageDraw, ImageFont

def generate_meme_image(
    top_text: str = "",
    bottom_text: str = "",
    bg_color: str = "#1e1e2e",
    text_color: str = "#ffffff",
    style: str = "classic"
) -> str:
    """
    Renders a meme image with top and bottom text overlay using PIL/Pillow.
    Saves to temporary directory and returns PNG filepath.
    """
    width, height = 800, 600
    image = Image.new("RGB", (width, height), color=bg_color)
    draw = ImageDraw.Draw(image)

    # Decorative header card styling
    draw.rectangle([20, 20, width - 20, height - 20], outline="#bb9af7", width=4)

    # Load default font
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", 36)
    except IOError:
        font = ImageFont.load_default()

    def draw_text_centered(text: str, y_pos: int, is_top: bool = True):
        if not text:
            return
        words = text.upper().split()
        lines = []
        current_line = []
        
        for word in words:
            test_line = " ".join(current_line + [word])
            bbox = draw.textbbox((0, 0), test_line, font=font)
            line_w = bbox[2] - bbox[0]
            if line_w < (width - 80):
                current_line.append(word)
            else:
                if current_line:
                    lines.append(" ".join(current_line))
                current_line = [word]
        if current_line:
            lines.append(" ".join(current_line))

        line_height = 45
        for i, line in enumerate(lines):
            bbox = draw.textbbox((0, 0), line, font=font)
            text_w = bbox[2] - bbox[0]
            x = (width - text_w) // 2
            y = y_pos + (i * line_height)

            # Draw black outline stroke
            for offset_x in [-2, 0, 2]:
                for offset_y in [-2, 0, 2]:
                    draw.text((x + offset_x, y + offset_y), line, font=font, fill="#000000")
            # Draw main text
            draw.text((x, y), line, font=font, fill=text_color)

    if top_text:
        draw_text_centered(top_text, y_pos=50, is_top=True)
    if bottom_text:
        draw_text_centered(bottom_text, y_pos=height - 130, is_top=False)

    temp_dir = tempfile.gettempdir()
    output_path = os.path.join(temp_dir, f"zauq_meme_{os.urandom(6).hex()}.png")
    image.save(output_path, format="PNG")
    return output_path
