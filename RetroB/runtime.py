# -*- coding: utf-8 -*-
# runtime.py (VERSION EXTENDIDA - GUI Tkinter + Accesibilidad para Snake - Python 2.7)
# Uso: python runtime.py <archivo_juego.json>

import sys
import json
import random
import colorsys

import Tkinter as tk

# El modulo winsound solo existe en Windows. Se protege el import para que
# el runtime no se caiga si alguien lo prueba en otro sistema operativo;
# simplemente el audio quedara deshabilitado.
try:
    import winsound
    AUDIO_DISPONIBLE = True
except ImportError:
    AUDIO_DISPONIBLE = False

# ----------------------------------------------------------------------
# PALETA "RETRO ARCADE NEON"
# ----------------------------------------------------------------------
COLOR_BG = '#050510'
COLOR_BG_PANEL = '#0b0b20'
COLOR_NEON_CYAN = '#00FFF2'
COLOR_NEON_MAGENTA = '#FF2BD6'
COLOR_NEON_YELLOW = '#F9F002'
COLOR_NEON_PURPLE = '#B967FF'
COLOR_NEON_GREEN = '#39FF14'
COLOR_NEON_RED = '#FF3860'
COLOR_TEXT_DIM = '#6A6A90'
COLOR_GRID_LINES = '#161632'


def _atenuar_color(color_hex, factor):
    """Oscurece un color hexadecimal (para simular el 'halo' del glow neon,
    ya que Tkinter no soporta transparencia real en los rellenos)."""
    color_hex = color_hex.lstrip('#')
    r = int(int(color_hex[0:2], 16) * factor)
    g = int(int(color_hex[2:4], 16) * factor)
    b = int(int(color_hex[4:6], 16) * factor)
    return '#%02X%02X%02X' % (r, g, b)


# Colores por defecto si el .brick NO define STAGE_COLORS ni FRUIT
# (garantiza que snake.brick original siga funcionando igual que antes,
# ahora con el look neon)
COLOR_SNAKE_CABEZA_DEFECTO = COLOR_NEON_GREEN
COLOR_SNAKE_CUERPO_DEFECTO = '#1FCF10'
COLOR_FOOD_DEFECTO = COLOR_NEON_MAGENTA
COLOR_GRID_FIJA = '#241640'
COLOR_PIEZA = COLOR_NEON_CYAN


