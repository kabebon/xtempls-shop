import os
import re

frontend_dir = r"c:\Users\007\Documents\antigravity\xtmepls_bot\frontend"

# Remove bevel sections
bevel_pattern = re.compile(r'<section data-type="bevel"[^>]*>.*?</section>', re.DOTALL)

for fname in os.listdir(frontend_dir):
    if fname.endswith(".html"):
        path = os.path.join(frontend_dir, fname)
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Remove bevel
        new_content = bevel_pattern.sub('', content)
        
        # Also replace "Также в контакты добавь Укажи почту: xtempls@yandex.ru и Tg: @xtempls_wear" if possible
        # This is already in footer, let's just make sure it's correct.
        
        if new_content != content:
            with open(path, "w", encoding="utf-8") as f:
                f.write(new_content)
            print(f"Updated {fname}")

print("Done.")
