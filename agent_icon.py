import sys
import io
import time
import threading

# Asegurar que la salida estándar use UTF-8 en Windows
if hasattr(sys.stdout, 'encoding') and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Colores (R, G, B)
TR = None
BK = (15, 19, 26)   # Negro del sombrero
DG = (42, 53, 70)   # Gris oscuro (brillo del sombrero)
FG = (160, 224, 37) # Verde principal de la rana
SG = (117, 168, 22) # Verde sombra (debajo del ala del sombrero)

# Arte original pixel a pixel
BASE_IMAGE = [
    [TR, TR, TR, TR, TR, BK, DG, BK, BK, BK, BK, TR, TR, TR, TR, TR], # 0
    [TR, TR, TR, TR, TR, BK, DG, BK, BK, BK, BK, TR, TR, TR, TR, TR], # 1
    [TR, TR, TR, TR, TR, BK, DG, BK, BK, BK, BK, TR, TR, TR, TR, TR], # 2
    [TR, TR, TR, TR, TR, BK, DG, BK, BK, BK, BK, TR, TR, TR, TR, TR], # 3
    [TR, TR, TR, BK, BK, BK, BK, BK, BK, BK, BK, BK, BK, TR, TR, TR], # 4 (Ala, más corta)
    [TR, TR, TR, TR, SG, SG, SG, SG, SG, SG, SG, SG, TR, TR, TR, TR], # 5 (Sombra)
    [TR, TR, TR, TR, FG, FG, FG, FG, FG, FG, FG, FG, TR, TR, TR, TR], # 6 (Frente)
    [TR, TR, TR, TR, FG, BK, FG, FG, FG, FG, BK, FG, TR, TR, TR, TR], # 7 (Ojos en 5 y 10)
    [TR, TR, TR, TR, FG, FG, FG, FG, FG, FG, FG, FG, TR, TR, TR, TR], # 8
    [TR, TR, TR, FG, FG, FG, FG, FG, FG, FG, FG, FG, FG, TR, TR, TR], # 9 (Cachetes, más flacos)
    [TR, TR, TR, FG, FG, FG, FG, FG, FG, FG, FG, FG, FG, TR, TR, TR], # 10
    [TR, TR, TR, FG, FG, FG, FG, FG, FG, FG, FG, FG, FG, TR, TR, TR], # 11
    [TR, TR, TR, TR, FG, FG, TR, TR, TR, TR, FG, FG, TR, TR, TR, TR], # 12 (Piernas)
    [TR, TR, TR, FG, FG, FG, TR, TR, TR, TR, FG, FG, FG, TR, TR, TR], # 13 (Pies)
]

def render_half_blocks(grid):
    lines = []
    # Usar bloques de mitad (▀) permite tener píxeles perfectamente cuadrados
    for r in range(0, len(grid), 2):
        row_top = grid[r]
        row_bottom = grid[r+1] if r+1 < len(grid) else [None]*len(row_top)
        
        line = "   " # Indentación
        for c in range(len(row_top)):
            top = row_top[c]
            bottom = row_bottom[c]
            
            if top is None and bottom is None:
                line += "\033[0m  " # Espacio vacío (2 chars de ancho para simular pixel)
            elif top is not None and bottom is None:
                line += f"\033[38;2;{top[0]};{top[1]};{top[2]}m▀▀\033[0m"
            elif top is None and bottom is not None:
                line += f"\033[38;2;{bottom[0]};{bottom[1]};{bottom[2]}m▄▄\033[0m"
            else: # ambos tienen color
                line += f"\033[38;2;{top[0]};{top[1]};{top[2]};48;2;{bottom[0]};{bottom[1]};{bottom[2]}m▀▀\033[0m"
        lines.append(line)
    return lines

def create_frame(eye_state="center", y_offset=1):
    grid = [[TR]*16 for _ in range(16)] 
    
    for r in range(14):
        for c in range(16):
            if r + y_offset < 16:
                grid[r + y_offset][c] = BASE_IMAGE[r][c]
                
    eye_row = 7 + y_offset
    if eye_row < 16:
        # Borrar ojos originales
        grid[eye_row][5] = FG
        grid[eye_row][10] = FG
        
        if eye_state == "center":
            grid[eye_row][5] = BK
            grid[eye_row][10] = BK
        elif eye_state == "left":
            grid[eye_row][4] = BK
            grid[eye_row][9] = BK
        elif eye_state == "right":
            grid[eye_row][6] = BK
            grid[eye_row][11] = BK
        elif eye_state == "blink":
            grid[eye_row][5] = SG
            grid[eye_row][10] = SG

    return render_half_blocks(grid)

def generate_frames():
    frames = []
    # Ciclo de 64 cuadros
    for i in range(64):
        # Respiración: Sube y baja 1 pixel cada 16 cuadros
        y_offset = 1 if (i % 32) < 16 else 2
        
        eye = "center"
        if i == 15 or i == 45:
            eye = "blink"
        elif 20 <= i <= 24:
            eye = "left"
        elif 50 <= i <= 54:
            eye = "right"
            
        frames.append(create_frame(eye, y_offset))
        
    return frames

class TukiAnimation:
    def __init__(self, start_thread=True):
        self.frames = generate_frames()
        self.running = False
        self._thread = None
        self.current_frame_idx = 0
        if start_thread:
            self.start()
        
    def start(self, message="Starting TukiCode..."):
        if self.running: return
        self.running = True
        print(f"\n{message}\n")
        
        for _ in self.frames[0]: print()
        sys.stdout.write("\033[?25l")
        
        self._thread = threading.Thread(target=self._animate_loop)
        self._thread.daemon = True
        self._thread.start()
        
    def _animate_loop(self):
        lines_to_clear = len(self.frames[0])
        while self.running:
            sys.stdout.write(f"\033[{lines_to_clear}F")
            for line in self.frames[self.current_frame_idx]:
                sys.stdout.write("\033[2K" + line + "\n")
            sys.stdout.flush()
            self.current_frame_idx = (self.current_frame_idx + 1) % len(self.frames)
            time.sleep(0.12)

    def get_current_frame(self):
        frame = self.frames[self.current_frame_idx]
        self.current_frame_idx = (self.current_frame_idx + 1) % len(self.frames)
        return frame
            
    def stop(self):
        self.running = False
        if self._thread:
            self._thread.join()
        sys.stdout.write("\033[?25h")
        print("\n")

def run_demo():
    anim = TukiAnimation()
    try:
        anim.start(message="Press Ctrl+C to stop the animation...")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        anim.stop()

if __name__ == "__main__":
    run_demo()