class Juego:
    def __init__(self, datos_juego):
        self.datos_juego = datos_juego
        self.tipo_juego = self.datos_juego.get('tipo_juego', 'TETRIS')
        config = self.datos_juego.get('config', {})
        self.ancho = config.get('grid_size', [10, 20])[0]
        self.alto = config.get('grid_size', [10, 20])[1]
        self.grid = [[0 for _ in range(self.ancho)] for _ in range(self.alto)]
        self.puntuacion = 0
        self.juego_terminado = False

        # --- NUEVO: estado de accesibilidad (S08 Silenciar, S09 Pausa) ---
        # Generico: funciona sin importar el tipo de juego (Tetris o Snake)
        self.pausado = False
        self.silenciado = False

        # NUEVO: musica de fondo. Se recuerda que pista se pidio (para poder
        # reanudarla tras un efecto de sonido o al desactivar el silencio)
        self.musica_solicitada = None
        self.musica_activa = False

        # Estado temporal compartido por todos los juegos. Tetris también
        # pasa por el mismo loop de actualizacion, asi que estos campos deben
        # existir desde el inicio.
        self.efecto_activo = None
        self.efecto_ticks_restantes = 0

        # Popup motivacional reutilizado por Tetris.
        self.mensaje_motivacional = None
        self.mensaje_motivacional_ticks = 0
        self.ultimo_hito_motivacional = 0

        # NUEVO: parpadeo tipo arcade ("PRESS START") para textos de HUD
        self.blink_contador = 0
        self.blink_state = True

        # NUEVO: opcion seleccionada en el menu de GAME OVER (0=REINTENTAR, 1=SALIR)
        self.opcion_game_over = 0

        # --- Configuracion de la GUI ---
        self.root = tk.Tk()
        self.root.title("BrickScript - " + self.tipo_juego)
        self.root.protocol("WM_DELETE_WINDOW", self.cerrar_ventana)

        self.taman_celda = 25
        self.ancho_canvas = self.ancho * self.taman_celda
        self.alto_canvas = self.alto * self.taman_celda

        self.root.configure(bg=COLOR_BG)

        self.canvas = tk.Canvas(self.root, width=self.ancho_canvas, height=self.alto_canvas,
                                 bg=COLOR_BG, highlightthickness=0)
        self.canvas.pack(side=tk.LEFT, padx=10, pady=10)

        self.marco_score = tk.Frame(self.root, width=200, height=self.alto_canvas, bg=COLOR_BG_PANEL,
                                     highlightbackground=COLOR_NEON_CYAN, highlightthickness=1)
        self.marco_score.pack(side=tk.RIGHT, fill=tk.Y, padx=10, pady=10)

        tk.Label(self.marco_score, text=u"\u25C6 BRICKSCRIPT \u25C6", bg=COLOR_BG_PANEL, fg=COLOR_NEON_CYAN,
                 font=('Consolas', 13, 'bold')).pack(pady=(18, 6), padx=10)
        tk.Frame(self.marco_score, height=2, bg=COLOR_NEON_MAGENTA).pack(fill=tk.X, padx=16, pady=(0, 16))

        tk.Label(self.marco_score, text="PUNTUACION", bg=COLOR_BG_PANEL, fg=COLOR_TEXT_DIM,
                 font=('Consolas', 9, 'bold')).pack(padx=10)
        self.label_score = tk.Label(self.marco_score, text="000000", bg=COLOR_BG_PANEL, fg=COLOR_NEON_CYAN,
                                     font=('Consolas', 22, 'bold'))
        self.label_score.pack(pady=(0, 18), padx=10)

        # NUEVO S07: racha (con barra ASCII estilo pixel-art)
        tk.Label(self.marco_score, text="RACHA", bg=COLOR_BG_PANEL, fg=COLOR_TEXT_DIM,
                 font=('Consolas', 9, 'bold')).pack(padx=10)
        self.label_racha = tk.Label(self.marco_score, text="0", bg=COLOR_BG_PANEL, fg=COLOR_NEON_YELLOW,
                                     font=('Consolas', 13, 'bold'), justify=tk.CENTER)
        self.label_racha.pack(pady=(0, 18), padx=10)

        # NUEVO S03: contador de frutas consumidas por tipo
        self.label_frutas = tk.Label(self.marco_score, text="", bg=COLOR_BG_PANEL, fg=COLOR_NEON_PURPLE,
                                      font=('Consolas', 9), justify=tk.LEFT)
        self.label_frutas.pack(pady=(0, 18), padx=10)

        # NUEVO: indicador de estado (silencio / efecto activo)
        self.label_estado = tk.Label(self.marco_score, text="", bg=COLOR_BG_PANEL, fg=COLOR_NEON_RED,
                                      font=('Consolas', 9, 'bold'))
        self.label_estado.pack(pady=(0, 12), padx=10)

        tk.Frame(self.marco_score, height=2, bg=COLOR_NEON_MAGENTA).pack(fill=tk.X, padx=16, pady=(0, 12))

        self.label_controles = tk.Label(
            self.marco_score,
            text=u"CONTROLES\n\u2191\u2193\u2190\u2192 Mover\nP  Pausa\nM  Silenciar",
            bg=COLOR_BG_PANEL, fg=COLOR_TEXT_DIM, font=('Consolas', 9), justify=tk.LEFT
        )
        self.label_controles.pack(pady=10, padx=10)

        self.root.bind('<Key>', self.manejar_input_gui)

        if self.tipo_juego == 'TETRIS':
            self.pieza_actual = None
            self.pieza_x, self.pieza_y, self.pieza_rotacion = 0, 0, 0
            self.velocidad_gravedad = 0.4
            self.velocidad_inicial_tetris = self.velocidad_gravedad
            self.ultima_pieza_tetris = None
            self.nombre_pieza_tetris = None
            self.piezas_fijadas_tetris = 0
            self.racha_tetris = 0
            self.multiplicador_tetris = 1

        if self.tipo_juego == 'SNAKE':
            self.serpiente_cuerpo = []
            self.serpiente_direccion = (1, 0)
            self.posicion_comida = None

            # NUEVO S04-S06: tipos de fruta. Si el .brick no define ninguna
            # fruta con DEFINE FRUIT, se usa una fruta generica de 1 punto
            # para que snake.brick original siga funcionando igual.
            self.frutas_definidas = self.datos_juego.get('fruits', {})
            if not self.frutas_definidas:
                self.frutas_definidas = {
                    'DEFAULT': {'color': COLOR_FOOD_DEFECTO, 'score': 1, 'pattern': 'SOLID', 'effect': 'NONE'}
                }
            self.fruta_actual = None
            self.contador_frutas = {}  # NUEVO S03

            # NUEVO S07: racha
            self.racha_actual = 0
            self.streak_target = config.get('streak_target', 5)

            # NUEVO S01: colores de la serpiente segun etapa (tamano del cuerpo)
            self.stage_colors = self.datos_juego.get('stage_colors', [])

            # NUEVO: fase de animacion para la etapa "RAINBOW" (arcoiris que fluye)
            self.rainbow_offset = 0.0

            # NUEVO: efecto temporal activado por frutas especiales (EFFECT)
            self.efecto_activo = None
            self.efecto_ticks_restantes = 0

            self.velocidad_gravedad = 0.15

        # NUEVO: TICK_MULTIPLIER opcional (config global del .brick). Se
        # aplica primero, y LUEGO se guarda como base, para que tanto los
        # efectos de fruta como el reinicio (retry) respeten ese multiplicador.
        self.velocidad_gravedad *= config.get('tick_multiplier', 1.0)
        self.velocidad_base = self.velocidad_gravedad

        self.timer_gravedad = 0
        # NUEVO: pantalla de inicio - el juego no arranca (ni ejecuta
        # ON_START) hasta que el jugador presione ENTER
        self.juego_iniciado = False
        self.timer_id = None

    def run(self):
        self.root.after(50, self.game_loop)
        self.root.mainloop()

    def iniciar_juego(self):
        """NUEVO: se llama al presionar ENTER en la pantalla de inicio."""
        self.juego_iniciado = True
        self.ejecutar_evento('ON_START')

    def reiniciar_juego(self):
        """NUEVO: reinicia el estado del juego para intentar de nuevo,
        sin cerrar la ventana (opcion REINTENTAR del menu de GAME OVER)."""
        self.detener_musica()
        self.puntuacion = 0
        self.juego_terminado = False
        self.pausado = False
        self.opcion_game_over = 0
        self.timer_gravedad = 0
        self.velocidad_gravedad = self.velocidad_base
        self.grid = [[0 for _ in range(self.ancho)] for _ in range(self.alto)]

        if self.tipo_juego == 'TETRIS':
            self.pieza_actual = None
            self.pieza_x, self.pieza_y, self.pieza_rotacion = 0, 0, 0
            self.ultima_pieza_tetris = None
            self.nombre_pieza_tetris = None
            self.piezas_fijadas_tetris = 0
            self.racha_tetris = 0
            self.multiplicador_tetris = 1
            self.velocidad_gravedad = self.velocidad_inicial_tetris
            self.velocidad_base = self.velocidad_inicial_tetris

        self.mensaje_motivacional = None
        self.mensaje_motivacional_ticks = 0
        self.ultimo_hito_motivacional = 0

        if self.tipo_juego == 'SNAKE':
            self.serpiente_cuerpo = []
            self.serpiente_direccion = (1, 0)
            self.posicion_comida = None
            self.fruta_actual = None
            self.contador_frutas = {}
            self.racha_actual = 0
            self.rainbow_offset = 0.0

        self.efecto_activo = None
        self.efecto_ticks_restantes = 0

        # Reutiliza ON_START tal cual (vuelve a spawnear jugador/comida,
        # y si el .brick tiene PLAY_MUSIC, la musica arranca de nuevo)
        self.ejecutar_evento('ON_START')

    def game_loop(self):
        # NUEVO: contador para el parpadeo neon (PAUSA / GAME OVER),
        # cambia de estado cada ~400ms (8 ciclos de 50ms)
        self.blink_contador += 1
        if self.blink_contador >= 8:
            self.blink_contador = 0
            self.blink_state = not self.blink_state

        # NUEVO S09: si no ha iniciado, esta en pausa, o el juego termino,
        # no se procesa logica de juego, pero se sigue dibujando (pantalla
        # de inicio / overlay de PAUSA / pantalla de GAME OVER)
        if self.juego_iniciado and not self.pausado and not self.juego_terminado:
            self.timer_gravedad += 0.05
            if self.timer_gravedad >= self.velocidad_gravedad:
                self.timer_gravedad = 0
                self.ejecutar_evento('ON_TICK')
                self._actualizar_efecto_temporal()

            self._actualizar_mensaje_motivacional()

            # NUEVO: el arcoiris fluye con el tiempo, no solo con el movimiento
            if self.tipo_juego == 'SNAKE':
                self.rainbow_offset = (self.rainbow_offset + 0.015) % 1.0

        self.dibujar()
        self.timer_id = self.root.after(50, self.game_loop)

    def cerrar_ventana(self):
        self.detener_musica()
        if self.timer_id:
            self.root.after_cancel(self.timer_id)
        self.root.destroy()
        sys.exit(0)

    def manejar_input_gui(self, event):
        key = event.keysym.upper()

        # NUEVO: pantalla de inicio, se espera ENTER o ESPACIO para arrancar
        if not self.juego_iniciado:
            if key in ('RETURN', 'SPACE'):
                self.iniciar_juego()
            return

        # NUEVO: menu de GAME OVER estilo arcade (REINTENTAR / SALIR),
        # navegable con flechas y confirmado con ENTER/ESPACIO
        if self.juego_terminado:
            if key in ('LEFT', 'RIGHT', 'UP', 'DOWN'):
                self.opcion_game_over = 1 - self.opcion_game_over
            elif key in ('RETURN', 'SPACE'):
                if self.opcion_game_over == 0:
                    self.reiniciar_juego()
                else:
                    self.cerrar_ventana()
            elif key == 'ESCAPE':
                self.cerrar_ventana()
            return

        # NUEVO S09 / S08: pausa y silencio son controles globales de
        # accesibilidad, funcionan siempre, sin depender del .brick
        if key == 'P':
            self.snake_toggle_pausa()
            return
        if key == 'M':
            self.snake_toggle_mute()
            return

        if self.pausado:
            return  # mientras esta en pausa se ignoran las demas teclas

        if self.tipo_juego == 'TETRIS':
            if key == 'UP': self.ejecutar_evento('ON_KEY_UP')
            elif key == 'DOWN': self.ejecutar_evento('ON_KEY_DOWN')
            elif key == 'LEFT': self.ejecutar_evento('ON_KEY_LEFT')
            elif key == 'RIGHT': self.ejecutar_evento('ON_KEY_RIGHT')
        elif self.tipo_juego == 'SNAKE':
            if key == 'UP': self.snake_cambiar_direccion('UP')
            elif key == 'DOWN': self.snake_cambiar_direccion('DOWN')
            elif key == 'LEFT': self.snake_cambiar_direccion('LEFT')
            elif key == 'RIGHT': self.snake_cambiar_direccion('RIGHT')

    # ------------------------------------------------------------------
    # DIBUJO
    # ------------------------------------------------------------------

    def dibujar(self):
        self.canvas.delete("all")
        self.label_score.config(text=str(self.puntuacion).zfill(6))

        self._dibujar_fondo_grid()

        for y in range(self.alto):
            for x in range(self.ancho):
                if self.grid[y][x] == 1:
                    self.dibujar_celda(x, y, COLOR_GRID_FIJA, glow=False)

        if self.tipo_juego == 'TETRIS' and self.pieza_actual:
            patron_pieza = self._tetris_patron_pieza(self.nombre_pieza_tetris)
            sombra_y = self._tetris_posicion_sombra()
            if sombra_y is not None and sombra_y >= self.pieza_y:
                self._tetris_dibujar_pieza(self.pieza_x, sombra_y, self.pieza_rotacion, patron_pieza, ghost=True)
            self._tetris_dibujar_pieza(self.pieza_x, self.pieza_y, self.pieza_rotacion, patron_pieza)

        if self.tipo_juego == 'SNAKE':
            self._dibujar_snake()
            self.label_racha.config(text=str(self.racha_actual) + "\n" + self._texto_barra_racha())
            self.label_frutas.config(text=self._texto_contador_frutas())
            self.label_estado.config(text=self._texto_estado())
        elif self.tipo_juego == 'TETRIS':
            self.label_racha.config(text="RACHA\n" + str(self.racha_tetris) + " PIEZAS\nMULT x" + str(self.multiplicador_tetris))
            self.label_frutas.config(text="")
            if self.mensaje_motivacional and self.mensaje_motivacional_ticks > 0:
                self.label_estado.config(text=self.mensaje_motivacional)
                self.canvas.create_text(
                    self.ancho_canvas // 2, 24,
                    text=self.mensaje_motivacional,
                    fill=COLOR_NEON_YELLOW,
                    font=('Consolas', 14, 'bold')
                )
            else:
                self.label_estado.config(text="")

        # NUEVO: textura sutil tipo pantalla CRT sobre todo el tablero
        self.canvas.create_rectangle(0, 0, self.ancho_canvas, self.alto_canvas,
                                      fill=COLOR_BG, stipple='gray12', outline='')

        self._dibujar_marco_hud()

        if not self.juego_iniciado:
            self._dibujar_overlay_inicio()
        elif self.pausado and not self.juego_terminado:
            self._dibujar_overlay_pausa()
        elif self.juego_terminado:
            self._dibujar_overlay_game_over()

    def _dibujar_fondo_grid(self):
        """NUEVO: fondo negro con cuadricula tenue, look pantalla de arcade."""
        self.canvas.create_rectangle(0, 0, self.ancho_canvas, self.alto_canvas, fill=COLOR_BG, outline='')
        ts = self.taman_celda
        for gx in range(0, self.ancho + 1):
            self.canvas.create_line(gx * ts, 0, gx * ts, self.alto_canvas, fill=COLOR_GRID_LINES)
        for gy in range(0, self.alto + 1):
            self.canvas.create_line(0, gy * ts, self.ancho_canvas, gy * ts, fill=COLOR_GRID_LINES)

    def _dibujar_marco_hud(self):
        """NUEVO: borde neon + esquinas estilo HUD de arcade alrededor del tablero."""
        w, h = self.ancho_canvas, self.alto_canvas
        borde_color = COLOR_NEON_CYAN
        borde_ancho = 2
        if self.tipo_juego == 'TETRIS':
            borde_color, borde_ancho = self._tetris_color_borde_alarma()
        self.canvas.create_rectangle(2, 2, w - 2, h - 2, outline=borde_color, width=borde_ancho)
        largo = 14
        esquinas = [(2, 2, 1, 1), (w - 2, 2, -1, 1), (2, h - 2, 1, -1), (w - 2, h - 2, -1, -1)]
        for cx, cy, dx, dy in esquinas:
            color_esquina = COLOR_NEON_MAGENTA
            ancho_esquina = 3
            if self.tipo_juego == 'TETRIS':
                color_esquina = borde_color
                ancho_esquina = max(2, borde_ancho)
            self.canvas.create_line(cx, cy, cx + largo * dx, cy, fill=color_esquina, width=ancho_esquina)
            self.canvas.create_line(cx, cy, cx, cy + largo * dy, fill=color_esquina, width=ancho_esquina)

    def _tetris_patron_pieza(self, nombre_pieza):
        if not nombre_pieza:
            return None
        base = nombre_pieza.split('_', 1)[0].upper()
        if base == 'I':
            return 'VLINES'
        if base == 'O':
            return 'DOTS'
        if base == 'T':
            return 'CROSS'
        if base in ('J', 'L'):
            return 'DIAGONAL'
        if base in ('S', 'Z'):
            return 'S'
        return None

    def _tetris_posicion_sombra(self):
        if not self.pieza_actual:
            return None
        sombra_y = self.pieza_y
        while not self.tetris_verificar_colision(self.pieza_x, sombra_y + 1, self.pieza_rotacion):
            sombra_y += 1
        return sombra_y

    def _tetris_dibujar_pieza(self, x, y, rotacion, patron_pieza, ghost=False):
        matriz_pieza = self.pieza_actual[rotacion]
        color = COLOR_PIEZA
        if ghost:
            color = _atenuar_color(COLOR_PIEZA, 0.25)
        for y_offset, fila in enumerate(matriz_pieza):
            for x_offset, celda in enumerate(fila):
                if celda == 1:
                    self.dibujar_celda(x + x_offset, y + y_offset, color, patron_pieza, glow=not ghost, ghost=ghost)

    def _tetris_altura_apilada(self):
        """Devuelve la fraccion de altura ocupada por la pila fija en Tetris."""
        if self.tipo_juego != 'TETRIS':
            return 0.0
        fila_minima = None
        for y, fila in enumerate(self.grid):
            if any(celda == 1 for celda in fila):
                fila_minima = y
                break
        if fila_minima is None:
            return 0.0
        altura_ocupada = self.alto - fila_minima
        return altura_ocupada / float(self.alto)

    def _mezclar_color(self, color_a, color_b, factor):
        """Mezcla dos colores hexadecimales con factor entre 0.0 y 1.0."""
        factor = max(0.0, min(1.0, factor))
        color_a = color_a.lstrip('#')
        color_b = color_b.lstrip('#')
        ra = int(color_a[0:2], 16)
        ga = int(color_a[2:4], 16)
        ba = int(color_a[4:6], 16)
        rb = int(color_b[0:2], 16)
        gb = int(color_b[2:4], 16)
        bb = int(color_b[4:6], 16)
        r = int(ra + (rb - ra) * factor)
        g = int(ga + (gb - ga) * factor)
        b = int(ba + (bb - ba) * factor)
        return '#%02X%02X%02X' % (r, g, b)

    def _tetris_color_borde_alarma(self):
        """Devuelve color y grosor del borde segun la altura de la pila."""
        ocupacion = self._tetris_altura_apilada()
        if ocupacion < 0.70:
            return COLOR_NEON_CYAN, 2

        progreso = (ocupacion - 0.70) / 0.25
        progreso = max(0.0, min(1.0, progreso))
        if self.blink_state:
            color_base = self._mezclar_color(COLOR_NEON_CYAN, COLOR_NEON_RED, progreso)
        else:
            color_base = self._mezclar_color(COLOR_NEON_CYAN, COLOR_TEXT_DIM, 0.15 + progreso * 0.35)
        ancho = 2 + int(progreso * 2)
        return color_base, ancho

    def _dibujar_snake(self):
        # S04-S06: la comida se dibuja con el color y el patron de su tipo de fruta
        if self.posicion_comida and self.fruta_actual:
            x, y = self.posicion_comida
            color = self.fruta_actual.get('color', COLOR_FOOD_DEFECTO)
            patron = self.fruta_actual.get('pattern', 'SOLID')
            self.dibujar_celda(x, y, color, patron)

        # S01: color de la serpiente segun la etapa actual (tamano del cuerpo)
        color_etapa = self._color_etapa_actual()
        total_segmentos = len(self.serpiente_cuerpo)
        for i, segmento in enumerate(self.serpiente_cuerpo):
            x, y = segmento
            if color_etapa == 'RAINBOW':
                # NUEVO: cada segmento tiene su propio tono, animado con el tiempo
                color = self._color_arcoiris(i, total_segmentos)
            elif color_etapa:
                color = color_etapa
            else:
                # Retrocompatibilidad: sin STAGE_COLORS definido
                color = COLOR_SNAKE_CABEZA_DEFECTO if i == 0 else COLOR_SNAKE_CUERPO_DEFECTO
            # S02: puntos decorativos en el cuerpo (cada 3 segmentos)
            patron = 'DOTS' if i > 0 and i % 3 == 0 else None
            self.dibujar_celda(x, y, color, patron)

    def _color_etapa_actual(self):
        """S01: devuelve el color (o el texto 'RAINBOW') de la etapa segun
        la longitud actual de la serpiente. None si no hay STAGE_COLORS."""
        longitud = len(self.serpiente_cuerpo)
        for etapa in self.stage_colors:
            minimo, maximo = etapa['rango']
            if minimo <= longitud <= maximo:
                return etapa['color']
        return None

    def _color_arcoiris(self, indice, total):
        """NUEVO: genera un color HSV distinto por segmento y lo anima con
        self.rainbow_offset para que el arcoiris parezca fluir."""
        hue = (indice / float(max(total, 1)) + self.rainbow_offset) % 1.0
        r, g, b = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
        return '#%02X%02X%02X' % (int(r * 255), int(g * 255), int(b * 255))

    def dibujar_celda(self, x, y, color, patron=None, glow=True, ghost=False):
        ts = self.taman_celda
        x1, y1 = x * ts, y * ts
        x2, y2 = x1 + ts, y1 + ts

        # NUEVO: efecto glow neon. Tkinter no soporta transparencia real,
        # asi que se simula dibujando 2 capas concentricas mas oscuras
        # detras de la celda principal (un "halo" que se funde con el fondo).
        if ghost:
            fill_color = _atenuar_color(color, 0.18)
            outline_color = _atenuar_color(COLOR_NEON_CYAN, 0.55)
            self.canvas.create_rectangle(
                x1 + 1, y1 + 1, x2 - 1, y2 - 1,
                fill=fill_color, outline=outline_color, width=1,
                dash=(3, 2), stipple='gray50'
            )
        elif glow:
            halo_ext = _atenuar_color(color, 0.22)
            halo_med = _atenuar_color(color, 0.45)
            self.canvas.create_rectangle(x1 - 3, y1 - 3, x2 + 3, y2 + 3, fill=halo_ext, outline='')
            self.canvas.create_rectangle(x1 - 1, y1 - 1, x2 + 1, y2 + 1, fill=halo_med, outline='')

        # Margen de 1px entre celdas para dar el efecto "bloques" pixel-art
        if not ghost:
            self.canvas.create_rectangle(x1 + 1, y1 + 1, x2 - 1, y2 - 1, fill=color, outline=COLOR_BG, width=1)

        # NUEVO: patrones dentro de la celda ademas del color (S02 / S06 /
        # rediseno visual). Ayuda tambien a usuarios con daltonismo, ya que
        # no dependen unicamente del color para distinguir elementos.
        if patron == 'VLINES':
            for i in (1, 2):
                lx = x1 + (i * ts // 3)
                self.canvas.create_line(lx, y1 + 2, lx, y2 - 2, fill=COLOR_BG, width=1)
        elif patron == 'STRIPES':
            for i in (1, 2):
                ly = y1 + (i * ts // 3)
                self.canvas.create_line(x1 + 2, ly, x2 - 2, ly, fill=COLOR_BG, width=1)
        elif patron == 'DOTS':
            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
            r = ts // 6
            self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r, fill=COLOR_BG, outline='')
        elif patron == 'CROSS':
            self.canvas.create_line(x1 + 3, y1 + 3, x2 - 3, y2 - 3, fill=COLOR_BG, width=2)
            self.canvas.create_line(x1 + 3, y2 - 3, x2 - 3, y1 + 3, fill=COLOR_BG, width=2)
        elif patron == 'DIAGONAL':
            self.canvas.create_line(x1 + 2, y2 - 3, x2 - 3, y1 + 2, fill=COLOR_BG, width=2)
            self.canvas.create_line(x1 + 5, y2 - 1, x2 - 1, y1 + 5, fill=COLOR_BG, width=1)
        elif patron == 'S':
            puntos = [
                x1 + 3, y1 + 5,
                x1 + 7, y1 + 2,
                x2 - 4, y1 + 5,
                x2 - 7, y1 + 10,
                x1 + 5, y2 - 5,
                x1 + 2, y2 - 2,
            ]
            self.canvas.create_line(*puntos, fill=COLOR_BG, width=2, smooth=True, splinesteps=12)

    def _dibujar_overlay_inicio(self):
        """NUEVO: pantalla de bienvenida, se muestra hasta que se presiona ENTER."""
        self.canvas.create_rectangle(0, 0, self.ancho_canvas, self.alto_canvas,
                                      fill=COLOR_BG, stipple='gray25', outline='')
        cx = self.ancho_canvas // 2
        cy = self.alto_canvas // 2
        self.canvas.create_text(cx, cy - 40, text=self.tipo_juego,
                                 fill=COLOR_NEON_CYAN, font=('Consolas', 24, 'bold'))
        color = COLOR_NEON_YELLOW if self.blink_state else _atenuar_color(COLOR_NEON_YELLOW, 0.3)
        self.canvas.create_text(cx, cy + 6, text="PRESIONA ENTER PARA JUGAR",
                                 fill=color, font=('Consolas', 12, 'bold'))
        self.canvas.create_text(cx, cy + 40, text="Flechas: Mover   P: Pausa   M: Silenciar",
                                 fill=COLOR_TEXT_DIM, font=('Consolas', 9))

    def _dibujar_overlay_pausa(self):
        self.canvas.create_rectangle(0, 0, self.ancho_canvas, self.alto_canvas,
                                      fill=COLOR_BG, stipple='gray50', outline='')
        color = COLOR_NEON_YELLOW if self.blink_state else _atenuar_color(COLOR_NEON_YELLOW, 0.35)
        self.canvas.create_text(
            self.ancho_canvas // 2, self.alto_canvas // 2,
            text=u"\u25A0 PAUSA \u25A0\n\nP para continuar",
            fill=color, font=('Consolas', 16, 'bold'), justify=tk.CENTER
        )

    def _dibujar_overlay_game_over(self):
        """NUEVO: pantalla de GAME OVER con menu REINTENTAR/SALIR dibujado
        en el canvas (estilo arcade), en vez de un dialogo nativo de Windows
        que rompia la ambientacion y solo permitia cerrar."""
        self.canvas.create_rectangle(0, 0, self.ancho_canvas, self.alto_canvas,
                                      fill=COLOR_BG, stipple='gray25', outline='')
        color_titulo = COLOR_NEON_RED if self.blink_state else _atenuar_color(COLOR_NEON_RED, 0.3)
        cx = self.ancho_canvas // 2
        cy = self.alto_canvas // 2

        self.canvas.create_text(cx, cy - 50, text="GAME OVER", fill=color_titulo,
                                 font=('Consolas', 22, 'bold'))
        self.canvas.create_text(cx, cy - 16, text="PUNTUACION: " + str(self.puntuacion),
                                 fill=COLOR_NEON_CYAN, font=('Consolas', 12, 'bold'))

        opciones = [("REINTENTAR", 0), ("SALIR", 1)]
        y_opcion = cy + 22
        for texto, indice in opciones:
            if indice == self.opcion_game_over:
                color = COLOR_NEON_YELLOW if self.blink_state else _atenuar_color(COLOR_NEON_YELLOW, 0.4)
                texto_mostrado = u"\u25B6 " + texto + u" \u25C0"
            else:
                color = COLOR_TEXT_DIM
                texto_mostrado = texto
            self.canvas.create_text(cx, y_opcion, text=texto_mostrado, fill=color,
                                     font=('Consolas', 13, 'bold'))
            y_opcion += 26

        self.canvas.create_text(cx, y_opcion + 8, text=u"\u2190 \u2192 Elegir    ENTER Confirmar",
                                 fill=COLOR_TEXT_DIM, font=('Consolas', 9))

    def _texto_barra_racha(self):
        """NUEVO S07: barra de progreso ASCII (bloques) hacia el bono de racha."""
        if not self.streak_target:
            return ""
        progreso = self.racha_actual % self.streak_target
        if self.racha_actual > 0 and progreso == 0:
            progreso = self.streak_target
        longitud_barra = 10
        llenos = min(int((progreso / float(self.streak_target)) * longitud_barra), longitud_barra)
        return u'\u2588' * llenos + u'\u2591' * (longitud_barra - llenos)

    def _texto_contador_frutas(self):
        if not self.contador_frutas:
            return "FRUTAS\n(ninguna aun)"
        lineas = ["FRUTAS"]
        for nombre, cantidad in self.contador_frutas.items():
            lineas.append(nombre + ": " + str(cantidad))
        return "\n".join(lineas)

    def _texto_estado(self):
        estados = []
        if self.silenciado:
            estados.append("SONIDO: OFF")
        if self.efecto_activo:
            estados.append("EFECTO: " + self.efecto_activo)
        return "\n".join(estados)

    def _hito_motivacional(self, puntuacion):
        if puntuacion <= 0:
            return 0
        if puntuacion <= 100:
            return (puntuacion // 10) * 10
        return 100 + (((puntuacion - 100) // 50) * 50)

    def _texto_motivacional(self, hito):
        if hito < 50:
            return "¡BIEN!"
        if hito < 100:
            return "¡SIGUE ASI!"
        if hito == 100:
            return "¡EXCELENTE!"
        return "¡IMPARABLE!"

    def _actualizar_mensaje_motivacional(self):
        if self.mensaje_motivacional_ticks <= 0:
            return
        self.mensaje_motivacional_ticks -= 1
        if self.mensaje_motivacional_ticks <= 0:
            self.mensaje_motivacional = None

    def _disparar_mensaje_motivacional(self):
        hito = self._hito_motivacional(self.puntuacion)
        if hito > self.ultimo_hito_motivacional:
            self.ultimo_hito_motivacional = hito
            self.mensaje_motivacional = self._texto_motivacional(hito)
            self.mensaje_motivacional_ticks = 24

    def _tetris_registrar_racha(self):
        self.racha_tetris += 1
        self.multiplicador_tetris = 2 if self.racha_tetris > 3 else 1

    def _tetris_sumar_puntos(self, puntos_base):
        puntos = puntos_base * self.multiplicador_tetris
        self.puntuacion += puntos
        self._disparar_mensaje_motivacional()

    def _tetris_actualizar_velocidad(self):
        base_inicial = getattr(self, 'velocidad_inicial_tetris', self.velocidad_gravedad)
        velocidad_natural = max(0.12, base_inicial * (0.96 ** self.piezas_fijadas_tetris))
        self.velocidad_base = velocidad_natural
        if not self.efecto_activo:
            self.velocidad_gravedad = velocidad_natural

    # ------------------------------------------------------------------
    # EVENTOS / ACCIONES DEL DSL
    # ------------------------------------------------------------------

    def ejecutar_evento(self, nombre_evento):
        if nombre_evento in self.datos_juego['events']:
            for accion in self.datos_juego['events'][nombre_evento]:
                verbo, objeto = accion.get('accion'), accion.get('objeto')

                if verbo == 'INCREASE_SCORE':
                    if self.tipo_juego == 'TETRIS':
                        self._tetris_sumar_puntos(int(objeto))
                    else:
                        self.puntuacion += int(objeto)
                    continue
                if verbo == 'GAME_OVER':
                    self.juego_terminado = True
                    self.detener_musica()  # deja el canal libre para el sonido de derrota

                # NUEVO: acciones de accesibilidad, disponibles en cualquier
                # evento y cualquier tipo de juego (S08, S09, S10)
                if verbo == 'TOGGLE_PAUSE': self.snake_toggle_pausa()
                if verbo == 'TOGGLE_MUTE': self.snake_toggle_mute()
                if verbo == 'PLAY_SOUND': self.reproducir_sonido(accion['params'][0])
                if verbo == 'PLAY_MUSIC': self.reproducir_musica(accion['params'][0])

                if self.tipo_juego == 'TETRIS':
                    if verbo == 'SPAWN': self.tetris_spawn_pieza()
                    if verbo == 'MOVE': self.tetris_mover_pieza(accion['params'][0])
                    if verbo == 'ROTATE': self.tetris_rotar_pieza()

                if self.tipo_juego == 'SNAKE':
                    if verbo == 'SPAWN' and objeto == 'PLAYER': self.snake_spawn_jugador(accion)
                    if verbo == 'SPAWN' and objeto == 'FOOD': self.snake_spawn_comida()
                    if verbo == 'MOVE' and objeto == 'PLAYER': self.snake_mover_jugador()
                    if verbo == 'GROW': self.snake_crecer()

    # ------------------------------------------------------------------
    # TETRIS (logica identica a la version original, sin cambios)
    # ------------------------------------------------------------------

    def tetris_spawn_pieza(self):
        nombres_piezas = list(self.datos_juego['shapes'].keys())
        if getattr(self, 'ultima_pieza_tetris', None) in nombres_piezas and len(nombres_piezas) > 1:
            nombres_piezas = [nombre for nombre in nombres_piezas if nombre != self.ultima_pieza_tetris]
        nombre_pieza = random.choice(nombres_piezas)
        self.ultima_pieza_tetris = nombre_pieza
        self.nombre_pieza_tetris = nombre_pieza
        self.pieza_actual = self.datos_juego['shapes'][nombre_pieza]
        self.pieza_x, self.pieza_y, self.pieza_rotacion = self.ancho // 2 - 2, 0, 0
        if self.tetris_verificar_colision(self.pieza_x, self.pieza_y, self.pieza_rotacion):
            self.juego_terminado = True
            self.racha_tetris = 0
            self.multiplicador_tetris = 1

    def tetris_mover_pieza(self, direccion):
        if not self.pieza_actual: return
        dx, dy = 0, 0
        if direccion == 'LEFT': dx = -1
        elif direccion == 'RIGHT': dx = 1
        elif direccion == 'DOWN': dy = 1
        if not self.tetris_verificar_colision(self.pieza_x + dx, self.pieza_y + dy, self.pieza_rotacion):
            self.pieza_x += dx
            self.pieza_y += dy
        elif dy > 0:
            self.tetris_fijar_pieza()

    def tetris_rotar_pieza(self):
        if not self.pieza_actual: return
        nueva_rotacion = (self.pieza_rotacion + 1) % len(self.pieza_actual)
        if not self.tetris_verificar_colision(self.pieza_x, self.pieza_y, nueva_rotacion):
            self.pieza_rotacion = nueva_rotacion

    def tetris_fijar_pieza(self):
        matriz_pieza = self.pieza_actual[self.pieza_rotacion]
        for y_offset, fila in enumerate(matriz_pieza):
            for x_offset, celda in enumerate(fila):
                if celda == 1:
                    if 0 <= self.pieza_y + y_offset < self.alto and 0 <= self.pieza_x + x_offset < self.ancho:
                        self.grid[self.pieza_y + y_offset][self.pieza_x + x_offset] = 1
        self._tetris_registrar_racha()
        self._tetris_sumar_puntos(10)
        self.piezas_fijadas_tetris += 1
        self._tetris_actualizar_velocidad()
        self.pieza_actual = None
        self.tetris_limpiar_lineas()
        self.ejecutar_evento('ON_START')

    def tetris_verificar_colision(self, x, y, rotacion):
        if not self.pieza_actual: return False
        matriz_pieza = self.pieza_actual[rotacion]
        for y_offset, fila in enumerate(matriz_pieza):
            for x_offset, celda in enumerate(fila):
                if celda == 1:
                    nuevo_x, nuevo_y = x + x_offset, y + y_offset
                    if not (0 <= nuevo_x < self.ancho and 0 <= nuevo_y < self.alto and self.grid[nuevo_y][nuevo_x] == 0):
                        return True
        return False

    def tetris_limpiar_lineas(self):
        nuevo_grid = [fila for fila in self.grid if not all(fila)]
        lineas_limpias = self.alto - len(nuevo_grid)
        if lineas_limpias > 0:
            self.grid = [[0] * self.ancho for _ in range(lineas_limpias)] + nuevo_grid
            for _ in range(lineas_limpias): self.ejecutar_evento('ON_LINE_CLEAR')

    # ------------------------------------------------------------------
    # SNAKE
    # ------------------------------------------------------------------

    def snake_spawn_jugador(self, accion):
        coords = accion['params'][0] if accion['params'] else [self.ancho // 2, self.alto // 2]
        self.serpiente_cuerpo = [(coords[0], coords[1])]
        self.serpiente_direccion = (1, 0)

    def snake_spawn_comida(self):
        while True:
            x, y = random.randint(0, self.ancho - 1), random.randint(0, self.alto - 1)
            if (x, y) not in self.serpiente_cuerpo:
                self.posicion_comida = (x, y)
                break
        # NUEVO S04-S06: se elige al azar un tipo de fruta entre las definidas
        nombre_fruta = random.choice(list(self.frutas_definidas.keys()))
        self.fruta_actual = dict(self.frutas_definidas[nombre_fruta])
        self.fruta_actual['nombre'] = nombre_fruta

    def snake_mover_jugador(self):
        if not self.serpiente_cuerpo: return
        cabeza_x, cabeza_y = self.serpiente_cuerpo[0]
        dir_x, dir_y = self.serpiente_direccion
        nueva_cabeza = (cabeza_x + dir_x, cabeza_y + dir_y)

        if not (0 <= nueva_cabeza[0] < self.ancho and 0 <= nueva_cabeza[1] < self.alto):
            self.racha_actual = 0  # NUEVO S07: la racha se rompe al chocar
            self.ejecutar_evento('ON_COLLISION_WALL')
            return

        if nueva_cabeza in self.serpiente_cuerpo[:-1]:
            self.racha_actual = 0
            self.ejecutar_evento('ON_COLLISION_SELF')
            return

        self.serpiente_cuerpo.insert(0, nueva_cabeza)

        if nueva_cabeza == self.posicion_comida:
            self._comer_fruta()
            self.ejecutar_evento('ON_EAT_FOOD')
        else:
            self.serpiente_cuerpo.pop()

    def _comer_fruta(self):
        """NUEVO: aplica S03 (contador), S04-S06 (puntaje/efecto) y S07 (racha)."""
        fruta = self.fruta_actual or {'nombre': 'DEFAULT', 'score': 1, 'effect': 'NONE'}
        nombre = fruta.get('nombre', 'DEFAULT')

        # S03: contador de tipos de fruta consumida
        self.contador_frutas[nombre] = self.contador_frutas.get(nombre, 0) + 1

        # S07: racha. Cada fruta comida sin chocar aumenta la racha.
        self.racha_actual += 1
        multiplicador = 1.0
        if self.streak_target and self.racha_actual % self.streak_target == 0:
            multiplicador = 1.5  # bono de puntos al alcanzar el objetivo de racha
            self.ejecutar_evento('ON_STREAK_UPDATE')

        puntos = int(fruta.get('score', 1) * multiplicador)
        self.puntuacion += puntos

        # S06: efectos especiales segun el tipo de fruta
        efecto = fruta.get('effect', 'NONE')
        if efecto == 'DOUBLE_POINTS':
            self.puntuacion += puntos
        elif efecto == 'SPEED_BOOST':
            self._activar_efecto_temporal('SPEED_BOOST', velocidad=self.velocidad_base * 0.6, duracion_ticks=40)
        elif efecto == 'SLOW_TIME':
            self._activar_efecto_temporal('SLOW_TIME', velocidad=self.velocidad_base * 1.6, duracion_ticks=40)

        # S10: pista de audio al comer (si el .brick no define PLAY_SOUND en
        # ON_EAT_FOOD, este sonido por defecto sirve como retroalimentacion
        # inmediata; se puede sobreescribir agregando la accion en el .brick)
        self.reproducir_sonido('eat.wav')

    def _activar_efecto_temporal(self, nombre, velocidad, duracion_ticks):
        self.efecto_activo = nombre
        self.efecto_ticks_restantes = duracion_ticks
        self.velocidad_gravedad = velocidad

    def _actualizar_efecto_temporal(self):
        if self.efecto_activo:
            self.efecto_ticks_restantes -= 1
            if self.efecto_ticks_restantes <= 0:
                self.efecto_activo = None
                self.velocidad_gravedad = self.velocidad_base

    def snake_cambiar_direccion(self, direccion):
        if direccion == 'UP' and self.serpiente_direccion[1] != 1:
            self.serpiente_direccion = (0, -1)
        elif direccion == 'DOWN' and self.serpiente_direccion[1] != -1:
            self.serpiente_direccion = (0, 1)
        elif direccion == 'LEFT' and self.serpiente_direccion[0] != 1:
            self.serpiente_direccion = (-1, 0)
        elif direccion == 'RIGHT' and self.serpiente_direccion[0] != -1:
            self.serpiente_direccion = (1, 0)

    def snake_crecer(self):
        pass

    # ------------------------------------------------------------------
    # ACCESIBILIDAD: PAUSA / SILENCIO / AUDIO (S08, S09, S10)
    # ------------------------------------------------------------------

    def snake_toggle_pausa(self):
        self.pausado = not self.pausado

    def snake_toggle_mute(self):
        self.silenciado = not self.silenciado
        if self.silenciado:
            self._detener_canal_audio()
        elif self.musica_solicitada and self.musica_activa:
            # Se desactivo el silencio: retoma la musica que estaba sonando
            self.reproducir_musica(self.musica_solicitada, reiniciar=False)

    def reproducir_sonido(self, nombre_archivo):
        """S10: reproduce un efecto corto, respetando el silencio (S08)."""
        if self.silenciado:
            return
        if AUDIO_DISPONIBLE:
            try:
                winsound.PlaySound(nombre_archivo, winsound.SND_FILENAME | winsound.SND_ASYNC)
                # NOTA: winsound solo tiene UN canal de audio. Un efecto
                # corto interrumpe la musica de fondo; se reprograma su
                # reinicio poco despues para no dejarla en silencio.
                if self.musica_activa and self.musica_solicitada:
                    self.root.after(500, self._reanudar_musica_tras_efecto)
            except Exception:
                # Si el archivo no existe o falla el driver de audio, el
                # juego no debe interrumpirse por esto.
                pass

    def reproducir_musica(self, nombre_archivo, reiniciar=True):
        """NUEVO: musica de fondo en bucle (SND_LOOP), tambien respeta el silencio."""
        self.musica_solicitada = nombre_archivo
        if reiniciar:
            self.musica_activa = True
        if self.silenciado:
            return
        if AUDIO_DISPONIBLE:
            try:
                winsound.PlaySound(nombre_archivo,
                                    winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_LOOP)
            except Exception:
                pass

    def detener_musica(self):
        self.musica_activa = False
        self._detener_canal_audio()

    def _detener_canal_audio(self):
        if AUDIO_DISPONIBLE:
            try:
                winsound.PlaySound(None, winsound.SND_PURGE)
            except Exception:
                pass

    def _reanudar_musica_tras_efecto(self):
        if self.musica_activa and not self.silenciado and self.musica_solicitada:
            self.reproducir_musica(self.musica_solicitada, reiniciar=False)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Uso: python runtime.py <archivo_juego.json>")
        sys.exit(1)
    archivo_juego = sys.argv[1]
    try:
        with open(archivo_juego, 'r') as f:
            datos_juego = json.load(f)
    except IOError:
        print("Error: No se pudo encontrar el archivo " + archivo_juego)
        sys.exit(1)
    juego = Juego(datos_juego)
    juego.run()