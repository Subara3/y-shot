"""Generate icons from emoji for y-shot (社内用)."""
from PIL import Image, ImageDraw, ImageFont


def create_emoji_icon(emoji, size):
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype('seguiemj.ttf', int(size * 0.85))
    bbox = draw.textbbox((0, 0), emoji, font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (size - w) // 2 - bbox[0]
    y = (size - h) // 2 - bbox[1]
    draw.text((x, y), emoji, font=font, embedded_color=True)
    return img


def save_ico(emoji, ico_path, png_path):
    sizes = [16, 32, 48, 64, 128, 256]
    images = [create_emoji_icon(emoji, s) for s in sizes]
    images[-1].save(ico_path, format='ICO',
                    sizes=[(s, s) for s in sizes],
                    append_images=images[:-1])
    print(f"  {ico_path}")
    preview = create_emoji_icon(emoji, 512)
    preview.save(png_path, format='PNG')
    print(f"  {png_path}")


if __name__ == '__main__':
    print("Generating icons...")
    save_ico('🦐', 'shot_icon.ico', 'shot_icon.png')
    save_ico('🍤', 'diff_icon.ico', 'diff_icon.png')
    print("Done!")
